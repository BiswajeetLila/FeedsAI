"""
app/ingest/rss.py
RSS/Atom feed fetcher using feedparser.
"""
import calendar
from dataclasses import dataclass
import logging
import socket
import urllib.parse

import bleach
import feedparser

logger = logging.getLogger(__name__)

BLEACH_ALLOWED_TAGS = ["a", "b", "i", "p", "code", "pre", "em", "strong"]
BLEACH_ALLOWED_ATTRS = {"a": ["href"]}


@dataclass
class RawItem:
    url: str
    canonical_url: str          # normalized: lowercase, strip query/fragments for dedup
    title: str
    author: str | None
    published_at: int | None    # unix timestamp
    excerpt: str | None         # bleach-cleaned, max 500 chars
    source_title: str | None


def _canonical_url(raw_url: str) -> str:
    """Normalize URL: lowercase, keep scheme+netloc+path only, no query/fragment."""
    try:
        parsed = urllib.parse.urlparse(raw_url)
        normalized = urllib.parse.urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            "",   # params
            "",   # query
            "",   # fragment
        ))
        return normalized
    except Exception:
        return raw_url.lower()


def _clean_excerpt(html_text: str | None) -> str | None:
    """Bleach-clean HTML, strip tags, truncate to 500 chars."""
    if not html_text:
        return None
    try:
        cleaned = bleach.clean(html_text, tags=BLEACH_ALLOWED_TAGS, attributes=BLEACH_ALLOWED_ATTRS, strip=True)
        # Strip remaining HTML tags to get plain text
        plain = bleach.clean(cleaned, tags=[], strip=True)
        plain = plain.strip()
        if not plain:
            return None
        return plain[:500]
    except Exception as exc:
        logger.debug("Error cleaning excerpt: %s", exc)
        return None


def _parse_timestamp(entry) -> int | None:
    """Parse published_parsed or updated_parsed to unix timestamp."""
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val is not None:
            try:
                return int(calendar.timegm(val))
            except (OverflowError, ValueError, OSError):
                continue
    return None


def fetch_rss(url: str, source_title: str | None = None) -> list[RawItem]:
    """
    Fetch and parse RSS/Atom feed. Returns list of RawItem.
    - Uses feedparser.parse(url)
    - Skips entries with no link or no title
    - On feedparser bozo error: logs warning but continues processing valid entries
    - Returns empty list on network failure, doesn't raise
    """
    try:
        prev_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(15)
        try:
            feed = feedparser.parse(url, request_headers={"Connection": "close"})
        finally:
            socket.setdefaulttimeout(prev_timeout)
    except Exception as exc:
        logger.warning("Network failure fetching %s: %s", url, exc)
        return []

    # Check for bozo (malformed feed)
    if getattr(feed, "bozo", False):
        bozo_exc = getattr(feed, "bozo_exception", None)
        logger.warning("Bozo feed at %s: %s", url, bozo_exc)
        # Continue anyway — feedparser often partially parses bozo feeds

    # If no entries at all and network error, return empty
    entries = getattr(feed, "entries", [])
    if not entries and not hasattr(feed, "feed"):
        logger.warning("No entries found at %s", url)
        return []

    items: list[RawItem] = []
    for entry in entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)

        if not link or not title:
            continue

        title = title.strip()
        if not title:
            continue

        # Author
        author: str | None = None
        if hasattr(entry, "author"):
            author = entry.author or None
        elif hasattr(entry, "authors") and entry.authors:
            author = entry.authors[0].get("name") if isinstance(entry.authors[0], dict) else None

        # Timestamp
        published_at = _parse_timestamp(entry)

        # Excerpt: prefer summary, fallback to description or content
        raw_html: str | None = None
        if hasattr(entry, "summary") and entry.summary:
            raw_html = entry.summary
        elif hasattr(entry, "description") and entry.description:
            raw_html = entry.description
        elif hasattr(entry, "content") and entry.content:
            # content is a list of dicts
            raw_html = entry.content[0].get("value") if entry.content else None

        excerpt = _clean_excerpt(raw_html)

        items.append(RawItem(
            url=link,
            canonical_url=_canonical_url(link),
            title=title,
            author=author,
            published_at=published_at,
            excerpt=excerpt,
            source_title=source_title or getattr(feed.feed, "title", None),
        ))

    return items
