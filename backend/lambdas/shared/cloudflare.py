"""
Shared helpers for calling Cloudflare Workers AI APIs.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from botocore.exceptions import BotoCoreError, ClientError
import requests
from requests import RequestException


LOGGER = logging.getLogger(__name__)

_TOKEN_CACHE: dict[str, str] = {}


class CloudflareIntegrationError(RuntimeError):
    """Raised when Cloudflare credentials or API invocations fail."""


def resolve_api_token(
    *,
    inline_token: Optional[str],
    secret_name: Optional[str],
    secrets_manager_client,
    cache_key: Optional[str] = None,
) -> str:
    """
    Resolve Cloudflare API token from inline env var or Secrets Manager, with basic caching.
    """
    key = cache_key or secret_name or inline_token or "__default__"
    cached = _TOKEN_CACHE.get(key)
    if cached:
        return cached

    token = (inline_token or "").strip()
    if token:
        _TOKEN_CACHE[key] = token
        return token

    if not secret_name:
        raise CloudflareIntegrationError("Cloudflare API token is not configured")

    try:
        response = secrets_manager_client.get_secret_value(SecretId=secret_name)
    except (ClientError, BotoCoreError) as exc:
        raise CloudflareIntegrationError(f"Failed to load Cloudflare secret: {exc}") from exc

    secret_string = (response.get("SecretString") or "").strip()
    if secret_string.startswith("{"):
        try:
            parsed = json.loads(secret_string)
        except json.JSONDecodeError:
            parsed = {}
        candidate = parsed.get("api_token") or parsed.get("token")
        if isinstance(candidate, str) and candidate.strip():
            secret_string = candidate.strip()

    if not secret_string:
        raise CloudflareIntegrationError("Cloudflare API token secret is empty")

    _TOKEN_CACHE[key] = secret_string
    return secret_string


def call_cloudflare_ai(
    *,
    account_id: str,
    model_id: str,
    token: str,
    payload: Dict[str, Any],
    timeout_seconds: float,
) -> Dict[str, Any]:
    """
    Invoke a Cloudflare Workers AI endpoint and return the parsed JSON payload.
    """
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_id}"
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout_seconds,
        )
    except RequestException as exc:
        raise CloudflareIntegrationError(f"Cloudflare request failed: {exc}") from exc

    if response.status_code >= 400:
        raise CloudflareIntegrationError(
            f"Cloudflare returned HTTP {response.status_code}: {response.text[:200]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise CloudflareIntegrationError(f"Cloudflare returned non-JSON payload: {exc}") from exc

    if not data.get("success", True):
        raise CloudflareIntegrationError(f"Cloudflare API error: {data.get('errors')}")

    return data
