"""
Postprocess Lambda (Store step).

Takes summaries from the previous Step Functions state and persists metadata to
DynamoDB / S3. For the PoC we simply write the summary record to DynamoDB and
optionally archive the raw article body in S3.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from decimal import Decimal
from typing import Any, Dict

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from backend.lambdas.shared.cloudflare import (
    CloudflareIntegrationError,
    call_cloudflare_ai,
    resolve_api_token,
)
from backend.lambdas.shared.url import ensure_source_link


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

TABLE_NAME = os.getenv("SUMMARY_TABLE_NAME", "")
RAW_BUCKET = os.getenv("RAW_BUCKET_NAME")
ENABLE_TITLE_TRANSLATION = os.getenv("ENABLE_TITLE_TRANSLATION", "true").lower() == "true"
ENABLE_SUMMARY_TRANSLATION = os.getenv("ENABLE_SUMMARY_TRANSLATION", "true").lower() == "true"
TRANSLATE_REGION = os.getenv("TRANSLATE_REGION") or os.getenv("AWS_REGION")
DETAIL_TTL_SECONDS = int(os.getenv("DETAIL_TTL_SECONDS", "43200"))
SUMMARY_TTL_SECONDS = int(os.getenv("SUMMARY_TTL_SECONDS", "172800"))
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_API_TOKEN_SECRET_NAME = os.getenv("CLOUDFLARE_API_TOKEN_SECRET_NAME", "")
CLOUDFLARE_TRANSLATE_MODEL_ID = os.getenv("CLOUDFLARE_TRANSLATE_MODEL_ID", "@cf/meta/m2m100-1.2b")
CLOUDFLARE_TRANSLATE_TIMEOUT_SECONDS = float(os.getenv("CLOUDFLARE_TRANSLATE_TIMEOUT_SECONDS", "20"))
CLOUDFLARE_TRANSLATE_SOURCE_LANG = os.getenv("CLOUDFLARE_TRANSLATE_SOURCE_LANG", "auto")
SUMMARY_FALLBACK_MESSAGE = "本文から要約を生成できませんでした。"

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
secrets_manager = boto3.client("secretsmanager", region_name=TRANSLATE_REGION or os.getenv("AWS_REGION"))

_JP_CHAR_PATTERN = re.compile(r"[\u3040-\u30ff\u4e00-\u9faf]")


def _get_cloudflare_api_token() -> str | None:
    try:
        return resolve_api_token(
            inline_token=CLOUDFLARE_API_TOKEN,
            secret_name=CLOUDFLARE_API_TOKEN_SECRET_NAME,
            secrets_manager_client=secrets_manager,
        )
    except CloudflareIntegrationError as exc:
        LOGGER.warning("Failed to resolve Cloudflare token: %s", exc)
        return None


def _translate_with_cloudflare(text: str) -> str | None:
    if not CLOUDFLARE_ACCOUNT_ID:
        return None

    token = _get_cloudflare_api_token()
    if not token:
        return None

    original = text.strip()
    payload: Dict[str, Any] = {
        "text": text,
        "target_lang": "ja",
    }
    source_lang = CLOUDFLARE_TRANSLATE_SOURCE_LANG.strip().lower()
    if source_lang and source_lang != "auto":
        payload["source_lang"] = CLOUDFLARE_TRANSLATE_SOURCE_LANG

    try:
        data = call_cloudflare_ai(
            account_id=CLOUDFLARE_ACCOUNT_ID,
            model_id=CLOUDFLARE_TRANSLATE_MODEL_ID,
            token=token,
            payload=payload,
            timeout_seconds=CLOUDFLARE_TRANSLATE_TIMEOUT_SECONDS,
        )
    except CloudflareIntegrationError as exc:
        LOGGER.warning("Cloudflare translation request failed: %s", exc)
        return None

    result = data.get("result")
    if isinstance(result, dict):
        candidates = [
            result.get("translated_text"),
            result.get("translation"),
            result.get("response"),
            result.get("output_text"),
            result.get("text"),
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                cleaned = candidate.strip()
                if cleaned and cleaned != original:
                    return cleaned

        translations = result.get("translations")
        if isinstance(translations, list):
            for entry in translations:
                if isinstance(entry, dict):
                    candidate = entry.get("translation") or entry.get("text")
                    if isinstance(candidate, str) and candidate.strip():
                        cleaned = candidate.strip()
                        if cleaned and cleaned != original:
                            return cleaned
    elif isinstance(result, str) and result.strip():
        cleaned = result.strip()
        if cleaned != original:
            return cleaned

    LOGGER.warning("Cloudflare translation succeeded but no translated text found")
    return None


def _contains_japanese(text: str) -> bool:
    return bool(_JP_CHAR_PATTERN.search(text))


def _extract_japanese_text(value: str) -> str:
    """
    Keep only Japanese-containing segments and drop any leading non-Japanese characters.
    If no Japanese is found, return an empty string so callers can decide how to fallback.
    """
    if not value:
        return ""

    segments: list[str] = []
    for raw_line in value.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = _JP_CHAR_PATTERN.search(stripped)
        if not match:
            continue
        cleaned = stripped[match.start() :].strip()
        if cleaned:
            segments.append(cleaned)
    if segments:
        return "\n".join(segments).strip()

    match = _JP_CHAR_PATTERN.search(value)
    if match:
        return value[match.start() :].strip()
    return ""


def _translate_headline(title: str | None) -> str | None:
    if not ENABLE_TITLE_TRANSLATION:
        return None
    if not title:
        return None
    if _contains_japanese(title):
        return title

    translated = _translate_with_cloudflare(title)
    if translated:
        cleaned = translated.strip()
        japanese_only = _extract_japanese_text(cleaned)
        if japanese_only:
            return japanese_only
        if cleaned and cleaned != title.strip() and _contains_japanese(cleaned):
            return cleaned
    return None


def _translate_text_to_japanese(text: str | None) -> str | None:
    if not ENABLE_SUMMARY_TRANSLATION:
        return None
    if not text:
        return None

    original = text.strip()
    if not original:
        return None
    if _contains_japanese(original):
        return None

    translated = _translate_with_cloudflare(original)
    if translated:
        cleaned = translated.strip()
        japanese_only = _extract_japanese_text(cleaned)
        if japanese_only:
            return japanese_only
        if cleaned and cleaned != original and _contains_japanese(cleaned):
            return cleaned
    return None


def _truncate_title(title: str, max_length: int = 120) -> str:
    clean_title = (title or "").strip()
    if len(clean_title) <= max_length:
        return clean_title
    return clean_title[: max_length - 1].rstrip() + "…"


def _sanitize_for_dynamodb(value: Any) -> Any:
    """
    Recursively convert floats to Decimal for DynamoDB compatibility.
    DynamoDB disallows native float so we coerce via string to preserve precision.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _sanitize_for_dynamodb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_dynamodb(v) for v in value]
    return value


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_existing_item(table, source_id: str, item_id: str) -> Dict[str, Any]:
    try:
        response = table.get_item(
            Key={
                "pk": f"SOURCE#{source_id}",
                "sk": f"ITEM#{item_id}",
            }
        )
        return response.get("Item") or {}
    except (ClientError, BotoCoreError) as exc:
        LOGGER.debug("Failed to load existing summary item for merge: %s", exc)
        return {}


def _resolve_detail_context(payload: Dict[str, Any]) -> tuple[bool, int | None, str]:
    request_context = payload.get("request_context") or {}
    reason = (request_context.get("reason") or "").lower()
    requested_at = _coerce_int(request_context.get("requested_at"))
    has_detail_flag = bool(payload.get("generate_detailed_summary"))
    is_detail_reason = reason in {"detail", "on_demand_summary", "manual_detail"}
    is_detail_invocation = has_detail_flag or (is_detail_reason and requested_at is not None)
    return is_detail_invocation, requested_at, reason


def _prepare_summary_payload(
    payload: Dict[str, Any],
    existing_item: Dict[str, Any],
    is_detail_invocation: bool,
) -> tuple[Dict[str, Any], str]:
    existing_summaries = existing_item.get("summaries") or {}
    existing_summary_long = (existing_summaries.get("summary_long") or "").strip()
    existing_status = existing_item.get("detail_status")

    summaries_payload = dict(payload.get("summaries") or {})
    raw_summary_original = (summaries_payload.get("summary_long") or "").strip()
    translated_summary = _translate_text_to_japanese(raw_summary_original)
    if translated_summary:
        summaries_payload["summary_long"] = translated_summary
    elif raw_summary_original:
        filtered_summary = _extract_japanese_text(raw_summary_original)
        if filtered_summary:
            summaries_payload["summary_long"] = filtered_summary
        elif not _contains_japanese(raw_summary_original):
            summaries_payload["summary_long"] = SUMMARY_FALLBACK_MESSAGE

    summaries_for_store: Dict[str, Any] = dict(summaries_payload)

    summary_long_value = (summaries_for_store.get("summary_long") or "").strip()
    if summary_long_value:
        filtered_summary_long = _extract_japanese_text(summary_long_value)
        if filtered_summary_long:
            summary_long_value = filtered_summary_long
            summaries_for_store["summary_long"] = filtered_summary_long
        elif not _contains_japanese(summary_long_value):
            summary_long_value = SUMMARY_FALLBACK_MESSAGE
            summaries_for_store["summary_long"] = SUMMARY_FALLBACK_MESSAGE

    if not is_detail_invocation:
        if existing_status in {"ready", "stale"} and existing_summary_long:
            summaries_for_store["summary_long"] = existing_summary_long
            summary_long_value = existing_summary_long
        else:
            summary_long_value = ""
            summaries_for_store.pop("summary_long", None)

    return summaries_for_store, summary_long_value


def _build_summary_item(
    *,
    payload: Dict[str, Any],
    existing_item: Dict[str, Any],
    summaries_for_store: Dict[str, Any],
    detail_ready: bool,
    requested_at: int | None,
    processed_link: str | None,
    headline_translated: str | None,
    now: int,
) -> Dict[str, Any]:
    existing_status = existing_item.get("detail_status")
    existing_ready_at = _coerce_int(existing_item.get("detail_ready_at"))
    existing_expires_at = _coerce_int(existing_item.get("detail_expires_at"))
    existing_created_at = _coerce_int(existing_item.get("created_at"))
    truncated_title = _truncate_title(payload["item"]["title"])

    item_created_at = existing_created_at if existing_created_at else now
    item: Dict[str, Any] = {
        "pk": f"SOURCE#{payload['source']['id']}",
        "sk": f"ITEM#{payload['item']['id']}",
        "title": truncated_title,
        "link": processed_link or payload["item"]["link"],
        "summaries": summaries_for_store,
        "metrics": payload.get("metrics", {}),
        "created_at": item_created_at,
        "updated_at": now,
    }

    published_at = payload["item"].get("published_at")
    if published_at:
        item["published_at"] = published_at
    if SUMMARY_TTL_SECONDS > 0:
        item["expires_at"] = now + SUMMARY_TTL_SECONDS

    if headline_translated:
        item["headline_translated"] = headline_translated
    else:
        summaries = payload["summaries"]
        summary_brief = (summaries.get("summary_long") or "").strip()
        if _contains_japanese(summary_brief):
            item["headline_translated"] = _truncate_title(summary_brief, 90)

    if detail_ready:
        item["detail_status"] = "ready"
        item["detail_ready_at"] = now
        if DETAIL_TTL_SECONDS > 0:
            item["detail_expires_at"] = now + DETAIL_TTL_SECONDS
    else:
        if existing_status == "ready" and existing_ready_at:
            item["detail_status"] = "ready"
            item["detail_ready_at"] = existing_ready_at
            if existing_expires_at:
                item["detail_expires_at"] = existing_expires_at
        else:
            item["detail_status"] = "partial"

    if requested_at is not None:
        item["detail_requested_at"] = requested_at

    return item


def put_summary(payload: Dict[str, Any]) -> None:
    if not TABLE_NAME:
        raise RuntimeError("SUMMARY_TABLE_NAME must be configured")
    table = dynamodb.Table(TABLE_NAME)
    source_id = payload["source"]["id"]
    item_id = payload["item"]["id"]
    existing_item = _load_existing_item(table, source_id, item_id)
    is_detail_invocation, requested_at, _reason = _resolve_detail_context(payload)
    now = int(time.time())

    processed_link = ensure_source_link(payload["source"]["id"], payload["item"]["link"])
    if processed_link:
        payload["item"]["link"] = processed_link

    summaries_for_store, summary_long_value = _prepare_summary_payload(
        payload,
        existing_item,
        is_detail_invocation,
    )
    payload["summaries"] = dict(summaries_for_store)

    detail_ready = is_detail_invocation and summary_long_value != ""
    item = _build_summary_item(
        payload=payload,
        existing_item=existing_item,
        summaries_for_store=summaries_for_store,
        detail_ready=detail_ready,
        requested_at=requested_at,
        processed_link=processed_link,
        headline_translated=_translate_headline(payload["item"]["title"]),
        now=now,
    )
    table.put_item(Item=_sanitize_for_dynamodb(item))

    if detail_ready:
        LOGGER.debug(
            "Detailed summary persisted for source=%s item=%s", payload['source']['id'], payload['item']['id']
        )


def archive_raw_body(payload: Dict[str, Any]) -> str | None:
    """Optionally upload the raw article to S3 for auditing."""
    if not RAW_BUCKET or "article_body" not in payload:
        return None
    key = f"raw/{payload['source']['id']}/{payload['item']['id']}.txt"
    try:
        s3_client.put_object(
            Bucket=RAW_BUCKET,
            Key=key,
            Body=payload["article_body"].encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
    except (ClientError, BotoCoreError) as exc:
        LOGGER.warning("Failed to archive raw body: %s", exc)
        return None
    return key


def handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    LOGGER.info("Persisting summary for item id=%s", event["item"].get("id"))
    archive_key = archive_raw_body(event)
    put_summary(event)
    return {
        "status": "stored",
        "summary_table": TABLE_NAME,
        "raw_archive_key": archive_key,
        "input": {k: v for k, v in event.items() if k != "article_body"},
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    if isinstance(event, str):
        event = json.loads(event)
    return handle(event, context)
