import json
import pathlib
import sys

import pytest
from types import SimpleNamespace
from urllib.error import HTTPError

sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))

from backend.lambdas.collector import handler as collector  # noqa: E402


def test_handle_fetches_and_normalizes_html(monkeypatch: pytest.MonkeyPatch):
    sample_html = """
    <html><body>
    <article>
      <h1>Example</h1>
      <p>This is the first paragraph.</p>
      <p>This is the second paragraph.</p>
    </article>
    </body></html>
    """

    def fake_request(url, headers, **kwargs):
        response = SimpleNamespace(headers=SimpleNamespace(get_content_charset=lambda default: "utf-8"))
        return sample_html.encode("utf-8"), response

    monkeypatch.setattr(collector, "_request_with_retry", fake_request)
    monkeypatch.setattr(collector, "_resolve_feed_url", lambda article_url, endpoint_url: None)
    monkeypatch.setattr(collector.time, "time", lambda: 1000.0)

    event = {"item": {"link": "https://example.com/news/1"}, "source": {"id": "example"}}
    result = collector.handle(event, context=None)

    assert "article_body" in result
    assert "This is the first paragraph." in result["article_body"]
    assert result["metrics"]["fetch_seconds"] == 0.0


def test_handle_truncates_large_payload(monkeypatch: pytest.MonkeyPatch):
    large_text = "A" * 5000
    def fake_request(url, headers, **kwargs):
        response = SimpleNamespace(headers=SimpleNamespace(get_content_charset=lambda default: "utf-8"))
        return large_text.encode("utf-8"), response

    monkeypatch.setattr(collector, "_request_with_retry", fake_request)
    monkeypatch.setattr(collector, "_resolve_feed_url", lambda article_url, endpoint_url: None)
    monkeypatch.setattr(collector.time, "time", lambda: 2000.0)
    monkeypatch.setattr(collector, "MAX_ARTICLE_BYTES", 100)

    event = {"item": {"link": "https://example.com/large"}, "source": {"id": "example"}}
    result = collector.handle(event, context=None)

    assert len(result["article_body"].encode("utf-8")) <= 100


def test_handle_raises_runtime_error_on_fetch_failure(monkeypatch: pytest.MonkeyPatch):
    def fake_request(url, headers, **kwargs):
        raise TimeoutError("timeout")

    monkeypatch.setattr(collector, "_request_with_retry", fake_request)
    monkeypatch.setattr(collector, "_resolve_feed_url", lambda article_url, endpoint_url: None)
    monkeypatch.setattr(collector.time, "time", lambda: 3000.0)

    event = {"item": {"link": "https://example.com/error"}, "source": {"id": "example"}}

    with pytest.raises(RuntimeError) as excinfo:
        collector.handle(event, context=None)

    assert "Collector failed" in str(excinfo.value)


def test_handle_falls_back_to_feed(monkeypatch: pytest.MonkeyPatch):
    def fake_fetch(url, headers, **kwargs):
        raise HTTPError(url, 500, "error", hdrs=None, fp=None)

    monkeypatch.setattr(collector, "_request_with_retry", fake_fetch)
    monkeypatch.setattr(collector, "_resolve_feed_url", lambda article_url, endpoint_url: "https://example.com/feed")
    monkeypatch.setattr(collector, "_fetch_feed_entry_text", lambda feed, target: "RSS body")
    monkeypatch.setattr(collector.time, "time", lambda: 100.0)

    event = {
        "item": {"link": "https://example.com/rss-item"},
        "endpoint": {"url": "https://example.com/feed"},
        "source": {"id": "example"},
    }

    result = collector.handle(event, context=None)

    assert result["article_body"] == "RSS body"
    assert result["metrics"].get("fallback") == "rss"


def test_lambda_handler_accepts_string_payload(monkeypatch: pytest.MonkeyPatch):
    def fake_request(url, headers, **kwargs):
        response = SimpleNamespace(headers=SimpleNamespace(get_content_charset=lambda default: "utf-8"))
        return b"<p>Hello World</p>", response

    monkeypatch.setattr(collector, "_request_with_retry", fake_request)
    monkeypatch.setattr(collector, "_resolve_feed_url", lambda article_url, endpoint_url: None)
    monkeypatch.setattr(collector.time, "time", lambda: 4000.0)

    payload = json.dumps({"item": {"link": "https://example.com"}, "source": {"id": "foo"}})
    result = collector.lambda_handler(payload, context=None)

    assert result["item"]["link"] == "https://example.com"
