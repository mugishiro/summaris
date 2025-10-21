import io
import json
import pathlib
import sys

import pytest
from botocore.exceptions import ClientError

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from backend.lambdas.summarizer import handler as summarizer  # noqa: E402


def test_build_prompt_includes_article_and_guidance():
    config = summarizer.PromptConfig(
        system="system prompt",
        user_template="記事:\n{article_body}\n\n{guidance}",
    )
    payload = summarizer.build_prompt(config, "本文テキスト")

    assert payload.system == "system prompt"
    assert "本文テキスト" in payload.user
    assert "JSON は次の仕様" in payload.user


def test_parse_response_extracts_json_payload():
    raw = {
        "content": [
            {
                "type": "text",
                "text": "```json\n{\n"
                '  "summary_long": "長い要約",\n'
                '  "diff_points": ["差分"]\n'
                "}\n```"
            }
        ]
    }

    result = summarizer.parse_bedrock_response(raw)
    assert result["summary_long"] == "長い要約"
    assert result["diff_points"] == ["差分"]


def test_parse_cloudflare_response_extracts_json_payload():
    raw = {
        "success": True,
        "result": {
            "response": "```json\n{\n"
            '  "summary_long": "長い要約",\n'
            '  "diff_points": ["差分"]\n'
            "}\n```"
        },
    }

    result = summarizer.parse_cloudflare_response(raw)
    assert result["summary_long"] == "長い要約"
    assert result["diff_points"] == ["差分"]


def test_call_bedrock_retries_on_throttling(monkeypatch: pytest.MonkeyPatch):
    class DummyClient:
        def __init__(self):
            self.calls = 0

        def invoke_model(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ClientError(
                    {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
                    "InvokeModel",
                )
            return {"body": io.BytesIO(b'{"ok": true}')}

    dummy = DummyClient()
    monkeypatch.setattr(summarizer, "bedrock", dummy)
    monkeypatch.setattr(summarizer.time, "sleep", lambda s: None)

    result = summarizer.call_bedrock(summarizer.PromptPayload(system="", user=""))
    assert result["ok"] is True
    assert dummy.calls == 2


def test_handle_returns_summaries(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        summarizer,
        "load_prompt",
        lambda: summarizer.PromptConfig(system="sys", user_template="{article_body}{guidance}"),
    )
    monkeypatch.setattr(
        summarizer,
        "call_bedrock",
        lambda prompt: {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "summary_long": "長い",
                            "diff_points": ["a"],
                        }
                    )
                }
            ]
        },
    )
    monkeypatch.setattr(summarizer, "_enforce_summary_quality", lambda article, summary: summary)

    event = {"article_body": "本文", "source": {"id": "bbc"}, "generate_detailed_summary": True}
    result = summarizer.handle(event, context=None)

    assert result["summaries"]["summary_long"] == "長い"
    assert result["llm"]["model_id"] == summarizer.BEDROCK_MODEL_ID
    assert result["llm"]["provider"] == "bedrock"


def test_handle_cloudflare_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(summarizer, "SUMMARIZER_PROVIDER", "cloudflare", raising=False)
    monkeypatch.setattr(
        summarizer,
        "load_prompt",
        lambda: summarizer.PromptConfig(system="sys", user_template="{article_body}{guidance}"),
    )
    def raise_cloudflare_error(prompt):
        raise summarizer.ExternalServiceError("boom")

    monkeypatch.setattr(summarizer, "call_cloudflare", raise_cloudflare_error)
    monkeypatch.setattr(
        summarizer,
        "call_bedrock",
        lambda prompt: {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "summary_long": "長い",
                            "diff_points": ["a"],
                        }
                    )
                }
            ]
        },
    )
    monkeypatch.setattr(summarizer, "_enforce_summary_quality", lambda article, summary: summary)

    event = {"article_body": "本文", "source": {"id": "bbc"}, "generate_detailed_summary": True}
    result = summarizer.handle(event, context=None)

    assert result["summaries"]["summary_long"] == "長い"
    assert result["llm"]["provider"] == "bedrock"
    assert result["llm"]["fallback_origin"]["provider"] == "cloudflare"
