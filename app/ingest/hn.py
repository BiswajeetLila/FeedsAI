"""
app/ingest/hn.py
Hacker News ingestion via Algolia API.
"""
import logging

import httpx

from app.ingest.rss import RawItem, _canonical_url

logger = logging.getLogger(__name__)

HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"


def fetch_hn(feed_filter: str = "front_page", limit: int = 30) -> list[RawItem]:
    """
    Fetch HN stories via Algolia API.
    GET https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30
    """
    try:
        params = {
            "tags": feed_filter,
            "hitsPerPage": limit,
        }
        response = httpx.get(HN_ALGOLIA_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("Failed to fetch HN (%s): %s", feed_filter, exc)
        return []

    items: list[RawItem] = []
    for hit in data.get("hits", []):
        url = hit.get("url")
        if not url:
            # Skip Ask HN, internal HN posts, etc.
            continue

        title = hit.get("title") or ""
        title = title.strip()
        if not title:
            continue

        # created_at_i is unix timestamp (int); fallback to None
        published_at: int | None = hit.get("created_at_i")
        if published_at is not None:
            try:
                published_at = int(published_at)
            except (TypeError, ValueError):
                published_at = None

        items.append(RawItem(
            url=url,
            canonical_url=_canonical_url(url),
            title=title,
            author=hit.get("author"),
            published_at=published_at,
            excerpt=None,
            source_title="Hacker News",
        ))

    return items
