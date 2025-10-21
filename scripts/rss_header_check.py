#!/usr/bin/env python3
"""
RSS header inspector.

Fetches HTTP headers for a list of RSS feed URLs and reports the presence of
ETag / Last-Modified as well as response metadata. Intended to support
development plan phase 0.3 verification.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable, List


DEFAULT_TIMEOUT = 10  # seconds


@dataclass
class FeedResult:
    url: str
    status: int | None
    etag: str | None
    last_modified: str | None
    server: str | None
    error: str | None
    duration: float


def fetch_head(url: str, timeout: int = DEFAULT_TIMEOUT) -> FeedResult:
    start = time.time()
    req = urllib.request.Request(url, method="HEAD")

    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            headers = resp.headers
            return FeedResult(
                url=url,
                status=resp.status,
                etag=headers.get("ETag"),
                last_modified=headers.get("Last-Modified"),
                server=headers.get("Server"),
                error=None,
                duration=time.time() - start,
            )
    except urllib.error.HTTPError as exc:
        return FeedResult(
            url=url,
            status=exc.code,
            etag=exc.headers.get("ETag"),
            last_modified=exc.headers.get("Last-Modified"),
            server=exc.headers.get("Server"),
            error=f"HTTPError: {exc}",
            duration=time.time() - start,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return FeedResult(
            url=url,
            status=None,
            etag=None,
            last_modified=None,
            server=None,
            error=f"{type(exc).__name__}: {exc}",
            duration=time.time() - start,
        )


def load_urls(source: Iterable[str]) -> List[str]:
    urls = []
    for line in source:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        urls.append(text)
    return urls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "urls",
        nargs="*",
        help="Feed URLs to inspect. If omitted, read from stdin (one per line).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent requests (default: 4)",
    )
    args = parser.parse_args()

    urls = args.urls or load_urls(sys.stdin)
    if not urls:
        print("No URLs provided.", file=sys.stderr)
        return 1

    results: List[FeedResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(fetch_head, url, args.timeout) for url in urls]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    header = f"{'URL':60} | {'Status':>6} | {'ETag':>20} | {'Last-Modified':>25} | {'Duration(s)':>11} | Note"
    print(header)
    print("-" * len(header))
    for res in sorted(results, key=lambda x: x.url):
        note = res.error or ""
        print(
            f"{res.url[:60]:60} | {res.status if res.status is not None else '---':>6} | "
            f"{(res.etag or '---')[:20]:>20} | {(res.last_modified or '---')[:25]:>25} | "
            f"{res.duration:11.3f} | {note}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
