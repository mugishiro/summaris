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
import requests
from requests.exceptions import RequestException

from shared.url import ensure_source_link


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

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
secrets_manager = boto3.client("secretsmanager", region_name=TRANSLATE_REGION or os.getenv("AWS_REGION"))
_cloudflare_api_token_cache: str | None = None

_JP_CHAR_PATTERN = re.compile(r"[\u3040-\u30ff\u4e00-\u9faf]")


def _resolve_cloudflare_api_token() -> str | None:
    """Resolve Cloudflare API token from env or Secrets Manager."""
    global _cloudflare_api_token_cache

    if _cloudflare_api_token_cache:
        return _cloudflare_api_token_cache

    token = (CLOUDFLARE_API_TOKEN or "").strip()
    if token:
        _cloudflare_api_token_cache = token
        return token

    if CLOUDFLARE_API_TOKEN_SECRET_NAME:
        try:
            response = secrets_manager.get_secret_value(SecretId=CLOUDFLARE_API_TOKEN_SECRET_NAME)
        except (ClientError, BotoCoreError) as exc:
            LOGGER.warning("Failed to load Cloudflare API token secret: %s", exc)
            return None
        secret_string = (response.get("SecretString") or "").strip()
        if secret_string:
            if secret_string.startswith("{"):
                try:
                    parsed = json.loads(secret_string)
                except json.JSONDecodeError:
                    parsed = {}
                else:
                    candidate = parsed.get("api_token") or parsed.get("token")
                    if isinstance(candidate, str) and candidate.strip():
                        secret_string = candidate.strip()
        if secret_string:
            _cloudflare_api_token_cache = secret_string
            return secret_string

    return None


def _translate_with_cloudflare(text: str) -> str | None:
    if not CLOUDFLARE_ACCOUNT_ID:
        return None

    token = _resolve_cloudflare_api_token()
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

    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CLOUDFLARE_TRANSLATE_MODEL_ID}"
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=CLOUDFLARE_TRANSLATE_TIMEOUT_SECONDS,
        )
    except RequestException as exc:
        LOGGER.warning("Cloudflare translation request failed: %s", exc)
        return None

    if response.status_code >= 400:
        LOGGER.warning("Cloudflare translation HTTP %s: %s", response.status_code, response.text[:200])
        return None

    try:
        data = response.json()
    except ValueError as exc:
        LOGGER.warning("Cloudflare translation returned non-JSON payload: %s", exc)
        return None

    if not data.get("success", True):
        LOGGER.warning("Cloudflare translation API error: %s", data.get("errors"))
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


def _translate_headline(title: str | None) -> str | None:
    if not ENABLE_TITLE_TRANSLATION:
        return None
    if not title:
        return None
    if _contains_japanese(title):
        return title

    translated = _translate_with_cloudflare(title)
    if translated and translated.strip() and translated.strip() != title.strip():
        return translated.strip()
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


def put_summary(payload: Dict[str, Any]) -> None:
    if not TABLE_NAME:
        raise RuntimeError("SUMMARY_TABLE_NAME must be configured")
    table = dynamodb.Table(TABLE_NAME)
    headline_translated = _translate_headline(payload["item"]["title"])
    request_context = payload.get("request_context") or {}
    reason = (request_context.get("reason") or "").lower()
    requested_at = _coerce_int(request_context.get("requested_at"))
    has_detail_flag = bool(payload.get("generate_detailed_summary"))
    is_detail_reason = reason in {"detail", "on_demand_summary", "manual_detail"}
    is_detail_invocation = has_detail_flag or (is_detail_reason and requested_at is not None)
    now = int(time.time())

    existing_item: Dict[str, Any] = {}
    try:
        response = table.get_item(
            Key={
                "pk": f"SOURCE#{payload['source']['id']}",
                "sk": f"ITEM#{payload['item']['id']}",
            }
        )
        existing_item = response.get("Item") or {}
    except (ClientError, BotoCoreError) as exc:
        LOGGER.debug("Failed to load existing summary item for merge: %s", exc)
    truncated_title = _truncate_title(payload["item"]["title"])

    processed_link = ensure_source_link(payload["source"]["id"], payload["item"]["link"])
    if processed_link:
        payload["item"]["link"] = processed_link

    existing_created_at = _coerce_int(existing_item.get("created_at"))

    summaries_payload = dict(payload.get("summaries") or {})
    translated_summary = _translate_text_to_japanese(summaries_payload.get("summary_long"))
    if translated_summary:
        summaries_payload["summary_long"] = translated_summary
    payload["summaries"] = summaries_payload
    summaries_for_store: Dict[str, Any] = dict(summaries_payload)

    summary_long_value = (summaries_for_store.get("summary_long") or "").strip()
    if not is_detail_invocation:
        summary_long_value = ""
        summaries_for_store.pop("summary_long", None)
        summaries_for_store.pop("diff_points", None)

    item = {
        "pk": f"SOURCE#{payload['source']['id']}",
        "sk": f"ITEM#{payload['item']['id']}",
        "title": truncated_title,
        "link": processed_link or payload["item"]["link"],
        "summaries": summaries_for_store,
        "metrics": payload.get("metrics", {}),
    }
    item_created_at = existing_created_at if existing_created_at else now
    item["created_at"] = item_created_at
    item["updated_at"] = now
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

    detail_ready = is_detail_invocation and summary_long_value != ""
    if detail_ready:
        item["detail_status"] = "ready"
        item["detail_ready_at"] = now
        if DETAIL_TTL_SECONDS > 0:
            item["detail_expires_at"] = now + DETAIL_TTL_SECONDS
    else:
        existing_status = existing_item.get("detail_status")
        existing_ready_at = _coerce_int(existing_item.get("detail_ready_at"))
        existing_expires_at = _coerce_int(existing_item.get("detail_expires_at"))
        if existing_status == "ready" and existing_ready_at:
            item["detail_status"] = "ready"
            item["detail_ready_at"] = existing_ready_at
            if existing_expires_at:
                item["detail_expires_at"] = existing_expires_at
        else:
            item["detail_status"] = "partial"

    if requested_at is not None:
        item["detail_requested_at"] = requested_at

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
