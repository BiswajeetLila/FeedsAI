"""
app/ingest/arxiv.py
arXiv ingestion via the official Atom API.
"""
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from app.ingest.rss import RawItem, _canonical_url

logger = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"

# Atom XML namespaces used by arXiv
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# Strip version suffix like v1, v2 from arxiv abs URLs
_VERSION_RE = re.compile(r"(arxiv\.org/abs/[\d.]+)v\d+$", re.IGNORECASE)


def _strip_arxiv_version(url: str) -> str:
    """Remove version suffix (v1, v2, …) from arXiv abs URL before canonicalizing."""
    return _VERSION_RE.sub(r"\1", url)


def _parse_iso8601(ts: str) -> int | None:
    """Parse ISO 8601 timestamp string to unix int."""
    try:
        # arXiv uses format: 2024-01-23T12:34:56Z
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return None


def fetch_arxiv(query: str, max_results: int = 20) -> list[RawItem]:
    """
    Fetch arXiv papers via the official Atom API.
    GET https://export.arxiv.org/api/query?search_query={query}&max_results={max_results}&sortBy=submittedDate&sortOrder=descending
    """
    try:
        params = {
            "search_query": query,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        response = httpx.get(ARXIV_API_URL, params=params, timeout=20)
        response.raise_for_status()
        xml_text = response.text
    except Exception as exc:
        logger.warning("Failed to fetch arXiv (query=%s): %s", query, exc)
        return []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Failed to parse arXiv XML (query=%s): %s", query, exc)
        return []

    items: list[RawItem] = []
    for entry in root.findall("atom:entry", _NS):
        # URL: <id> element text
        id_el = entry.find("atom:id", _NS)
        if id_el is None or not id_el.text:
            continue
        raw_url = id_el.text.strip()

        # Title
        title_el = entry.find("atom:title", _NS)
        if title_el is None or not title_el.text:
            continue
        title = " ".join(title_el.text.split())  # collapse whitespace

        # Canonical URL: strip version suffix then normalize
        versioned_stripped = _strip_arxiv_version(raw_url)
        canonical = _canonical_url(versioned_stripped)

        # Authors: first author name, "et al." if multiple
        author_els = entry.findall("atom:author", _NS)
        author: str | None = None
        if author_els:
            first_name_el = author_els[0].find("atom:name", _NS)
            if first_name_el is not None and first_name_el.text:
                author = first_name_el.text.strip()
                if len(author_els) > 1:
                    author = f"{author} et al."

        # Published timestamp
        pub_el = entry.find("atom:published", _NS)
        published_at: int | None = None
        if pub_el is not None and pub_el.text:
            published_at = _parse_iso8601(pub_el.text.strip())

        # Excerpt: <summary> stripped and truncated to 500 chars
        summary_el = entry.find("atom:summary", _NS)
        excerpt: str | None = None
        if summary_el is not None and summary_el.text:
            plain = " ".join(summary_el.text.split())
            excerpt = plain[:500] if plain else None

        items.append(RawItem(
            url=raw_url,
            canonical_url=canonical,
            title=title,
            author=author,
            published_at=published_at,
            excerpt=excerpt,
            source_title="arXiv",
        ))

    return items
