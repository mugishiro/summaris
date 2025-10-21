"""
Lightweight update checker Lambda.

Receives a source item, performs a HEAD request to capture ETag / Last-Modified,
and stores the metadata in DynamoDB. Returns a flag indicating whether the
downstream collector should fetch the article body (based on changes or staleness).
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from botocore.config import Config


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

USER_AGENT = os.getenv("CHECKER_USER_AGENT", "news-summary-checker/0.1")
SOURCE_STATUS_TABLE = os.getenv("SOURCE_STATUS_TABLE", "")
DEFAULT_THRESHOLD_SECONDS = int(os.getenv("CHECKER_DEFAULT_THRESHOLD_SECONDS", "3600"))
TIMEOUT_SECONDS = float(os.getenv("CHECKER_HTTP_TIMEOUT_SECONDS", "10"))
SOURCE_STATUS_TTL_SECONDS = int(os.getenv("SOURCE_STATUS_TTL_SECONDS", "172800"))

dynamodb = boto3.resource("dynamodb")
session = boto3.session.Session()

http_config = Config(connect_timeout=TIMEOUT_SECONDS, read_timeout=TIMEOUT_SECONDS)


@dataclass
class SourceMetadata:
    source_id: str
    name: str
    url: str
    threshold_seconds: int
    force_fetch: bool

    @classmethod
    def from_event(cls, event: Dict[str, Any]) -> "SourceMetadata":
        source = event.get("source") or {}
        endpoint = event.get("endpoint") or {}

        source_id = source.get("id")
        explicit_url = endpoint.get("url") if isinstance(endpoint, dict) else None
        fallback_url = None
        if isinstance(source.get("endpoint"), dict):
            fallback_url = source["endpoint"].get("url")
        if not fallback_url and isinstance(source.get("urls"), list):
            fallback_url = source["urls"][0] if source["urls"] else None
        if not fallback_url:
            fallback_url = source.get("url")

        url = explicit_url or fallback_url

        if not source_id or not url:
            raise ValueError("Event must include source.id and endpoint.url")

        threshold = int(event.get("threshold_seconds") or DEFAULT_THRESHOLD_SECONDS)
        force = bool(event.get("force_fetch", False))
        return cls(
            source_id=str(source_id),
            name=str(source.get("name", source.get("id", ""))),
            url=str(url),
            threshold_seconds=threshold,
            force_fetch=force,
        )


def _table():
    if not SOURCE_STATUS_TABLE:
        raise RuntimeError("SOURCE_STATUS_TABLE environment variable must be set")
    return dynamodb.Table(SOURCE_STATUS_TABLE)


def _perform_head(url: str) -> Dict[str, Optional[str]]:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            return {
                "etag": headers.get("etag"),
                "last_modified": headers.get("last-modified"),
                "status": response.status,
            }
    except urllib.error.HTTPError as exc:
        LOGGER.warning("HEAD request returned HTTP %s for %s", exc.code, url)
        return {
            "etag": None,
            "last_modified": None,
            "status": exc.code,
        }
    except urllib.error.URLError as exc:  # covers timeout/socket errors
        LOGGER.warning("HEAD request failed for %s: %s", url, exc)
        raise


def _load_existing_record(metadata: SourceMetadata) -> Dict[str, Any] | None:
    try:
        response = _table().get_item(
            Key={
                "pk": f"SOURCE#{metadata.source_id}",
                "sk": f"URL#{metadata.url}",
            }
        )
    except (ClientError, BotoCoreError) as exc:
        LOGGER.error("Failed to read source metadata: %s", exc)
        raise
    return response.get("Item")


def _should_fetch(existing: Dict[str, Any] | None, head: Dict[str, Optional[str]], metadata: SourceMetadata) -> bool:
    if metadata.force_fetch:
        return True
    if existing is None:
        return True

    now = int(time.time())
    last_checked = int(existing.get("checked_at", 0))
    if now - last_checked >= metadata.threshold_seconds:
        return True

    existing_etag = existing.get("etag")
    existing_last_modified = existing.get("last_modified")
    if head.get("etag") and head.get("etag") != existing_etag:
        return True
    if head.get("last_modified") and head.get("last_modified") != existing_last_modified:
        return True
    return False


def _persist(metadata: SourceMetadata, head: Dict[str, Optional[str]]) -> None:
    Item = {
        "pk": f"SOURCE#{metadata.source_id}",
        "sk": f"URL#{metadata.url}",
        "source_id": metadata.source_id,
        "source_name": metadata.name,
        "url": metadata.url,
        "etag": head.get("etag"),
        "last_modified": head.get("last_modified"),
        "status": head.get("status"),
        "checked_at": int(time.time()),
        "threshold_seconds": metadata.threshold_seconds,
    }
    if SOURCE_STATUS_TTL_SECONDS > 0:
        Item["expires_at"] = int(time.time()) + SOURCE_STATUS_TTL_SECONDS
    try:
        _table().put_item(Item=Item)
    except (ClientError, BotoCoreError) as exc:
        LOGGER.error("Failed to persist source metadata: %s", exc)
        raise


def handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    metadata = SourceMetadata.from_event(event)
    LOGGER.info("Checking source %s url=%s", metadata.source_id, metadata.url)

    existing = _load_existing_record(metadata)
    head = _perform_head(metadata.url)

    should_fetch = _should_fetch(existing, head, metadata)
    _persist(metadata, head)

    payload = {
        "source": {
            "id": metadata.source_id,
            "name": metadata.name,
        },
        "endpoint": {
            "url": metadata.url,
        },
        "metadata": head,
        "should_fetch": should_fetch,
        "threshold_seconds": metadata.threshold_seconds,
    }

    if should_fetch:
        payload["enqueue"] = True

    return payload


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    if isinstance(event, str):
        event = json.loads(event)
    return handle(event, context)
