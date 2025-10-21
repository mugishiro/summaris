"""
Summarizer Lambda (LLM call step).

Invoked after the collector fetches article text. This PoC skeleton prepares a
prompt and calls Bedrock Claude via boto3. Secrets (model ID, temperature, etc.)
are expected to be stored in AWS Secrets Manager.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import requests
from requests.exceptions import RequestException


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


class ConfigurationError(RuntimeError):
    """Raised when required environment settings are missing or invalid."""


class ExternalServiceError(RuntimeError):
    """Raised when downstream services return recoverable errors."""


def _get_env(key: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(key)
    if value is None or value == "":
        if required and default is None:
            raise ConfigurationError(f"Environment variable {key} must be set")
        return default if default is not None else ""
    return value


def _get_int_env(key: str, default: int | None = None, *, required: bool = False) -> int:
    value = os.getenv(key)
    if value is None:
        if required and default is None:
            raise ConfigurationError(f"Environment variable {key} must be set")
        if default is None:
            raise ConfigurationError(f"Environment variable {key} is missing and no default provided")
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {key} must be an integer") from exc


def _get_float_env(key: str, default: float | None = None, *, required: bool = False) -> float:
    value = os.getenv(key)
    if value is None:
        if required and default is None:
            raise ConfigurationError(f"Environment variable {key} must be set")
        if default is None:
            raise ConfigurationError(f"Environment variable {key} is missing and no default provided")
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {key} must be numeric") from exc


BEDROCK_MODEL_ID = _get_env("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
SECRET_NAME = _get_env("PROMPT_SECRET_NAME", "")
REGION = _get_env("AWS_REGION", "ap-northeast-1")
PROMPT_BODY_CHAR_LIMIT = _get_int_env("PROMPT_BODY_CHAR_LIMIT", 8000)
BEDROCK_MAX_ATTEMPTS = _get_int_env("BEDROCK_MAX_ATTEMPTS", 5)
BEDROCK_BACKOFF_BASE_SECONDS = _get_float_env("BEDROCK_BACKOFF_BASE_SECONDS", 5.0)
BEDROCK_BACKOFF_MAX_SECONDS = _get_float_env("BEDROCK_BACKOFF_MAX_SECONDS", 60.0)
BEDROCK_MAX_TOKENS = _get_int_env("BEDROCK_MAX_TOKENS", 2048)
THROTTLE_ERROR_CODES = {"ThrottlingException", "TooManyRequestsException", "ServiceUnavailableException"}

SUMMARIZER_PROVIDER = _get_env("SUMMARIZER_PROVIDER", "cloudflare").lower()
CLOUDFLARE_ACCOUNT_ID = _get_env("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = _get_env("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_API_TOKEN_SECRET_NAME = _get_env("CLOUDFLARE_API_TOKEN_SECRET_NAME", "")
CLOUDFLARE_MODEL_ID = _get_env("CLOUDFLARE_MODEL_ID", "@cf/meta/llama-3-8b-instruct")
CLOUDFLARE_TIMEOUT_SECONDS = _get_float_env("CLOUDFLARE_TIMEOUT_SECONDS", 40.0)

GUARDRAIL_PROMPT = (
    "出力する JSON は次の仕様に厳密に従ってください:\n"
    "- 出力は {\"summary_long\":\"...\",\"diff_points\":[]} の形式の JSON オブジェクト 1 つだけとし、余計な文字列や説明を付けない。\n"
    "- summary_long (500文字以内) は日本語で、入力本文に記載された事実のみを要約する。\n"
    "- diff_points は本文で確認できる固有名詞・数値などの事実を箇条書きで列挙する。存在しない場合は空配列 []。\n"
    "- 本文と無関係な出来事・他記事の情報・推測は一切含めない。本文で確認できない場合は summary_long に"
    "「本文から要約を生成できませんでした」と記載し、他フィールドも最小限にする。\n"
    "- JSON 以外のテキストやコードブロックは出力しない。"
)

bedrock = boto3.client(
    "bedrock-runtime",
    region_name=REGION,
    config=Config(retries={"max_attempts": 3, "mode": "standard"}),
)
secrets_manager = boto3.client("secretsmanager", region_name=REGION)

_cloudflare_api_token_cache: str | None = None


@dataclass
class PromptConfig:
    system: str
    user_template: str


@dataclass
class PromptPayload:
    system: str
    user: str


def load_prompt() -> PromptConfig:
    """Fetch prompt templates from Secrets Manager."""
    if not SECRET_NAME:
        raise ConfigurationError("PROMPT_SECRET_NAME must be configured for summarizer")
    try:
        response = secrets_manager.get_secret_value(SecretId=SECRET_NAME)
    except (ClientError, BotoCoreError) as exc:
        raise ExternalServiceError(f"Failed to load prompt secret: {exc}") from exc

    secret = json.loads(response["SecretString"])
    return PromptConfig(
        system=secret.get("system_prompt", ""),
        user_template=secret.get("user_template", ""),
    )


def _prepare_article_excerpt(body: str) -> str:
    excerpt = (body or "").strip()
    if len(excerpt) > PROMPT_BODY_CHAR_LIMIT:
        excerpt = excerpt[:PROMPT_BODY_CHAR_LIMIT]
    if not excerpt:
        excerpt = "（本文が空でした。入力データを確認してください。）"
    return f"<article>\n{excerpt}\n</article>"


def build_prompt(config: PromptConfig, body: str) -> PromptPayload:
    """Prepare prompt text shared across LLM providers."""
    article_block = _prepare_article_excerpt(body)
    try:
        user_prompt = config.user_template.format(
            article_body=article_block,
            guidance=GUARDRAIL_PROMPT,
        )
    except KeyError as exc:
        raise RuntimeError(f"Prompt template missing placeholder: {exc}") from exc
    if "{guidance}" not in config.user_template:
        user_prompt = f"{user_prompt.rstrip()}\n\n{GUARDRAIL_PROMPT}"
    else:
        user_prompt = user_prompt.strip()
    return PromptPayload(system=config.system, user=user_prompt)


JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
TOKEN_SPLIT_RE = re.compile(r"""[\s、。・,;:!?（）()\[\]{}"'`]+""")
JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
MARKDOWN_SECTION_RE = re.compile(r"\*\*\s*([^\*]+?)\s*\*\*\s*[:：]\s*(.*)", re.IGNORECASE)
PLAIN_SECTION_RE = re.compile(r"^\s*([A-Za-z][A-Za-z _()-]*?)\s*[:：]\s*(.*)", re.IGNORECASE)
BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*・•●◎◦]|[0-9]+[.)])\s*")
SUMMARY_KEYWORDS = (
    "summary_long",
    "summary long",
    "long summary",
    "summary (500",
    "summary (120",
)
DIFF_KEYWORDS = (
    "diff_points",
    "diff points",
    "differences",
    "diffs",
)


def _resolve_cloudflare_api_token() -> str:
    """Retrieve Cloudflare API token from env or Secrets Manager, caching the result."""
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
            raise ExternalServiceError(f"Failed to load Cloudflare API token secret: {exc}") from exc

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

    raise ExternalServiceError("Cloudflare API token must be configured via environment variable or Secrets Manager")


def _build_bedrock_request(prompt: PromptPayload) -> Dict[str, Any]:
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": BEDROCK_MAX_TOKENS,
        "temperature": 0.2,
        "system": prompt.system,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt.user}]}],
    }


def _find_json_candidates(text: str) -> list[str]:
    candidates = [match.group(1).strip() for match in JSON_FENCE_RE.finditer(text)]
    if candidates:
        return candidates

    # Fallback: scan for the first balanced JSON object in the text.
    results: list[str] = []
    depth = 0
    start_idx = None
    for idx, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start_idx = idx
            depth += 1
        elif char == "}":
            if depth:
                depth -= 1
                if depth == 0 and start_idx is not None:
                    results.append(text[start_idx : idx + 1].strip())
                    start_idx = None
    return results


def _parse_structured_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current_key: str | None = None
    buffer: list[str] = []

    def _flush():
        nonlocal current_key, buffer
        if current_key is not None:
            content = "\n".join(line for line in buffer if line.strip()).strip()
            sections[current_key] = content
        current_key = None
        buffer = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        markdown_match = MARKDOWN_SECTION_RE.match(line)
        if markdown_match:
            _flush()
            header = markdown_match.group(1).strip().lower()
            remainder = markdown_match.group(2).strip()
            current_key = header
            buffer = [remainder] if remainder else []
            continue

        plain_match = PLAIN_SECTION_RE.match(line)
        if plain_match and not line.strip().startswith(("-", "*", "・", "•", "●", "◎", "◦")):
            header = plain_match.group(1).strip().lower()
            remainder = plain_match.group(2).strip()
            if any(keyword in header for keyword in SUMMARY_KEYWORDS + DIFF_KEYWORDS):
                _flush()
                current_key = header
                buffer = [remainder] if remainder else []
                continue

        if current_key is not None:
            buffer.append(line)

    _flush()
    return sections


def _clean_summary_text(value: str) -> str:
    text = value.strip()
    if not text:
        return ""

    sections = _parse_structured_sections(text)
    for key in sections:
        lowered = key.lower()
        if any(keyword in lowered for keyword in SUMMARY_KEYWORDS):
            text = sections[key]
            break
    lines = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if BULLET_PREFIX_RE.match(stripped):
            continue
        lowered = stripped.lower()
        if lowered.startswith("summary") or lowered.startswith("diff"):
            continue
        if MARKDOWN_SECTION_RE.match(stripped):
            continue
        cleaned = BULLET_PREFIX_RE.sub("", stripped).strip()
        if not cleaned:
            continue
        lines.append(cleaned)

    if lines:
        deduped: list[str] = []
        seen: set[str] = set()
        for line in lines:
            if line not in seen:
                deduped.append(line)
                seen.add(line)
        text = "\n".join(deduped)

    text = re.sub(r"\*\*\s*summary(?:\s+long)?\s*\*\*\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*summary(?:_long|\s+long)?[^:：]*[:：]\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _parse_diff_points(value: str | list[Any]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value or "").strip()
    if not text:
        return []

    if text.startswith("["):
        try:
            parsed_json = json.loads(text)
            if isinstance(parsed_json, list):
                return [str(item).strip() for item in parsed_json if str(item).strip()]
        except json.JSONDecodeError:
            pass

    sections = _parse_structured_sections(text)
    for key in sections:
        lowered = key.lower()
        if any(keyword in lowered for keyword in DIFF_KEYWORDS):
            text = sections[key]
            break

    points: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        had_prefix = bool(BULLET_PREFIX_RE.match(stripped))
        cleaned = BULLET_PREFIX_RE.sub("", stripped).strip()
        if cleaned and (had_prefix or any(keyword in stripped.lower() for keyword in DIFF_KEYWORDS)):
            points.append(cleaned)
    return points


def _normalise_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure mandatory keys exist and have proper types."""
    summary_long_candidates = [
        data.get("summary_long"),
        data.get("summary"),
    ]

    def _pick(candidates: list[Any]) -> str:
        for value in candidates:
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text
        return ""

    summary_raw = _pick(summary_long_candidates)
    summary_cleaned = _clean_summary_text(summary_raw)
    summary_long = _extract_japanese_lines(summary_cleaned)

    diff_points = data.get("diff_points", [])
    if isinstance(diff_points, (str, list)):
        cleaned_diff_points = _parse_diff_points(diff_points)
    else:
        raise RuntimeError("diff_points must be a string or a list of strings")

    return {
        "summary_long": summary_long,
        "diff_points": cleaned_diff_points,
    }


def _contains_japanese(text: str) -> bool:
    return bool(JAPANESE_CHAR_RE.search(text))


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_SPLIT_RE.split(text):
        token = raw.strip()
        if not token:
            continue
        if _contains_japanese(token):
            tokens.append(token)
            continue
        lowered = token.lower()
        if len(lowered) < 3:
            continue
        tokens.append(lowered)
    return tokens


def _has_article_overlap(article: str, summary: str) -> bool:
    if not article or not summary:
        return False
    article_normalised = article.lower()
    tokens = _tokenize(summary)[:40]
    if not tokens:
        return False
    matches = 0
    for token in tokens:
        target = token if _contains_japanese(token) else token.lower()
        if target and target in article_normalised:
            matches += 1
    threshold = max(1, len(tokens) // 6)
    return matches >= threshold


def _fallback_summary() -> Dict[str, Any]:
    return {
        "summary_long": "",
        "diff_points": [],
    }


def _extract_japanese_lines(text: str) -> str:
    if not text:
        return ""
    segments = [segment.strip() for segment in text.splitlines() if segment.strip()]
    japanese_segments = [segment for segment in segments if _contains_japanese(segment)]
    if japanese_segments:
        return "\n".join(japanese_segments)
    return text.strip()


def _enforce_summary_quality(article: str, summaries: Dict[str, Any]) -> Dict[str, Any]:
    """Apply軽量な検証で本文との乖離を検出し、必要に応じてフォールバックする。"""
    article = article or ""
    if not summaries:
        LOGGER.warning("Summaries missing, falling back to default response")
        return _fallback_summary()

    summary_detail = (summaries.get("summary_long") or "").strip()

    if article:
        article_has_jp = _contains_japanese(article)
        summary_has_jp = any(
            _contains_japanese(text)
            for text in (summary_detail,)
            if text
        )
        # 言語が明らかに異なる（例: 英文本文 + 日本語要約）の場合は重複チェックをスキップ
        if article_has_jp == summary_has_jp:
            if not _has_article_overlap(article, summary_detail):
                LOGGER.warning("Summary content appears unrelated to article; using fallback")
                return _fallback_summary()
    return summaries


def call_bedrock(prompt: PromptPayload) -> Dict[str, Any]:
    """Invoke Claude with exponential backoff on throttling-related errors."""
    attempt = 0
    backoff = BEDROCK_BACKOFF_BASE_SECONDS
    request_payload = _build_bedrock_request(prompt)
    serialized = json.dumps(request_payload).encode("utf-8")

    while attempt < BEDROCK_MAX_ATTEMPTS:
        attempt += 1
        try:
            response = bedrock.invoke_model(
                body=serialized,
                modelId=BEDROCK_MODEL_ID,
                accept="application/json",
                contentType="application/json",
            )
            return json.loads(response["body"].read())
        except (ClientError, BotoCoreError) as exc:
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if error_code in THROTTLE_ERROR_CODES and attempt < BEDROCK_MAX_ATTEMPTS:
                LOGGER.warning(
                    "Bedrock throttled (attempt %s/%s, code=%s). Sleeping %.1fs before retry.",
                    attempt,
                    BEDROCK_MAX_ATTEMPTS,
                    error_code,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, BEDROCK_BACKOFF_MAX_SECONDS)
                continue
            LOGGER.exception("Bedrock invocation failed on attempt %s/%s", attempt, BEDROCK_MAX_ATTEMPTS)
            raise ExternalServiceError(f"Bedrock invocation failed: {exc}") from exc

    raise ExternalServiceError("Exceeded maximum Bedrock retry attempts")


def call_cloudflare(prompt: PromptPayload) -> Dict[str, Any]:
    """Invoke Cloudflare Workers AI text generation endpoint."""
    if not CLOUDFLARE_ACCOUNT_ID:
        raise ExternalServiceError("Cloudflare account ID must be configured")

    token = _resolve_cloudflare_api_token()

    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CLOUDFLARE_MODEL_ID}"
    payload = {
        "messages": [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=CLOUDFLARE_TIMEOUT_SECONDS,
        )
    except RequestException as exc:
        raise ExternalServiceError(f"Cloudflare request failed: {exc}") from exc

    if response.status_code >= 400:
        raise ExternalServiceError(f"Cloudflare returned HTTP {response.status_code}: {response.text[:200]}")

    try:
        data = response.json()
    except ValueError as exc:
        raise ExternalServiceError(f"Cloudflare returned non-JSON payload: {exc}") from exc
    if not data.get("success", True):
        raise ExternalServiceError(f"Cloudflare API error: {data.get('errors')}")
    return data


def _parse_summary_text(text: str) -> Dict[str, Any]:
    for candidate in _find_json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        try:
            return _normalise_schema(parsed)
        except RuntimeError as exc:
            LOGGER.warning("Invalid summary schema: %s", exc)

    LOGGER.warning("Failed to parse structured JSON response, returning fallback summaries")
    fallback = _fallback_summary()
    summary_section = _clean_summary_text(text)
    if not summary_section:
        summary_section = _clean_summary_text(text.splitlines()[0] if text else "")
    if not summary_section:
        summary_section = text[:600]
    fallback["summary_long"] = _extract_japanese_lines(summary_section)
    diff_candidates = _parse_diff_points(text)
    if diff_candidates:
        fallback["diff_points"] = diff_candidates
    return fallback


def parse_bedrock_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    content = raw.get("content", [])
    if not content:
        raise RuntimeError("Claude response missing content")

    text_segments = [item.get("text", "") for item in content if item.get("type") == "text"]
    text = "\n".join(segment for segment in text_segments if segment).strip()
    if not text:
        raise RuntimeError("Claude response missing text content")
    return _parse_summary_text(text)


def parse_cloudflare_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    result = raw.get("result") or {}
    text_candidates = [
        result.get("response"),
        result.get("output_text"),
        result.get("text"),
    ]
    text = ""
    for candidate in text_candidates:
        if isinstance(candidate, str) and candidate.strip():
            text = candidate.strip()
            break

    if not text:
        # Some Workers AI models return an array of message dicts
        messages = result.get("messages") or []
        if isinstance(messages, list):
            joined = []
            for message in messages:
                content = message.get("content")
                if isinstance(content, str):
                    joined.append(content)
            text = "\n".join(joined).strip()

    if not text:
        raise RuntimeError("Cloudflare response missing text content")

    return _parse_summary_text(text)


def parse_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Backward-compatible alias for existing unit tests."""
    return parse_bedrock_response(raw)


def _coerce_requested_at(value: Any) -> Optional[int]:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
        if isinstance(value, str) and value.strip():
            return int(value.strip())
    except (TypeError, ValueError):
        return None
    return None


def _should_generate_detailed(event: Dict[str, Any]) -> bool:
    if event.get("generate_detailed_summary"):
        return True
    request_context = event.get("request_context") or {}
    if not isinstance(request_context, dict):
        return False
    reason = (request_context.get("reason") or "").strip().lower()
    if reason not in {"detail", "on_demand_summary", "manual_detail"}:
        return False
    requested_at = _coerce_requested_at(request_context.get("requested_at"))
    return requested_at is not None


def _generate_lightweight_summary(event: Dict[str, Any]) -> Dict[str, Any]:
    item = event.get("item") or {}
    title = (item.get("title") or "").strip()
    body = (event.get("article_body") or "").strip()

    if not body:
        body = "本文が取得できませんでした。"

    if not title:
        title = body.splitlines()[0] if body else ""

    paragraphs = [line.strip() for line in body.splitlines() if line.strip()]
    if paragraphs:
        summary_long = " ".join(paragraphs)[:600]
    else:
        summary_long = body[:600]

    cleaned_long = _extract_japanese_lines(summary_long.strip())

    return {
        "summary_long": cleaned_long,
        "diff_points": [],
    }


def handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    if "article_body" not in event:
        raise ValueError("Event missing article_body")

    reason = (event.get("request_context") or {}).get("reason")
    LOGGER.info(
        "Summarizer invoked for item=%s reason=%s detailed_flag=%s",
        (event.get("item") or {}).get("id"),
        reason,
        bool(event.get("generate_detailed_summary")),
    )

    if not _should_generate_detailed(event):
        summaries = _generate_lightweight_summary(event)
        return {
            **event,
            "summaries": summaries,
        }

    prompt_config = load_prompt()
    prompt = build_prompt(prompt_config, event["article_body"])

    provider = SUMMARIZER_PROVIDER if SUMMARIZER_PROVIDER in {"bedrock", "cloudflare"} else "bedrock"
    if provider == "cloudflare":
        LOGGER.info("Calling Cloudflare model=%s", CLOUDFLARE_MODEL_ID)
        try:
            response = call_cloudflare(prompt)
            summaries = parse_cloudflare_response(response)
            llm_meta = {
                "provider": "cloudflare",
                "model_id": CLOUDFLARE_MODEL_ID,
                "raw_response": response,
            }
        except ExternalServiceError as exc:
            LOGGER.warning("Cloudflare summarization failed (%s); falling back to Bedrock", exc)
            response = call_bedrock(prompt)
            summaries = parse_bedrock_response(response)
            llm_meta = {
                "provider": "bedrock",
                "model_id": BEDROCK_MODEL_ID,
                "raw_response": response,
                "fallback_origin": {
                    "provider": "cloudflare",
                    "model_id": CLOUDFLARE_MODEL_ID,
                    "error": str(exc),
                },
            }
    else:
        LOGGER.info("Calling Bedrock model=%s tokens=%s", BEDROCK_MODEL_ID, BEDROCK_MAX_TOKENS)
        response = call_bedrock(prompt)
        summaries = parse_bedrock_response(response)
        llm_meta = {
            "provider": "bedrock",
            "model_id": BEDROCK_MODEL_ID,
            "raw_response": response,
        }
    summaries = _enforce_summary_quality(event["article_body"], summaries)

    return {
        **event,
        "summaries": summaries,
        "llm": llm_meta,
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    if isinstance(event, str):
        event = json.loads(event)
    return handle(event, context)
