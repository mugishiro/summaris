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
