"""
Content API Lambda.

Exposes lightweight REST endpoints for cluster summaries:
- GET /clusters
- GET /clusters/{id}

This function is intended to run behind an API Gateway HTTP API using the
payload format version 2.0. Responses include CORS headers so that they can
be consumed from the Amplify/CloudFront hosted frontend.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import BotoCoreError, ClientError

from shared.url import ensure_source_link

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def _safe_int_env(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        LOGGER.warning("Invalid integer for %s=%s; using default %s", key, value, default)
        return default


SUMMARY_TABLE_NAME = os.getenv("SUMMARY_TABLE_NAME", "")
DEFAULT_LIMIT = _safe_int_env("API_CLUSTER_LIMIT", 0)  # 0 or negative => unlimited
DETAIL_TTL_SECONDS = _safe_int_env("DETAIL_TTL_SECONDS", 43200)
DETAIL_PENDING_TIMEOUT_SECONDS = _safe_int_env("DETAIL_PENDING_TIMEOUT_SECONDS", 900)

DYNAMODB = boto3.resource("dynamodb")
WORKER_LAMBDA_ARN = os.getenv("WORKER_LAMBDA_ARN", "")
LAMBDA_CLIENT = boto3.client("lambda") if WORKER_LAMBDA_ARN else None

SOURCE_CATALOG: Dict[str, Dict[str, Any]] = {
    "nhk-news": {
        "id": "nhk-news",
        "name": "NHK News",
        "url": "https://www3.nhk.or.jp/news/",
        "feed_url": "https://www3.nhk.or.jp/rss/news/cat0.xml",
        "default_topics": ["国内", "社会"],
    },
    "bbc-world": {
        "id": "bbc-world",
        "name": "BBC World News",
        "url": "https://www.bbc.com/news/world",
        "feed_url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "default_topics": ["国際", "世界"],
    },
    "al-jazeera-english": {
        "id": "al-jazeera-english",
        "name": "Al Jazeera English",
        "url": "https://www.aljazeera.com/",
        "feed_url": "https://www.aljazeera.com/xml/rss/all.xml",
        "default_topics": ["国際", "中東"],
    },
    "dw-world": {
        "id": "dw-world",
        "name": "Deutsche Welle World",
        "url": "https://www.dw.com/en/world",
        "feed_url": "https://rss.dw.com/rdf/rss-en-world",
        "default_topics": ["国際", "ヨーロッパ"],
    },
    "el-pais": {
        "id": "el-pais",
        "name": "EL PAÍS",
        "url": "https://elpais.com/",
        "feed_url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
        "default_topics": ["国際", "スペイン"],
    },
    "straits-times": {
        "id": "straits-times",
        "name": "The Straits Times",
        "url": "https://www.straitstimes.com/news/world",
        "feed_url": "https://www.straitstimes.com/news/world/rss.xml",
        "default_topics": ["国際", "アジア"],
    },
    "times-of-india": {
        "id": "times-of-india",
        "name": "The Times of India",
        "url": "https://timesofindia.indiatimes.com/",
        "feed_url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "default_topics": ["国際", "インド"],
    },
    "allafrica-latest": {
        "id": "allafrica-latest",
        "name": "AllAfrica Latest",
        "url": "https://allafrica.com/latest/",
        "feed_url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
        "default_topics": ["国際", "アフリカ"],
    },
}

MOCK_SUMMARY_FALLBACK = "本文から要約を取得できませんでした。"


def _table():
    if not SUMMARY_TABLE_NAME:
        raise RuntimeError("SUMMARY_TABLE_NAME environment variable must be set")
    return DYNAMODB.Table(SUMMARY_TABLE_NAME)


def _normalise_id(value: Optional[str], prefix: str) -> str:
    if not value:
        return ""
    return value[len(prefix) :] if value.startswith(prefix) else value


def _get_source_metadata(source_id: str) -> Dict[str, Any]:
    metadata = SOURCE_CATALOG.get(source_id)
    if metadata:
        return metadata

    readable = source_id.replace("-", " ").replace("_", " ").title()
    return {
        "id": source_id,
        "name": readable,
        "url": "",
        "feed_url": None,
        "default_topics": ["general"],
    }


def _derive_summary_long(summaries: Dict[str, Any]) -> str:
    if not summaries:
        return ""
    for key in ("summary_long", "summary"):
        value = summaries.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _derive_diff_points(summaries: Dict[str, Any]) -> List[str]:
    if not summaries:
        return []
    points = summaries.get("diff_points")
    if not isinstance(points, list):
        return []
    result = []
    for point in points:
        text = str(point).strip()
        if text:
            result.append(text)
    return result


def _clean_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    text = str(value).strip()
    return text or None


def _detect_languages(summary: str) -> Optional[List[str]]:
    if not summary:
        return None
    has_japanese = any("\u3040" <= char <= "\u30ff" or "\u4e00" <= char <= "\u9faf" for char in summary)
    has_latin = any("A" <= char <= "Z" or "a" <= char <= "z" for char in summary)
    languages: List[str] = []
    if has_japanese:
        languages.append("日本語")
    if has_latin:
        languages.append("英語")
    return languages or None


def _derive_importance(updated_at: float, summary_long: str, diff_points: List[str]) -> str:
    now = time.time()
    age_hours = (now - updated_at) / 3600

    if summary_long and "要約を生成できませんでした" in summary_long:
        return "low"

    if age_hours <= 6:
        return "high"
    if age_hours <= 24:
        return "medium"

    return "medium" if len(diff_points) >= 5 else "low"


def _derive_topics(source_id: str, diff_points: List[str]) -> List[str]:
    metadata = _get_source_metadata(source_id)
    return list(metadata.get("default_topics", []))


JP_TEXT_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


def _extract_japanese_lines(text: str) -> str:
    if not text:
        return ""
    segments = [segment.strip() for segment in text.splitlines() if segment.strip()]
    japanese_segments = [segment for segment in segments if JP_TEXT_RE.search(segment)]
    if japanese_segments:
        return "\n".join(japanese_segments)
    return text.strip()


def _maybe_epoch_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_epoch_seconds(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(time.time())


def _format_epoch(value: Any) -> Optional[str]:
    epoch = _maybe_epoch_seconds(value)
    if epoch is None or epoch <= 0:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _marshall_item(raw_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source_id = _normalise_id(raw_item.get("pk"), "SOURCE#")
    item_id = _normalise_id(raw_item.get("sk"), "ITEM#")
    if not source_id or not item_id:
        return None

    summaries = raw_item.get("summaries") or {}
    summary_long = _derive_summary_long(summaries)
    diff_points = _derive_diff_points(summaries)

    created_at_epoch = _to_epoch_seconds(raw_item.get("created_at"))
    updated_at_epoch = _to_epoch_seconds(raw_item.get("updated_at"))
    if updated_at_epoch == 0 and created_at_epoch != 0:
        updated_at_epoch = created_at_epoch
    if created_at_epoch == 0:
        created_at_epoch = updated_at_epoch if updated_at_epoch != 0 else int(time.time())
    if updated_at_epoch == 0:
        updated_at_epoch = created_at_epoch
    created_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created_at_epoch))
    updated_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(updated_at_epoch))

    metadata = _get_source_metadata(source_id)
    raw_article_link = raw_item.get("link")
    article_url = raw_article_link or metadata.get("url", "")
    site_url = metadata.get("url", "") or None
    adjusted_article_url = ensure_source_link(source_id, raw_article_link or article_url)
    article_href = adjusted_article_url or raw_article_link
    article_title = _clean_optional_str(raw_item.get("title")) or metadata.get("name")
    headline_translated = raw_item.get("headline_translated")
    detail_status_raw = _clean_optional_str(raw_item.get("detail_status"))
    detail_status = detail_status_raw
    expires_epoch = _maybe_epoch_seconds(raw_item.get("detail_expires_at"))
    if (
        detail_status == "ready"
        and DETAIL_TTL_SECONDS > 0
        and expires_epoch is not None
        and expires_epoch <= time.time()
    ):
        detail_status = "stale"
    detail_failure_reason = _clean_optional_str(raw_item.get("detail_failure_reason"))

    is_ready = detail_status in {"ready", "stale"}

    summary_long_ready = summary_long.strip()
    resolved_summary_long = ""
    resolved_diff_points = []
    if is_ready:
        resolved_summary_long = _extract_japanese_lines(summary_long_ready)
        resolved_diff_points = diff_points
    else:
        resolved_summary_long = ""
        resolved_diff_points = []

    return {
        "id": item_id,
        "headline": raw_item.get("title") or "(タイトル不明)",
        "summaryLong": resolved_summary_long,
        "headlineJa": headline_translated or None,
        "createdAt": created_at_iso,
        "updatedAt": updated_at_iso,
        "publishedAt": _clean_optional_str(raw_item.get("published_at")),
        "importance": _derive_importance(updated_at_epoch, resolved_summary_long, resolved_diff_points),
        "diffPoints": resolved_diff_points,
        "topics": _derive_topics(source_id, diff_points),
        "factCheckStatus": "pending" if resolved_diff_points else None,
        "languages": _detect_languages(resolved_summary_long),
        "detailStatus": detail_status,
        "detailRequestedAt": _format_epoch(raw_item.get("detail_requested_at")),
        "detailReadyAt": _format_epoch(raw_item.get("detail_ready_at")),
        "detailExpiresAt": _format_epoch(raw_item.get("detail_expires_at")),
        "detailFailedAt": _format_epoch(raw_item.get("detail_failed_at")),
        "detailFailureReason": detail_failure_reason,
        "sources": [
            {
                "id": metadata["id"],
                "name": metadata["name"],
                "url": (adjusted_article_url or article_url or site_url or ""),
                "articleUrl": article_href or None,
                "articleTitle": article_title,
                "siteUrl": site_url,
            }
        ],
    }


def _scan_clusters(limit: int) -> List[Dict[str, Any]]:
    table = _table()
    items: List[Dict[str, Any]] = []
    last_evaluated_key: Optional[Dict[str, Any]] = None
    max_items = limit if limit and limit > 0 else None

    while max_items is None or len(items) < max_items:
        scan_kwargs: Dict[str, Any] = {}
        if max_items is not None:
            remaining = max_items - len(items)
            if remaining <= 0:
                break
            scan_kwargs["Limit"] = min(50, remaining)
        if last_evaluated_key:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

        try:
            response = table.scan(**scan_kwargs)
        except (ClientError, BotoCoreError) as exc:
            LOGGER.error("Failed to scan DynamoDB: %s", exc)
            raise

        records = response.get("Items", [])
        for record in records:
            cluster = _marshall_item(record)
            if cluster:
                items.append(cluster)
            if max_items is not None and len(items) >= max_items:
                break

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    items.sort(key=lambda item: item["updatedAt"], reverse=True)
    return items


def _find_cluster_record(cluster_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    table = _table()
    last_evaluated_key: Optional[Dict[str, Any]] = None

    while True:
        scan_kwargs: Dict[str, Any] = {
            "Limit": 50,
            "FilterExpression": Attr("sk").eq(f"ITEM#{cluster_id}"),
        }
        if last_evaluated_key is not None:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

        try:
            response = table.scan(**scan_kwargs)
        except (ClientError, BotoCoreError) as exc:
            LOGGER.error("Failed to scan for cluster %s: %s", cluster_id, exc)
            raise

        for record in response.get("Items", []):
            cluster = _marshall_item(record)
            if cluster:
                return cluster, record

        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    return None, None


def _load_cluster_by_id(cluster_id: str) -> Optional[Dict[str, Any]]:
    cluster, _ = _find_cluster_record(cluster_id)
    return cluster


def _start_detail_generation(cluster: Dict[str, Any], raw_item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not LAMBDA_CLIENT or not WORKER_LAMBDA_ARN:
        LOGGER.error("Worker Lambda ARN is not configured")
        raise RuntimeError("Worker Lambda ARN is not configured")

    source_id = _normalise_id(raw_item.get("pk"), "SOURCE#")
    if not source_id:
        raise RuntimeError("Unable to determine source id for cluster detail generation")

    metadata = _get_source_metadata(source_id)
    feed_url = metadata.get("feed_url") or metadata.get("url")
    article_link = ensure_source_link(source_id, raw_item.get("link")) or raw_item.get("link") or feed_url or (cluster.get("sources") or [{}])[0].get("url")
    if not article_link:
        raise RuntimeError("Article link is required to generate detailed summary")

    table = _table()
    requested_at = int(time.time())

    try:
        table.update_item(
            Key={
                "pk": raw_item["pk"],
                "sk": raw_item["sk"],
            },
            UpdateExpression=(
                "SET #detail_status = :pending "
                "REMOVE detail_failed_at, detail_failure_reason"
            ),
            ConditionExpression="attribute_not_exists(#detail_status) OR #detail_status <> :pending",
            ExpressionAttributeNames={
                "#detail_status": "detail_status",
            },
            ExpressionAttributeValues={
                ":pending": "pending",
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            LOGGER.info("Detail generation already pending for cluster %s", cluster["id"])
            return False, None
        raise

    execution_input = {
        "source": {
            "id": source_id,
            "name": metadata.get("name", source_id),
            "endpoint": {"url": feed_url},
        },
        "endpoint": {"url": feed_url},
        "item": {
            "id": cluster["id"],
            "title": raw_item.get("title") or cluster.get("headline"),
            "link": article_link,
        },
        "request_context": {
            "reason": "detail",
            "trigger": "on_demand_summary",
            "requested_at": requested_at,
        },
        "generate_detailed_summary": True,
    }

    try:
        response = LAMBDA_CLIENT.invoke(
            FunctionName=WORKER_LAMBDA_ARN,
            InvocationType="Event",
            Payload=json.dumps(execution_input, ensure_ascii=False).encode("utf-8"),
        )
    except (ClientError, BotoCoreError) as exc:
        LOGGER.exception("Failed to invoke worker Lambda for cluster %s: %s", cluster["id"], exc)
        raise

    request_id = (response.get("ResponseMetadata") or {}).get("RequestId")
    return True, request_id


def _is_detail_expired(raw_item: Dict[str, Any]) -> bool:
    if DETAIL_TTL_SECONDS <= 0:
        return False
    expires_at = _maybe_epoch_seconds(raw_item.get("detail_expires_at"))
    if expires_at is None:
        return False
    return expires_at <= time.time()


def _mark_detail_failure(raw_item: Dict[str, Any], reason: str) -> None:
    table = _table()
    failed_at = int(time.time())
    table.update_item(
        Key={
            "pk": raw_item["pk"],
            "sk": raw_item["sk"],
        },
        UpdateExpression="SET #detail_status = :failed, detail_failed_at = :failed_at, detail_failure_reason = :reason",
        ExpressionAttributeNames={
            "#detail_status": "detail_status",
        },
        ExpressionAttributeValues={
            ":failed": "failed",
            ":failed_at": failed_at,
            ":reason": reason,
        },
    )
    raw_item["detail_status"] = "failed"
    raw_item["detail_failed_at"] = failed_at
    raw_item["detail_failure_reason"] = reason


def _response(status_code: int, body: Any) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }


def _handle_detail_request(cluster_id: str) -> Dict[str, Any]:
    try:
        cluster, record = _find_cluster_record(cluster_id)
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.exception("Failed to load cluster %s for detail request: %s", cluster_id, exc)
        return _response(500, {"message": "Failed to load cluster"})

    if not cluster or record is None:
        return _response(404, {"message": "Cluster not found"})

    summaries = record.get("summaries") or {}
    summary_long = (summaries.get("summary_long") or "").strip()
    detail_status = _clean_optional_str(record.get("detail_status"))
    now = time.time()

    if summary_long and detail_status == "ready" and not _is_detail_expired(record):
        return _response(
            200,
            {
                "status": "ready",
                "detailStatus": "ready",
                "cluster": cluster,
            },
        )

    if detail_status == "pending":
        requested_at = _maybe_epoch_seconds(record.get("detail_requested_at"))
        if (
            requested_at is not None
            and DETAIL_PENDING_TIMEOUT_SECONDS > 0
            and requested_at + DETAIL_PENDING_TIMEOUT_SECONDS <= now
        ):
            LOGGER.warning("Detail generation timed out for cluster %s; marking as failed", cluster_id)
            try:
                _mark_detail_failure(record, "timeout")
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Failed to mark detail failure for cluster %s: %s", cluster_id, exc)
                return _response(500, {"message": "Failed to update detail status"})
            detail_status = "failed"
        else:
            return _response(
                202,
                {
                    "status": "pending",
                    "detailStatus": "pending",
                    "cluster": cluster,
                },
            )

    if not WORKER_LAMBDA_ARN:
        return _response(500, {"message": "Detail generation pipeline is not configured"})

    had_existing_summary = bool(summary_long)
    try:
        started, invocation_request_id = _start_detail_generation(cluster, record)
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.exception("Failed to start detail generation for cluster %s: %s", cluster_id, exc)
        return _response(500, {"message": "Failed to start detail generation"})

    if not started:
        return _response(
            202,
            {
                "status": "pending",
                "detailStatus": "pending",
                "cluster": cluster,
            },
        )

    payload = {
        "status": "refreshing" if had_existing_summary else "started",
        "detailStatus": "pending",
        "cluster": {
            **cluster,
            "detailStatus": "pending",
        },
    }
    if invocation_request_id:
        payload["workerRequestId"] = invocation_request_id
    return _response(202, payload)


def handle(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method", "GET").upper()
    raw_path = ((event.get("requestContext") or {}).get("http") or {}).get("path") or event.get("rawPath") or "/"

    LOGGER.info("Received request method=%s path=%s", method, raw_path)

    if method not in {"GET", "POST"}:
        return _response(405, {"message": "Method not allowed"})

    path_segments = [segment for segment in raw_path.split("/") if segment]
    stage = (event.get("requestContext") or {}).get("stage")
    if stage and path_segments and path_segments[0] == stage:
        path_segments = path_segments[1:]

    if len(path_segments) == 3 and path_segments[0] == "clusters" and path_segments[2] in {"summaries", "detail"}:
        cluster_id = path_segments[1]
        if method == "POST":
            return _handle_detail_request(cluster_id)
        if method == "GET":
            cluster, _ = _find_cluster_record(cluster_id)
            if not cluster:
                return _response(404, {"message": "Cluster not found"})
            return _response(200, {"cluster": cluster})
        return _response(405, {"message": "Method not allowed"})

    if not path_segments or path_segments == ["clusters"]:
        limit_param = event.get("queryStringParameters", {}).get("limit") if event.get("queryStringParameters") else None
        try:
            limit = int(limit_param) if limit_param else DEFAULT_LIMIT
        except ValueError:
            limit = DEFAULT_LIMIT
        try:
            clusters = _scan_clusters(limit)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to load clusters: %s", exc)
            return _response(500, {"message": "Failed to load clusters"})
        return _response(200, {"clusters": clusters})

    if len(path_segments) == 2 and path_segments[0] == "clusters":
        cluster_id = path_segments[1]
        try:
            cluster = _load_cluster_by_id(cluster_id)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to load cluster %s: %s", cluster_id, exc)
            return _response(500, {"message": "Failed to load cluster"})
        if not cluster:
            return _response(404, {"message": "Cluster not found"})
        return _response(200, {"cluster": cluster})

    return _response(404, {"message": "Not Found"})


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    if isinstance(event, str):
        event = json.loads(event)
    return handle(event, context)
