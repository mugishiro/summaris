"""
Utility helpers for URL normalisation shared across Lambdas.

The logic matches the preprocessor requirements so that dispatcher and other
services produce consistent identifiers for the same article URL.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


_TRACKING_PARAMS: set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
}


def strip_tracking_params(pairs: Iterable[Tuple[str, str]]) -> list[Tuple[str, str]]:
    """Remove common tracking parameters from a parsed query string."""
    return [(k, v) for k, v in pairs if k not in _TRACKING_PARAMS]


def normalize_url(url: str) -> Tuple[str, str]:
    """
    Produce a canonical representation of the URL and its SHA-256 fingerprint.

    Steps:
    - default to https scheme when missing
    - lowercase scheme / host
    - collapse default ports
    - remove fragment
    - sort query parameters after dropping well-known tracking params
    """
    parsed = urlparse((url or "").strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    path = parsed.path or "/"

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    hostname = netloc.split(":")[0]
    if not hostname.endswith("straitstimes.com"):
        query_pairs = strip_tracking_params(query_pairs)
    query_pairs.sort()
    normalized_query = urlencode(query_pairs, doseq=True)

    normalized = urlunparse((scheme, netloc, path, "", normalized_query, ""))
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return normalized, fingerprint


def ensure_source_link(source_id: str, url: str | None) -> str | None:
    """Ensure source-specific accessibility requirements are applied to article URLs."""
    if not url:
        return url
    if source_id != "straits-times":
        return url
    try:
        parsed = urlparse(url)
    except ValueError:
        return url

    hostname = parsed.netloc.lower()
    if not hostname.endswith("straitstimes.com"):
        return url

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    existing_keys = {key for key, _ in query_pairs}
    updated = False
    if "utm_source" not in existing_keys:
        query_pairs.append(("utm_source", "rss"))
        updated = True
    if "utm_medium" not in existing_keys:
        query_pairs.append(("utm_medium", "referral"))
        updated = True

    if not updated:
        return url

    rebuilt = urlencode(query_pairs, doseq=True)
    rebuilt_url = urlunparse(parsed._replace(query=rebuilt))
    return rebuilt_url


__all__ = ["normalize_url", "strip_tracking_params", "ensure_source_link"]
