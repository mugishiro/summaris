import types

import pytest

from backend.lambdas.checker import handler as checker  # noqa: E402


class InMemoryTable:
    def __init__(self):
        self.storage: dict[tuple[str, str], dict] = {}

    def get_item(self, Key: dict):
        return {"Item": self.storage.get((Key["pk"], Key["sk"]))}

    def put_item(self, Item: dict):
        self.storage[(Item["pk"], Item["sk"])] = Item


@pytest.fixture()
def in_memory_table(monkeypatch: pytest.MonkeyPatch) -> InMemoryTable:
    table = InMemoryTable()
    monkeypatch.setattr(checker, "_table", lambda: table)
    monkeypatch.setattr(checker, "SOURCE_STATUS_TABLE", "test-table")
    return table


def make_metadata(source_id: str = "bbc-world", url: str = "https://example.com/feed", threshold: int = 3600):
    return checker.SourceMetadata(
        source_id=source_id,
        name="Example",
        url=url,
        threshold_seconds=threshold,
        force_fetch=False,
    )


def test_should_fetch_true_for_new_source():
    metadata = make_metadata()
    head = {"etag": None, "last_modified": None, "status": 200}
    assert checker._should_fetch(None, head, metadata) is True


def test_should_fetch_false_when_recent_and_no_change(monkeypatch: pytest.MonkeyPatch):
    metadata = make_metadata()
    monkeypatch.setattr(checker.time, "time", lambda: 10_000)
    existing = {
        "checked_at": 9_900,
        "etag": "etag-1",
        "last_modified": "Thu, 01 Jan 1970 00:00:00 GMT",
    }
    head = {"etag": "etag-1", "last_modified": "Thu, 01 Jan 1970 00:00:00 GMT", "status": 200}
    assert checker._should_fetch(existing, head, metadata) is False


def test_handle_enqueues_and_persists_when_fetch_needed(monkeypatch: pytest.MonkeyPatch, in_memory_table: InMemoryTable):
    monkeypatch.setattr(checker.time, "time", lambda: 123_456)
    head = {"etag": "etag-2", "last_modified": "Fri, 02 Jan 1970 00:00:00 GMT", "status": 200}
    monkeypatch.setattr(checker, "_perform_head", lambda url: head)

    event = {
        "source": {"id": "bbc-world", "name": "BBC World"},
        "endpoint": {"url": "https://example.com/feed"},
        "threshold_seconds": 3600,
    }

    result = checker.handle(event, context=types.SimpleNamespace())

    assert result["should_fetch"] is True
    assert result["enqueue"] is True
    assert result["metadata"] == head

    key = ("SOURCE#bbc-world", "URL#https://example.com/feed")
    stored = in_memory_table.storage[key]
    assert stored["etag"] == "etag-2"
    assert stored["status"] == 200
    assert stored["checked_at"] == 123_456


def test_handle_skips_enqueue_when_recent(monkeypatch: pytest.MonkeyPatch, in_memory_table: InMemoryTable):
    monkeypatch.setattr(checker.time, "time", lambda: 200_000)
    head = {"etag": "etag-current", "last_modified": "Sat, 03 Jan 1970 00:00:00 GMT", "status": 200}
    monkeypatch.setattr(checker, "_perform_head", lambda url: head)

    key = ("SOURCE#bbc-world", "URL#https://example.com/feed")
    in_memory_table.put_item(
        {
            "pk": key[0],
            "sk": key[1],
            "etag": "etag-current",
            "last_modified": "Sat, 03 Jan 1970 00:00:00 GMT",
            "checked_at": 199_500,
        }
    )

    event = {
        "source": {"id": "bbc-world", "name": "BBC World"},
        "endpoint": {"url": "https://example.com/feed"},
        "threshold_seconds": 5_000,
    }

    result = checker.handle(event, context=types.SimpleNamespace())

    assert result["should_fetch"] is False
    assert "enqueue" not in result

    stored = in_memory_table.storage[key]
    # checked_at should be refreshed even when skipping enqueue
    assert stored["checked_at"] == 200_000


def test_from_event_allows_source_url_fallback():
    event = {
        "source": {
            "id": "guardian",
            "name": "The Guardian",
            "url": "https://www.theguardian.com/world",
        },
        "threshold_seconds": 1200,
    }

    metadata = checker.SourceMetadata.from_event(event)

    assert metadata.source_id == "guardian"
    assert metadata.url == "https://www.theguardian.com/world"
    assert metadata.threshold_seconds == 1200
