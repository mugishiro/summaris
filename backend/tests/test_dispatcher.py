import json

import pytest

from backend.lambdas.dispatcher import handler as dispatcher  # noqa: E402


class StubSQS:
    def __init__(self, response=None):
        self.calls = []
        self._response = response or {"MessageId": "msg-1", "SequenceNumber": "seq-1"}

    def send_message(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_handle_skips_enqueue_when_flag_false(monkeypatch: pytest.MonkeyPatch):
    stub = StubSQS()
    monkeypatch.setattr(dispatcher, "sqs", stub)
    monkeypatch.setattr(dispatcher, "RAW_QUEUE_URL", "https://sqs.example.com/queue")

    event = {"should_fetch": False, "source": {"id": "bbc-world"}}
    result = dispatcher.handle(event, context=None)

    assert result["enqueued"] is False
    assert stub.calls == []


def test_handle_enqueues_when_flag_true(monkeypatch: pytest.MonkeyPatch):
    stub = StubSQS({"MessageId": "msg-123", "SequenceNumber": "seq-456"})
    monkeypatch.setattr(dispatcher, "sqs", stub)
    monkeypatch.setattr(dispatcher, "RAW_QUEUE_URL", "https://sqs.example.com/queue")
    monkeypatch.setattr(dispatcher, "_resolve_feed_url", lambda article, endpoint: "https://feed.example.com/rss")
    monkeypatch.setattr(
        dispatcher,
        "_fetch_feed_entries",
        lambda feed_url, limit=20: [
            {"link": "https://www3.nhk.or.jp/news/article1.html", "title": "Title 1"}
        ],
    )

    event = {
        "should_fetch": True,
        "source": {"id": "nhk-news"},
        "endpoint": {"url": "https://www3.nhk.or.jp/news/"},
    }
    result = dispatcher.handle(event, context=None)

    assert result["enqueued"] is True
    assert result["queue_message"] == {"message_id": "msg-123", "sequence_number": "seq-456"}
    assert len(stub.calls) == 1
    sent_body = json.loads(stub.calls[0]["MessageBody"])
    assert sent_body["source"]["id"] == "nhk-news"
    assert sent_body["item"]["link"] == "https://www3.nhk.or.jp/news/article1.html"
    assert sent_body["item"]["id"].startswith("nhk-news-")


def test_handle_enqueues_multiple_entries(monkeypatch: pytest.MonkeyPatch):
    stub = StubSQS({"MessageId": "msg-abc", "SequenceNumber": "seq-xyz"})
    monkeypatch.setattr(dispatcher, "sqs", stub)
    monkeypatch.setattr(dispatcher, "RAW_QUEUE_URL", "https://sqs.example.com/queue")
    monkeypatch.setattr(dispatcher, "_resolve_feed_url", lambda article, endpoint: "https://example.com/feed")
    monkeypatch.setattr(
        dispatcher,
        "_fetch_feed_entries",
        lambda feed_url, limit=20: [
            {"link": "https://example.com/article-1", "title": "First"},
            {"link": "https://example.com/article-2", "title": "Second"},
        ],
    )

    event = {
        "should_fetch": True,
        "source": {"id": "bbc-world"},
        "endpoint": {"url": "https://www.bbc.com/news/world"},
    }

    result = dispatcher.handle(event, context=None)

    assert result["enqueued"] is True
    assert result["messages_enqueued"] == 2
    assert len(stub.calls) == 2
    payloads = [json.loads(call["MessageBody"]) for call in stub.calls]
    links = {payload["item"]["link"] for payload in payloads}
    assert links == {"https://example.com/article-1", "https://example.com/article-2"}
