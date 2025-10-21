"""
Diff Validator Lambda.

Validates that generated summaries stay aligned with the original article by
highlighting factual anchor points (numbers / named entities) and checking that
each diff point appears in the source text. The Lambda also fills in
`diff_points` when the summarizer omitted them.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterable, List

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

NUMBER_PATTERN = re.compile(r"\b\d{1,4}(?:[,.]\d{3})*(?:\.\d+)?\b")
EN_PROPER_NOUN_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b")
JP_PROPER_NOUN_PATTERN = re.compile(r"[一-龥々〆ヵヶ][\w一-龥々〆ヵヶー]*")


def _normalise_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def extract_candidate_facts(text: str) -> List[str]:
    """Return sorted unique list of numeric values and named entities."""
    if not text:
        return []

    candidates: set[str] = set()
    for pattern in (NUMBER_PATTERN, EN_PROPER_NOUN_PATTERN, JP_PROPER_NOUN_PATTERN):
        for match in pattern.findall(text):
            cleaned = _normalise_whitespace(match)
            if cleaned:
                candidates.add(cleaned)

    sorted_candidates = sorted(candidates, key=lambda item: (len(item), item.lower()))
    LOGGER.debug("Extracted %s candidate facts", len(sorted_candidates))
    return sorted_candidates[:20]


def validate_diff_points(diff_points: Iterable[str], article: str) -> Dict[str, Any]:
    """Ensure each diff point appears in the article text."""
    article_lower = article.lower()
    validation: list[dict[str, Any]] = []
    for point in diff_points:
        if not point:
            continue
        normalised = point.strip()
        exists = normalised.lower() in article_lower
        validation.append({"value": normalised, "present_in_article": exists})
    return {
        "points": validation,
        "missing": [item["value"] for item in validation if not item["present_in_article"]],
        "status": "ok" if all(item["present_in_article"] for item in validation) else "needs_review",
    }


def _ensure_diff_points(article: str, summaries: Dict[str, Any]) -> List[str]:
    diff_points = summaries.get("diff_points") or []
    if isinstance(diff_points, str):
        diff_points = [diff_points]

    diff_points = [point.strip() for point in diff_points if point and point.strip()]
    if diff_points:
        return diff_points

    extracted = extract_candidate_facts(article)
    LOGGER.info("Populating diff_points from article facts (count=%s)", len(extracted))
    return extracted[:5]


def handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    article = event.get("article_body") or ""
    summaries = event.get("summaries") or {}

    if not article:
        LOGGER.warning("Article body is empty; diff validation may be unreliable")
    if not summaries:
        raise ValueError("Event missing summaries for diff validation")

    diff_points = _ensure_diff_points(article, summaries)
    validation = validate_diff_points(diff_points, article)

    enriched = dict(event)
    enriched["summaries"] = {
        **summaries,
        "diff_points": diff_points,
    }
    enriched["diff_validation"] = validation
    return enriched


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    if isinstance(event, str):
        event = json.loads(event)
    return handle(event, context)
