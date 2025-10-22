"""
Preprocessor Lambda.

Responsibilities:
- Normalize the article URL (remove tracking params, sort query etc.)
- Compute URL fingerprint and article SimHash for duplicate detection.
- Enrich the event payload for downstream Lambdas.

Expected input (from Collector Lambda):
{
  "source": {...},
  "item": {"id": "...", "title": "...", "link": "..."},
  "article_body": "...",
  "metrics": {"fetch_seconds": 1.23}
}

Output is the same event structure with an additional "preprocess" section:
{
  ...
  "preprocess": {
    "url": {...},
    "hashes": {...}
  }
}
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from typing import Any, Dict, List

from shared.url import normalize_url


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

SIMHASH_BITS = int(os.getenv("SIMHASH_BITS", "64"))

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    normalized = unicodedata.normalize("NFKC", text or "")
    return _WORD_RE.findall(normalized.lower())


def compute_simhash(text: str, hashbits: int = SIMHASH_BITS) -> str:
    """
    Compute a simple SimHash fingerprint for the given text.
    Returns a hexadecimal string padded to hashbits/4 length.
    """
    if hashbits % 8 != 0:
        raise ValueError("SIMHASH_BITS must be a multiple of 8")

    vector = [0] * hashbits
    tokens = _tokenize(text)
    if not tokens:
        return "0" * (hashbits // 4)

    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for bit_index in range(hashbits):
            mask = 1 << bit_index
            vector[bit_index] += 1 if h & mask else -1

    fingerprint = 0
    for bit_index, weight in enumerate(vector):
        if weight > 0:
            fingerprint |= 1 << bit_index

    return f"{fingerprint:0{hashbits // 4}x}"




def enrich_event(event: Dict[str, Any]) -> Dict[str, Any]:
    if "item" not in event or "link" not in event["item"]:
        raise ValueError("Event.item.link is required for preprocessing")
    if "article_body" not in event:
        raise ValueError("Event.article_body is required for preprocessing")

    normalized_url, fingerprint = normalize_url(event["item"]["link"])
    simhash_value = compute_simhash(event["article_body"])

    preprocess_payload = {
        "url": {
            "normalized": normalized_url,
            "fingerprint": fingerprint,
        },
        "hashes": {
            "simhash": simhash_value,
            "sha256": hashlib.sha256(event["article_body"].encode("utf-8")).hexdigest(),
        },
    }

    item = dict(event["item"])
    item["normalized_link"] = normalized_url
    item["link_fingerprint"] = fingerprint

    return {
        **event,
        "item": item,
        "preprocess": preprocess_payload,
    }


def handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    LOGGER.info("Preprocessing article item=%s", event.get("item", {}).get("id"))
    enriched = enrich_event(event)
    return enriched


def lambda_handler(event: Any, context: Any) -> Dict[str, Any]:
    if isinstance(event, str):
        event = json.loads(event)
    return handle(event, context)


__all__ = [
    "compute_simhash",
    "normalize_url",
    "enrich_event",
    "lambda_handler",
]
