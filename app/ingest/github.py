"""
app/ingest/github.py
GitHub Releases ingestion via public Atom feed (no API key needed).
"""
import calendar
import logging
import socket

import bleach
import feedparser

from app.ingest.rss import RawItem, _canonical_url

logger = logging.getLogger(__name__)

BLEACH_ALLOWED_TAGS: list[str] = []  # strip all HTML for plain-text excerpt


def fetch_github_releases(repo: str) -> list[RawItem]:
    """
    Fetch GitHub releases via public Atom feed.
    URL: https://github.com/{repo}/releases.atom
    """
    url = f"https://github.com/{repo}/releases.atom"
    try:
        prev_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(15)
        try:
            feed = feedparser.parse(url, request_headers={"Connection": "close"})
        finally:
            socket.setdefaulttimeout(prev_timeout)
    except Exception as exc:
        logger.warning("Failed to fetch GitHub releases for %s: %s", repo, exc)
        return []

    if getattr(feed, "bozo", False):
        bozo_exc = getattr(feed, "bozo_exception", None)
        logger.warning("Bozo feed for GitHub releases %s: %s", repo, bozo_exc)

    entries = getattr(feed, "entries", [])
    if not entries:
        logger.debug("No GitHub release entries found for %s", repo)
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

        # Prefix repo name for clarity in digest
        display_title = f"[{repo}] {title}"

        # Timestamp
        published_at: int | None = None
        pub_parsed = getattr(entry, "published_parsed", None)
        if pub_parsed is not None:
            try:
                published_at = calendar.timegm(pub_parsed)
            except Exception:
                published_at = None

        # Excerpt: release notes, bleach-cleaned, max 300 chars
        excerpt: str | None = None
        raw_summary = getattr(entry, "summary", None)
        if raw_summary:
            try:
                plain = bleach.clean(raw_summary, tags=[], strip=True).strip()
                excerpt = plain[:300] if plain else None
            except Exception:
                excerpt = None

        items.append(RawItem(
            url=link,
            canonical_url=_canonical_url(link),
            title=display_title,
            author="GitHub Releases",
            published_at=published_at,
            excerpt=excerpt,
            source_title=f"GitHub: {repo}",
        ))

    return items
