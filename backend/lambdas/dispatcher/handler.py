"""
Dispatcher Lambda.

Receives the result from the checker step, and when the article needs to be
fetched, enqueues a message to the raw ingestion SQS queue. The message payload
mirrors the event to allow asynchronous processing.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from hashlib import md5
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from shared.url import ensure_source_link, normalize_url


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

RAW_QUEUE_URL = os.getenv("RAW_QUEUE_URL", "")
FEED_USER_AGENT = os.getenv("DISPATCHER_FEED_USER_AGENT", "news-summary-dispatcher/0.1")
SUMMARY_TABLE_NAME = os.getenv("SUMMARY_TABLE_NAME", "")

KNOWN_FEEDS = {
    "www.bbc.com": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "bbc.com": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "www.bbc.co.uk": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "bbc.co.uk": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "www3.nhk.or.jp": "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "www.nhk.or.jp": "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "www.aljazeera.com": "https://www.aljazeera.com/xml/rss/all.xml",
    "aljazeera.com": "https://www.aljazeera.com/xml/rss/all.xml",
    "www.dw.com": "https://rss.dw.com/rdf/rss-en-world",
    "dw.com": "https://rss.dw.com/rdf/rss-en-world",
    "www.elpais.com": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
    "elpais.com": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
    "www.straitstimes.com": "https://www.straitstimes.com/news/world/rss.xml",
    "straitstimes.com": "https://www.straitstimes.com/news/world/rss.xml",
    "timesofindia.indiatimes.com": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "www.timesofindia.indiatimes.com": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
    "www.allafrica.com": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
    "allafrica.com": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
}

sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")
summary_table = dynamodb.Table(SUMMARY_TABLE_NAME) if SUMMARY_TABLE_NAME else None


def _send_message(event: Dict[str, Any]) -> Dict[str, Any]:
    if not RAW_QUEUE_URL:
        raise RuntimeError("RAW_QUEUE_URL environment variable must be set")

    body = json.dumps(event)
    try:
        response = sqs.send_message(QueueUrl=RAW_QUEUE_URL, MessageBody=body)
    except (ClientError, BotoCoreError) as exc:
        LOGGER.error("Failed to send message to SQS: %s", exc)
        raise
    return {
        "message_id": response.get("MessageId"),
        "sequence_number": response.get("SequenceNumber"),
    }


def _resolve_feed_url(article_url: str | None, endpoint_url: str | None) -> str | None:
    if endpoint_url and any(endpoint_url.lower().endswith(ext) for ext in (".xml", ".rss", ".atom", ".rdf")):
        return endpoint_url

    candidate = endpoint_url
    if article_url:
        parsed = urlparse(article_url)
        netloc = parsed.netloc.lower()
        override = KNOWN_FEEDS.get(netloc)
        if override and (
            not candidate
            or not any(candidate.lower().endswith(ext) for ext in (".xml", ".rss", ".atom", ".rdf"))
        ):
            candidate = override
    return candidate


def _fetch_feed_entries(feed_url: str, *, limit: int = 20) -> List[Dict[str, str]]:
    import xml.etree.ElementTree as ET

    request = urllib.request.Request(feed_url, headers={"User-Agent": FEED_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read()
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.warning("Failed to fetch feed %s: %s", feed_url, exc)
        return []

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        LOGGER.warning("Failed to parse feed %s: %s", feed_url, exc)
        return []

    entries: List[Dict[str, str]] = []
    seen: set[str] = set()
    atom_ns = "{http://www.w3.org/2005/Atom}"
    rdf_ns = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"

    def _parse_datetime(value: str | None):
        if not value:
            return None
        text = value.strip()
        if not text:
            return None
        try:
            dt = parsedate_to_datetime(text)
            return dt.isoformat()
        except (ValueError, TypeError):
            try:
                dt = parsedate_to_datetime(text.replace("GMT", "UTC"))
                return dt.isoformat()
            except Exception:  # pylint: disable=broad-except
                return None

    def _add(link: str | None, title: str | None, published: str | None = None):
        if not link:
            return
        link = link.strip()
        if not link or link in seen:
            return
        seen.add(link)
        entry: Dict[str, str] = {"link": link, "title": title.strip() if title else ""}
        if published:
            parsed = _parse_datetime(published)
            if parsed:
                entry["published_at"] = parsed
        entries.append(entry)

    def _iter_items():
        yielded: set[int] = set()
        for item in root.findall(".//item"):
            yielded.add(id(item))
            yield item
        for elem in root.iter():
            tag = getattr(elem, "tag", "")
            if isinstance(tag, str) and tag.split("}")[-1].lower() == "item" and id(elem) not in yielded:
                yielded.add(id(elem))
                yield elem

    def _child_text(elem, local_name: str) -> str | None:
        for child in list(elem):
            tag = getattr(child, "tag", "")
            if isinstance(tag, str) and tag.split("}")[-1].lower() == local_name:
                text = (child.text or "").strip()
                if text:
                    return text
        return None

    def _child_text(elem, local_name: str) -> str | None:
        for child in list(elem):
            tag = getattr(child, "tag", "")
            if isinstance(tag, str) and tag.split("}")[-1].lower() == local_name:
                text = (child.text or "").strip()
                if text:
                    return text
        return None

    def _item_link(elem):
        link = _child_text(elem, "link")
        if link:
            return link
        for atom_link in elem.findall(f"{atom_ns}link"):
            href = atom_link.attrib.get("href")
            if href:
                return href.strip()
        guid = _child_text(elem, "guid")
        if guid:
            return guid
        for attr_key, attr_value in elem.attrib.items():
            if isinstance(attr_key, str) and attr_key.split("}")[-1].lower() in {"about", "resource"}:
                return attr_value.strip()
        return None

    def _item_title(elem):
        return _child_text(elem, "title")

    def _item_published(elem):
        published = _child_text(elem, "pubdate")
        if not published:
            published = _child_text(elem, "dc:date")
        if not published:
            published = _child_text(elem, "published")
        if not published:
            published = _child_text(elem, "updated")
        return published

    for item in _iter_items():
        link = _item_link(item)
        title = _item_title(item)
        published = _item_published(item)
        _add(link, title, published)
        if len(entries) >= limit:
            return entries

    for entry in root.findall(f".//{atom_ns}entry"):
        link = None
        for atom_link in entry.findall(f"{atom_ns}link"):
            href = atom_link.attrib.get("href")
            if href:
                link = href
                break
        published = (
            entry.findtext(f"{atom_ns}published")
            or entry.findtext(f"{atom_ns}updated")
        )
        _add(link, entry.findtext(f"{atom_ns}title"), published)
        if len(entries) >= limit:
            break

    if not entries:
        for elem in root.iter():
            tag = getattr(elem, "tag", "")
            if isinstance(tag, str) and tag.split("}")[-1].lower() == "entry":
                link = None
                for attr_key, attr_value in elem.attrib.items():
                    if attr_key.startswith(rdf_ns) and attr_key.split("}")[-1].lower() in {"about", "resource"}:
                        link = attr_value
                        break
                if not link:
                    link = _child_text(elem, "link")
                title = _child_text(elem, "title")
                published = (
                    _child_text(elem, "published")
                    or _child_text(elem, "updated")
                    or _child_text(elem, "pubdate")
                    or _child_text(elem, "dc:date")
                )
                _add(link, title, published)
                if len(entries) >= limit:
                    break

    return entries


def _build_item(source_id: str, entry: Dict[str, str]) -> Dict[str, Any]:
    raw_link = (entry.get("link") or "").strip()
    link = ensure_source_link(source_id, raw_link) or raw_link
    title = (entry.get("title") or "").strip()
    normalized_link, fingerprint = normalize_url(link)
    hashed = md5(normalized_link.encode("utf-8")).hexdigest() if normalized_link else md5(link.encode("utf-8")).hexdigest()
    item_id = f"{source_id}-{hashed}"
    published_at = entry.get("published_at")
    return {
        "link": link,
        "title": title,
        "id": item_id,
        "normalized_link": normalized_link,
        "link_fingerprint": fingerprint,
        "published_at": published_at,
    }


def _already_processed(source_id: str, item_id: str) -> bool:
    """Return True when the summary table already stores this item."""
    if not summary_table:
        return False
    try:
        response = summary_table.get_item(
            Key={
                "pk": f"SOURCE#{source_id}",
                "sk": f"ITEM#{item_id}",
            },
            ProjectionExpression="pk",
        )
    except (ClientError, BotoCoreError) as exc:
        LOGGER.warning("Failed to check summary table for item=%s: %s", item_id, exc)
        return False
    return "Item" in response


def handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    should_fetch = bool(event.get("should_fetch"))
    result: Dict[str, Any] = dict(event)

    if not should_fetch:
        LOGGER.info("should_fetch=false for source=%s; skipping enqueue", event.get("source"))
        result["enqueued"] = False
        return result

    endpoint_url = event.get("endpoint", {}).get("url")
    article_link = event.get("item", {}).get("link") or endpoint_url
    feed_url = _resolve_feed_url(article_link, endpoint_url)

    entries: List[Dict[str, str]] = []
    if feed_url:
        entries = _fetch_feed_entries(feed_url)

    if not entries:
        if not article_link:
            LOGGER.error("No article link available for source=%s", event.get("source", {}).get("id"))
            result["enqueued"] = False
            return result
        entries = [{"link": article_link, "title": event.get("item", {}).get("title", "")}]

    source_id = str(event.get("source", {}).get("id") or "source")
    messages = []
    duplicates: list[Dict[str, Any]] = []
    for entry in entries:
        link = entry.get("link")
        if not link:
            continue
        item = _build_item(source_id, entry)
        if _already_processed(source_id, item["id"]):
            duplicates.append(item)
            LOGGER.info("Skipping duplicate item id=%s url=%s", item["id"], link)
            continue

        payload = {
            "source": event.get("source"),
            "endpoint": {"url": feed_url or endpoint_url},
            "metadata": event.get("metadata"),
            "should_fetch": True,
            "threshold_seconds": event.get("threshold_seconds"),
            "enqueue": True,
            "item": item,
            "request_context": {
                "reason": "ingest",
                "source_id": source_id,
            },
        }

        message_meta = _send_message(payload)
        messages.append({"item": item, "queue_message": message_meta})
        LOGGER.info(
            "Enqueued message for source=%s item=%s message_id=%s",
            source_id,
            item["id"],
            message_meta.get("MessageId"),
        )

    result["enqueued"] = bool(messages)
    result["messages_enqueued"] = len(messages)
    result["feed_url"] = feed_url or endpoint_url
    result["duplicates_skipped"] = len(duplicates)
    if messages:
        result["queue_message"] = messages[0]["queue_message"]
    if duplicates:
        result["duplicate_item_ids"] = [item["id"] for item in duplicates]
    return result


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    if isinstance(event, str):
        event = json.loads(event)
    return handle(event, context)
