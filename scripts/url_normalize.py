#!/usr/bin/env python3
"""
URL normalization helper.

Removes common tracking parameters, sorts query strings, normalizes scheme/host,
and returns a stable hash identifier. Supports stdin/CLI usage to aid duplicate
detection experiments in development plan phase 0.3.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Dict, List
from urllib.parse import parse_qsl, urlparse, urlunparse, urlencode


TRACKING_PARAMS = {
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


def normalize_url(url: str) -> Dict[str, str]:
    parsed = urlparse(url.strip())

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"

    # remove default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    query_pairs: List[tuple[str, str]] = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k not in TRACKING_PARAMS
    ]
    # sort query parameters for stable ordering
    query_pairs.sort()
    normalized_query = urlencode(query_pairs, doseq=True)

    normalized = urlunparse((scheme, netloc, path, "", normalized_query, ""))
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    return {
        "original": url,
        "normalized": normalized,
        "fingerprint": fingerprint,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "urls",
        nargs="*",
        help="URLs to normalize (if omitted, read from stdin).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as compact JSON lines (default is human-readable).",
    )
    args = parser.parse_args()

    urls = args.urls or [line.strip() for line in sys.stdin if line.strip()]
    if not urls:
        print("No URLs provided.", file=sys.stderr)
        return 1

    for url in urls:
        data = normalize_url(url)
        if args.json:
            print(json.dumps(data, ensure_ascii=False))
        else:
            print(f"original   : {data['original']}")
            print(f"normalized : {data['normalized']}")
            print(f"fingerprint: {data['fingerprint']}")
            print("-" * 40)
    return 0


if __name__ == "__main__":
    sys.exit(main())
