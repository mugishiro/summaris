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
from typing import Any, Dict, Iterable, List, Tuple

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

lambda_client = boto3.client("lambda")


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


def _run_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = payload
    for step_name, function_arn in STEP_DEFINITIONS:
        LOGGER.info("Executing %s step for item=%s", step_name, (current.get("item") or {}).get("id"))
        current = _invoke_lambda(function_arn, current)
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
