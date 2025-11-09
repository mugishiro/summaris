import json

import pytest

from backend.lambdas.diff_validator import handler as diff_validator  # noqa: E402


def test_extract_candidate_facts_returns_numbers_and_names():
    text = "Prime Minister Fumio Kishida met with President Joe Biden on April 10, 2024 in Tokyo."
    facts = diff_validator.extract_candidate_facts(text)
    assert any("Fumio Kishida" in fact for fact in facts)
    assert any("Joe Biden" in fact for fact in facts)
    assert "2024" in facts


def test_handle_populates_diff_points_when_missing():
    article = "The yen climbed to 150.23 per dollar after remarks by Finance Minister Shunichi Suzuki."
    event = {
        "article_body": article,
        "summaries": {
            "summary_long": "Finance Minister Shunichi Suzuki は市場安定化への取り組みを強調し、その直後に円が150.23ドルに上昇した。",
            "diff_points": [],
        },
    }

    result = diff_validator.handle(event, context=None)
    assert result["summaries"]["diff_points"]
    assert result["diff_validation"]["status"] in {"ok", "needs_review"}


def test_handle_respects_existing_diff_points(monkeypatch: pytest.MonkeyPatch):
    article = "The SpaceX Falcon 9 rocket launched 22 Starlink satellites from Florida."
    event = {
        "article_body": article,
        "summaries": {
            "summary_long": "SpaceXはFalcon 9ロケットを用い、フロリダのケープカナベラル宇宙軍基地から22基のStarlink衛星を打ち上げた。これによりブロードバンド提供網がさらに強化される。",
            "diff_points": ["22", "Falcon 9", "Starlink"],
        },
    }

    result = diff_validator.handle(event, context=None)
    assert result["summaries"]["diff_points"] == ["22", "Falcon 9", "Starlink"]
    missing = result["diff_validation"]["missing"]
    assert "Falcon 9" not in missing


def test_lambda_handler_accepts_string_payload():
    payload = json.dumps(
        {
            "article_body": "Prime Minister Kishida met President Biden at the White House.",
            "summaries": {
                "summary_long": "岸田文雄首相は米ホワイトハウスでジョー・バイデン大統領と首脳会談を行い、防衛協力や経済安全保障を巡る連携を確認した。",
                "diff_points": [],
            },
        }
    )
    result = diff_validator.lambda_handler(payload, context=None)
    assert "diff_validation" in result
