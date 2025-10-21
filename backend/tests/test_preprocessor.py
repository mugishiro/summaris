import json
import pathlib
import sys
from types import SimpleNamespace

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from backend.lambdas.preprocessor import handler as preprocessor  # noqa: E402


class DummyComprehend:
    def __init__(self, response):
        self._response = response
        self.called_with = None

    def detect_dominant_language(self, Text):
        self.called_with = Text
        return self._response


def test_normalize_url_removes_tracking_params():
    normalized, fingerprint = preprocessor.normalize_url(
        "https://example.com/news?a=1&utm_source=test&b=2"
    )
    assert normalized == "https://example.com/news?a=1&b=2"
    assert len(fingerprint) == 64


def test_compute_simhash_consistent():
    text = "Example Domain is used for examples. Example domain!"
    fp1 = preprocessor.compute_simhash(text)
    fp2 = preprocessor.compute_simhash(text.upper())
    assert fp1 == fp2
    assert len(fp1) == preprocessor.SIMHASH_BITS // 4


def test_detect_language_with_stub(monkeypatch):
    fake_client = DummyComprehend(
        {"Languages": [{"LanguageCode": "ja", "Score": 0.9}]}
    )
    monkeypatch.setattr(preprocessor, "comprehend", fake_client)

    result = preprocessor.detect_language("こんにちは 世界")
    assert result.code == "ja"
    assert result.is_reliable is True
    assert result.score == pytest.approx(0.9)


def test_enrich_event_builds_payload(monkeypatch):
    fake_client = DummyComprehend(
        {"Languages": [{"LanguageCode": "en", "Score": 0.8}]}
    )
    monkeypatch.setattr(preprocessor, "comprehend", fake_client)

    event = {
        "source": {"id": "bbc-world"},
        "item": {
            "id": "example-1",
            "title": "Sample",
            "link": "https://example.com/article?utm_source=test",
        },
        "article_body": "Example Domain is used for illustrative examples.",
        "metrics": {"fetch_seconds": 1.23},
    }
    enriched = preprocessor.enrich_event(event)

    assert enriched["item"]["normalized_link"].startswith("https://example.com/")
    assert "preprocess" in enriched
    assert enriched["preprocess"]["language"]["code"] == "en"
    assert "simhash" in enriched["preprocess"]["hashes"]


def test_lambda_handler_accepts_string_payload(monkeypatch):
    fake_client = DummyComprehend(
        {"Languages": [{"LanguageCode": "en", "Score": 0.95}]}
    )
    monkeypatch.setattr(preprocessor, "comprehend", fake_client)

    event = {
        "source": {"id": "bbc-world"},
        "item": {
            "id": "example-2",
            "title": "Sample",
            "link": "https://example.com/",
        },
        "article_body": "Example Domain is used for illustrative examples.",
    }
    payload = json.dumps(event)
    result = preprocessor.lambda_handler(payload, SimpleNamespace())
    assert result["item"]["link_fingerprint"]
