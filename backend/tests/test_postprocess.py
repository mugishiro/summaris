import pathlib
import sys
from typing import Any, Dict

import pytest

root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(root))
sys.path.append(str(root / "backend" / "lambdas"))

from backend.lambdas.postprocess import handler as postprocess  # noqa: E402


class StubTable:
    def __init__(self) -> None:
        self.items: Dict[tuple[str, str], Dict[str, Any]] = {}

    def get_item(self, Key: Dict[str, str]) -> Dict[str, Any]:  # noqa: N803
        return {"Item": self.items.get((Key["pk"], Key["sk"]))}

    def put_item(self, Item: Dict[str, Any]) -> None:  # noqa: N803
        self.items[(Item["pk"], Item["sk"])] = Item


class StubDynamo:
    def __init__(self) -> None:
        self.table = StubTable()

    def Table(self, _name: str) -> StubTable:  # noqa: N803
        return self.table


@pytest.fixture(autouse=True)
def _patch_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(postprocess, "TABLE_NAME", "test-table", raising=False)
    monkeypatch.setattr(postprocess, "dynamodb", StubDynamo(), raising=False)
    monkeypatch.setattr(postprocess, "SUMMARY_TTL_SECONDS", 0, raising=False)
    monkeypatch.setattr(postprocess, "DETAIL_TTL_SECONDS", 0, raising=False)
    monkeypatch.setattr(postprocess, "_translate_headline", lambda title: None, raising=False)
    monkeypatch.setattr(postprocess, "_translate_text_to_japanese", lambda text: None, raising=False)


def _build_payload(**overrides: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "source": {"id": "source-1"},
        "item": {
            "id": "item-1",
            "title": "Sample headline",
            "link": "https://example.com/article",
        },
        "summaries": {
            "summary_long": "長い要約のテキスト",
            "diff_points": ["ポイント1", "ポイント2"],
        },
        "metrics": {},
        "request_context": {},
    }
    payload.update(overrides)
    return payload


def test_put_summary_with_ingest_reason_marks_partial() -> None:
    payload = _build_payload(request_context={"reason": "ingest"})

    postprocess.put_summary(payload)

    stored = postprocess.dynamodb.table.items[("SOURCE#source-1", "ITEM#item-1")]
    assert stored["detail_status"] == "partial"
    assert stored["summaries"] == {}


def test_put_summary_requires_explicit_detail_request_metadata() -> None:
    payload = _build_payload(request_context={"reason": "detail"})

    postprocess.put_summary(payload)

    stored = postprocess.dynamodb.table.items[("SOURCE#source-1", "ITEM#item-1")]
    assert stored["detail_status"] == "partial"
    assert stored["summaries"] == {}


def test_put_summary_stores_detail_when_flag_and_timestamp_present() -> None:
    payload = _build_payload(
        request_context={"reason": "detail", "requested_at": "1712345678"},
        generate_detailed_summary=True,
    )

    postprocess.put_summary(payload)

    stored = postprocess.dynamodb.table.items[("SOURCE#source-1", "ITEM#item-1")]
    assert stored["detail_status"] == "ready"
    assert stored["summaries"]["summary_long"] == "長い要約のテキスト"
    assert stored["detail_requested_at"] == 1712345678


def test_put_summary_translates_non_japanese_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _build_payload(
        summaries={
            "summary_long": "This is an English summary.",
            "diff_points": ["Point A", "Point B"],
        },
        request_context={"reason": "detail", "requested_at": "1712345678"},
        generate_detailed_summary=True,
    )

    translated_text = "これは翻訳された要約です。"
    monkeypatch.setattr(
        postprocess,
        "_translate_text_to_japanese",
        lambda text: translated_text,
        raising=False,
    )

    postprocess.put_summary(payload)

    stored = postprocess.dynamodb.table.items[("SOURCE#source-1", "ITEM#item-1")]
    assert stored["summaries"]["summary_long"] == translated_text
    assert payload["summaries"]["summary_long"] == translated_text


def test_ingest_preserves_existing_ready_summary() -> None:
    table = postprocess.dynamodb.table
    table.put_item(
        {
            "pk": "SOURCE#source-1",
            "sk": "ITEM#item-1",
            "summaries": {"summary_long": "既存の要約", "diff_points": ["既存ポイント"]},
            "detail_status": "ready",
            "detail_ready_at": 1700000000,
        }
    )

    payload = _build_payload(request_context={"reason": "ingest"})

    postprocess.put_summary(payload)

    stored = table.items[("SOURCE#source-1", "ITEM#item-1")]
    assert stored["detail_status"] == "ready"
    assert stored["summaries"]["summary_long"] == "既存の要約"
    assert stored["summaries"]["diff_points"] == ["既存ポイント"]


def test_put_summary_strips_english_segments() -> None:
    payload = _build_payload(
        summaries={
            "summary_long": "This is an English sentence. 日本語の説明です。",
            "diff_points": [],
        },
        request_context={"reason": "detail", "requested_at": "1712345678"},
        generate_detailed_summary=True,
    )

    postprocess.put_summary(payload)

    stored = postprocess.dynamodb.table.items[("SOURCE#source-1", "ITEM#item-1")]
    assert stored["summaries"]["summary_long"] == "日本語の説明です。"


def test_put_summary_sets_fallback_when_no_japanese_available() -> None:
    payload = _build_payload(
        summaries={
            "summary_long": "Completely English summary without Japanese.",
            "diff_points": ["Point A"],
        },
        request_context={"reason": "detail", "requested_at": "1712345678"},
        generate_detailed_summary=True,
    )

    postprocess.put_summary(payload)

    stored = postprocess.dynamodb.table.items[("SOURCE#source-1", "ITEM#item-1")]
    assert stored["summaries"]["summary_long"] == postprocess.SUMMARY_FALLBACK_MESSAGE
