"""
Collector Lambda (Fetch step).

Responsibilities:
- Receive a single RSS feed URL and metadata.
- Download the feed/article payload.
- Emit normalized article JSON to the Step Functions state machine.

This is a PoC implementation; network access, retries, and error handling should
be reviewed before production use.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from html import unescape
from html.parser import HTMLParser
from typing import Any, Dict


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

USER_AGENT = "news-summary-collector/0.1"
FEED_USER_AGENT = os.getenv("COLLECTOR_FEED_USER_AGENT", USER_AGENT)
MAX_ARTICLE_BYTES = int(os.getenv("MAX_ARTICLE_BYTES", "200000"))

KNOWN_FEEDS: Dict[str, str] = {
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
LD_JSON_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
ARTICLE_TYPES = {"Article", "NewsArticle", "ReportageNewsArticle", "AnalysisNewsArticle", "LiveBlogPosting"}
BBC_TEXT_BLOCK_RE = re.compile(r'<div[^>]+data-component=["\']text-block["\'][^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL)


class _HTMLTextExtractor(HTMLParser):
    """
    フィード内の HTML をプレーンテキストへ変換する簡易パーサ。
    script/style など本文に無関係なタグはスキップし、取得したテキスト
    から過剰な空白を圧縮する。
    """

    _SKIP_TAGS = {"script", "style", "noscript"}
    _BLOCK_TAGS = {
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "main",
        "aside",
        "li",
        "ul",
        "ol",
        "br",
        "hr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS and self._parts:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS and self._parts:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(unescape(text))

    def get_text(self) -> str:
        return " ".join(self._parts)


def _html_to_text(payload: str) -> str:
    """
    HTML をプレーンテキストへ変換する。解析に失敗した場合は元の
    ペイロードを返す。
    """
    if "<" not in payload or ">" not in payload:
        return payload

    parser = _HTMLTextExtractor()
    try:
        parser.feed(payload)
    except Exception:  # pylint: disable=broad-except
        LOGGER.warning("HTML parsing failed, returning raw payload")
        return payload

    text = parser.get_text()
    if not text:
        return payload

    # 空白を整理して読みやすくする。
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \f\r\v]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _coerce_text(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, list):
        parts = [_coerce_text(item) for item in value]
        joined = "\n".join(part for part in parts if part)
        return joined or None
    return None


def _extract_body_from_obj(obj: Any) -> str | None:
    if isinstance(obj, list):
        for item in obj:
            text = _extract_body_from_obj(item)
            if text:
                return text
        return None

    if not isinstance(obj, dict):
        return None

    candidates = ("articleBody", "text", "body", "description")
    for key in candidates:
        if key in obj:
            text = _coerce_text(obj[key])
            if text:
                return text

    for nested_key in ("mainEntityOfPage", "articleSection", "hasPart", "isPartOf", "@graph"):
        if nested_key in obj:
            text = _extract_body_from_obj(obj[nested_key])
            if text:
                return text

    return None


def _load_ldjson_objects(payload: str) -> list[Any]:
    payload = payload.strip()
    if not payload:
        return []
    try:
        data = json.loads(payload)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        items: list[Any] = []
        decoder = json.JSONDecoder()
        idx = 0
        length = len(payload)
        while idx < length:
            try:
                obj, offset = decoder.raw_decode(payload, idx)
            except json.JSONDecodeError:
                break
            items.append(obj)
            idx = offset
            while idx < length and payload[idx].isspace():
                idx += 1
        return items


def _extract_structured_article(html: str) -> str | None:
    for match in LD_JSON_RE.finditer(html):
        raw_json = unescape(match.group(1))
        for obj in _load_ldjson_objects(raw_json):
            if isinstance(obj, dict):
                types = obj.get("@type")
                if types:
                    if isinstance(types, str):
                        type_list = [types]
                    elif isinstance(types, list):
                        type_list = [str(t) for t in types]
                    else:
                        type_list = []
                else:
                    type_list = []
                if type_list and not any(t in ARTICLE_TYPES or str(t).lower().endswith("article") for t in type_list):
                    # 可能性の低いタイプはスキップして次を確認
                    text = _extract_body_from_obj(obj)
                else:
                    text = _extract_body_from_obj(obj)
            else:
                text = _extract_body_from_obj(obj)

            if text:
                return text
    return None


def _extract_bbc_article(html: str) -> str | None:
    blocks = BBC_TEXT_BLOCK_RE.findall(html)
    if not blocks:
        return None

    paragraphs = [_html_to_text(block) for block in blocks]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        return None

    article = "\n\n".join(paragraphs)
    article = re.sub(r"Share this page.*", "", article, flags=re.IGNORECASE | re.DOTALL)
    # BBC のページでは関連リンクが本文直後に連続するケースがあるため 5 行以上重複したら後方を削る
    lines = article.splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if cleaned and stripped == cleaned[-1]:
            continue
        cleaned.append(stripped)
    article = "\n".join(cleaned)
    return article.strip() or None


def _extract_article_text(url: str, html: str) -> str | None:
    if "bbc.com/news/" in url:
        article = _extract_bbc_article(html)
        if article:
            return article
    structured = _extract_structured_article(html)
    if structured:
        normalised = _html_to_text(structured)
        if len(normalised) >= 200:
            return normalised
    return None


RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def _request_with_retry(
    url: str,
    headers: Dict[str, str],
    *,
    max_attempts: int = 4,
    base_sleep: float = 0.5,
    timeout: float = 10.0,
) -> tuple[bytes, Any]:
    attempt = 0
    sleep = base_sleep
    while attempt < max_attempts:
        attempt += 1
        request = urllib.request.Request(url, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=timeout)
            try:
                body = response.read()
                return body, response
            finally:
                response.close()
        except urllib.error.HTTPError as exc:
            status = exc.code
            LOGGER.warning("HTTP error %s for %s (attempt %s/%s)", status, url, attempt, max_attempts)
            if status in RETRYABLE_STATUS_CODES and attempt < max_attempts:
                time.sleep(sleep)
                sleep = min(sleep * 2, 8.0)
                continue
            raise
        except urllib.error.URLError as exc:
            LOGGER.warning("URLError for %s (attempt %s/%s): %s", url, attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(sleep)
                sleep = min(sleep * 2, 8.0)
                continue
            raise


def fetch_body(url: str) -> str:
    """Fetch raw text from the target URL with retries."""
    body, response = _request_with_retry(url, headers={"User-Agent": USER_AGENT})
    charset = response.headers.get_content_charset("utf-8")
    return body.decode(charset, errors="replace")


def _normalise_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().lstrip("www.")
    path = parsed.path.rstrip("/")
    return f"{netloc}{path}"


def _resolve_feed_url(article_url: str, endpoint_url: str | None) -> str | None:
    # Prefer explicitly provided endpoint if it looks like a feed.
    if endpoint_url and any(endpoint_url.lower().endswith(ext) for ext in (".xml", ".rss", ".atom", ".rdf")):
        return endpoint_url

    candidate = endpoint_url

    parsed_article = urlparse(article_url)
    netloc = parsed_article.netloc.lower()

    override = KNOWN_FEEDS.get(netloc)
    if override and (not candidate or not any(candidate.lower().endswith(ext) for ext in (".xml", ".rss", ".atom", ".rdf"))):
        candidate = KNOWN_FEEDS.get(netloc, candidate)

    return candidate


def _fetch_feed_entry_text(feed_url: str | None, target_link: str) -> str | None:
    if not feed_url:
        return None

    LOGGER.info("Attempting RSS fallback feed=%s target=%s", feed_url, target_link)
    try:
        feed_body, _ = _request_with_retry(feed_url, headers={"User-Agent": FEED_USER_AGENT})
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.warning("Failed to fetch RSS feed %s: %s", feed_url, exc)
        return None

    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(feed_body)
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.warning("Failed to parse RSS feed %s: %s", feed_url, exc)
        return None

    target_norm = _normalise_url(target_link)
    target_path = urlparse(target_link).path.rstrip("/") if target_link else ""
    content_ns = "{http://purl.org/rss/1.0/modules/content/}"
    atom_ns = "{http://www.w3.org/2005/Atom}"
    def _child_text(elem, local_name: str) -> str | None:
        for child in list(elem):
            tag = getattr(child, "tag", "")
            if isinstance(tag, str) and tag.split("}")[-1].lower() == local_name:
                text = (child.text or "").strip()
                if text:
                    return text
        return None

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
        for entry in root.findall(f".//{atom_ns}entry"):
            yield entry

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

    def _item_content(elem):
        for tag in [
            f"{content_ns}encoded",
            "content:encoded",
            f"{atom_ns}content",
            "description",
            "summary",
        ]:
            found = elem.find(tag)
            if found is not None and (found.text or "").strip():
                return found.text
        for child in list(elem):
            tag = getattr(child, "tag", "")
            if isinstance(tag, str) and tag.split("}")[-1].lower() in {"encoded", "content", "description", "summary"}:
                text = (child.text or "").strip()
                if text:
                    return text
        return None

    for item in _iter_items():
        candidate_link = _item_link(item)
        if candidate_link:
            candidate_norm = _normalise_url(candidate_link)
            candidate_path = urlparse(candidate_link).path.rstrip("/")
            if candidate_norm and candidate_norm == target_norm:
                content = _item_content(item)
                if content:
                    LOGGER.info("Using RSS content fallback for %s", target_link)
                    return _html_to_text(content)
            if target_path and candidate_path and candidate_path == target_path:
                content = _item_content(item)
                if content:
                    LOGGER.info("Using RSS content fallback for %s", target_link)
                    return _html_to_text(content)
        if candidate_link and target_link and target_link in candidate_link:
            content = _item_content(item)
            if content:
                LOGGER.info("Using partial RSS fallback for %s", target_link)
                return _html_to_text(content)

    LOGGER.warning("No matching RSS entry found for link=%s feed=%s", target_link, feed_url)
    return None


def handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda entrypoint for Step Functions Task state.

    Expected input:
    {
      "source": {"id": "...", "name": "..."},
      "item": {"link": "...", "title": "..."}
    }
    """
    start = time.time()
    item = event.get("item", {})
    url = item.get("link")
    if not url:
        raise ValueError("Missing item.link in event payload")
    raw_feed = event.get("endpoint", {}).get("url")
    feed_url = _resolve_feed_url(url, raw_feed)
    feed_entry_body: str | None = None
    if feed_url:
        feed_entry_body = _fetch_feed_entry_text(feed_url, url)

    LOGGER.info("Fetching article url=%s", url)
    try:
        body = fetch_body(url)
        primary_error = None
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.warning("Primary fetch failed for %s: %s", url, exc)
        body = ""
        primary_error = exc

    duration = time.time() - start
    LOGGER.info("Fetch attempt completed in %.2fs", duration)

    normalized_body = None
    if body:
        extracted_body = _extract_article_text(url, body)
        if extracted_body:
            normalized_body = extracted_body
        else:
            structured_body = _extract_structured_article(body)
            if structured_body:
                normalized_body = _html_to_text(structured_body)
                fallback_body = _html_to_text(body)
                if len(normalized_body) < 200 <= len(fallback_body):
                    normalized_body = fallback_body
            else:
                normalized_body = _html_to_text(body)

    if feed_entry_body:
        if not normalized_body:
            normalized_body = feed_entry_body
            LOGGER.info("Using RSS body because article content missing for %s", url)
        elif len(normalized_body) < 200 and len(feed_entry_body) > len(normalized_body):
            LOGGER.info("Replacing short article body with RSS content for %s", url)
            normalized_body = feed_entry_body

    if not normalized_body:
        if primary_error:
            raise RuntimeError(f"Collector failed: {primary_error}") from primary_error
        raise RuntimeError("Collector failed: Unable to obtain article body")

    raw_bytes = normalized_body.encode("utf-8")
    if len(raw_bytes) > MAX_ARTICLE_BYTES:
        LOGGER.warning(
            "Article body larger than limit bytes=%s max=%s; truncating",
            len(raw_bytes),
            MAX_ARTICLE_BYTES,
        )
        normalized_body = raw_bytes[:MAX_ARTICLE_BYTES].decode("utf-8", errors="ignore")

    metrics: Dict[str, Any] = {"fetch_seconds": duration}
    if primary_error and normalized_body and feed_entry_body:
        metrics["fallback"] = "rss"
    if feed_entry_body:
        sources = metrics.setdefault("sources", [])
        if "rss" not in sources:
            sources.append("rss")

    return {
        "source": event.get("source"),
        "item": item,
        "article_body": normalized_body,
        "metrics": metrics,
        "request_context": event.get("request_context"),
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Compatibility wrapper for AWS Lambda console.

    Step Functions uses `handle` for clarity; this wrapper allows
    direct Lambda testing.
    """
    if isinstance(event, str):
        event = json.loads(event)
    return handle(event, context)
