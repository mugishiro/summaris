"""Pipeline worker Lambda.

This function orchestrates the end-to-end processing for a single news item.
It can be invoked directly (Pipeline Step Functions, Content API) or via SQS
events emitted by the dispatcher. The worker sequentially invokes the existing
functional Lambdas (collector → preprocessor → summarizer → postprocess) and
returns the final payload.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


def _env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


STEP_DEFINITIONS: Tuple[Tuple[str, str], ...] = (
    ("collector", _env("COLLECTOR_LAMBDA_ARN")),
    ("preprocessor", _env("PREPROCESSOR_LAMBDA_ARN")),
    ("summarizer", _env("SUMMARIZER_LAMBDA_ARN")),
    ("postprocess", _env("STORE_LAMBDA_ARN")),
)

SUMMARY_TABLE_NAME = (os.getenv("SUMMARY_TABLE_NAME") or "").strip()
ALERT_TOPIC_ARN = (os.getenv("ALERT_TOPIC_ARN") or "").strip()

lambda_client = boto3.client("lambda")
dynamodb = boto3.resource("dynamodb") if SUMMARY_TABLE_NAME else None
sns_client = boto3.client("sns") if ALERT_TOPIC_ARN else None


def _invoke_lambda(function_arn: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a pipeline Lambda synchronously and parse the JSON response."""
    try:
        response = lambda_client.invoke(
            FunctionName=function_arn,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
    except (ClientError, BotoCoreError) as exc:
        LOGGER.error("Failed to invoke Lambda %s: %s", function_arn, exc)
        raise

    function_error = response.get("FunctionError")
    raw_payload = response.get("Payload")
    body = raw_payload.read() if raw_payload else b""

    if function_error:
        message = body.decode("utf-8", errors="replace")[:512]
        LOGGER.error("Lambda %s reported an error: %s", function_arn, message)
        raise RuntimeError(f"Lambda {function_arn} failed: {message}")

    if not body:
        return {}

    decoded = body.decode("utf-8", errors="replace")
    try:
        result = json.loads(decoded)
    except json.JSONDecodeError:
        LOGGER.warning("Lambda %s returned non-JSON payload: %s", function_arn, decoded[:200])
        raise RuntimeError(f"Lambda {function_arn} returned non-JSON payload")

    # Some handlers may return JSON stringified twice; unwrap if needed.
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            LOGGER.warning("Lambda %s returned string result that is not JSON: %s", function_arn, result[:200])
            raise RuntimeError(f"Lambda {function_arn} returned unsupported payload format")
    if not isinstance(result, dict):
        raise RuntimeError(f"Lambda {function_arn} returned unexpected payload type: {type(result).__name__}")

    return result


def _is_detail_request(payload: Dict[str, Any]) -> bool:
    request_context = payload.get("request_context") or {}
    reason = (request_context.get("reason") or "").lower()
    if payload.get("generate_detailed_summary"):
        return True
    return reason in {"detail", "on_demand_summary", "manual_detail"}


def _detail_item_key(payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
    source = (payload.get("source") or {}).get("id")
    item = (payload.get("item") or {}).get("id")
    if not source or not item:
        return None
    return {"pk": f"SOURCE#{source}", "sk": f"ITEM#{item}"}


def _mark_detail_failure(payload: Dict[str, Any], reason: str) -> bool:
    if not SUMMARY_TABLE_NAME or not dynamodb:
        LOGGER.debug("Detail failure occurred but SUMMARY_TABLE_NAME is not configured")
        return False
    key = _detail_item_key(payload)
    if not key:
        LOGGER.warning("Unable to resolve DynamoDB key for detail failure notification")
        return False

    table = dynamodb.Table(SUMMARY_TABLE_NAME)
    now = int(time.time())
    try:
        table.update_item(
            Key=key,
            UpdateExpression=(
                "SET #detail_status = :failed, detail_failed_at = :failed_at, detail_failure_reason = :reason"
            ),
            ExpressionAttributeNames={"#detail_status": "detail_status"},
            ExpressionAttributeValues={
                ":failed": "failed",
                ":failed_at": now,
                ":reason": reason[:500],
            },
        )
        return True
    except (ClientError, BotoCoreError) as exc:
        LOGGER.warning("Failed to update detail failure status: %s", exc)
        return False


def _publish_alert(message: str, *, subject: str = "Detail generation failure") -> None:
    if not ALERT_TOPIC_ARN or not sns_client:
        return
    try:
        sns_client.publish(
            TopicArn=ALERT_TOPIC_ARN,
            Subject=subject[:100],
            Message=message,
        )
    except (ClientError, BotoCoreError) as exc:
        LOGGER.warning("Failed to publish failure alert: %s", exc)


def _handle_pipeline_failure(
    payload: Dict[str, Any],
    step_name: str,
    error: Exception,
    *,
    detail_request: bool,
) -> None:
    LOGGER.error("%s step failed for item=%s: %s", step_name, (payload.get("item") or {}).get("id"), error)
    if not detail_request:
        return
    reason = f"{step_name} failed: {error}"
    updated = _mark_detail_failure(payload, reason)
    message = (
        f"Detail generation failed at {step_name} for source={ (payload.get('source') or {}).get('id') } "
        f"item={ (payload.get('item') or {}).get('id') }: {error}"
    )
    if not updated:
        LOGGER.warning("Detail failure alert could not update DynamoDB record")
    _publish_alert(message)


def _run_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = payload
    detail_request = _is_detail_request(payload)
    for step_name, function_arn in STEP_DEFINITIONS:
        LOGGER.info("Executing %s step for item=%s", step_name, (current.get("item") or {}).get("id"))
        try:
            current = _invoke_lambda(function_arn, current)
        except Exception as exc:  # pylint: disable=broad-except
            _handle_pipeline_failure(payload, step_name, exc, detail_request=detail_request)
            raise
    return current


def _process_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for record in records:
        body = record.get("body")
        if not body:
            LOGGER.warning("Skipping SQS record without body")
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            LOGGER.warning("Skipping SQS record with invalid JSON body: %s", body[:200])
            continue
        result = _run_pipeline(payload)
        results.append(
            {
                "message_id": record.get("messageId"),
                "result": result,
            }
        )
    return results


def handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except json.JSONDecodeError:
            LOGGER.error("Received string event that is not valid JSON")
            raise

    if isinstance(event, dict) and "Records" in event:
        records = event.get("Records") or []
        results = _process_records(records)
        return {
            "processed": len(results),
            "results": results,
        }

    if not isinstance(event, dict):
        raise RuntimeError("Event payload must be a JSON object")

    return _run_pipeline(event)


def lambda_handler(event: Any, context: Any) -> Dict[str, Any]:
    return handle(event, context)
