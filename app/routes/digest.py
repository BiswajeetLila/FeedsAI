"""
app/routes/digest.py
Main digest page route.
"""
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.db import get_db, get_digest_items, record_activity
from app.startup import is_data_stale, _LAST_FETCH_FILE
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter()

TOPICS = [
    ("space", "Space"),
    ("robotics", "Robotics"),
    ("ai", "AI"),
    ("science", "Science"),
    ("design", "Design"),
    ("scifi", "Sci-Fi"),
    ("rationalism", "Rationalism"),
    ("engineering", "Engineering"),
    ("india", "India"),
]

_PAGE_SIZE = 10


def tier_label(score: float) -> tuple[str, str]:
    if score >= 8.0:
        return "top", "Top pick"
    elif score >= 5.0:
        return "relevant", "Relevant"
    else:
        return "borderline", "Borderline"


def _format_age(published_at: int | None) -> str:
    if published_at is None:
        return "unknown age"
    age_seconds = int(time.time()) - published_at
    if age_seconds < 3600:
        mins = max(1, age_seconds // 60)
        return f"{mins}m ago"
    elif age_seconds < 86400:
        hours = age_seconds // 3600
        return f"{hours}h ago"
    else:
        days = age_seconds // 86400
        return f"{days}d ago"


def _get_last_updated() -> str:
    if not _LAST_FETCH_FILE.exists():
        return "Never"
    try:
        return _LAST_FETCH_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return "Unknown"


def _build_item_dict(conn, item) -> dict:
    cluster_size: int | None = None
    if item.cluster_id is not None:
        row = conn.execute(
            "SELECT member_count FROM clusters WHERE id=?", (item.cluster_id,)
        ).fetchone()
        if row:
            cluster_size = row["member_count"]

    tier, label = tier_label(item.score)
    return {
        "id": item.id,
        "title": item.title,
        "url": item.url,
        "source_title": item.source_title,
        "excerpt": item.excerpt,
        "score": item.score,
        "tier": tier,
        "tier_label": label,
        "is_read": item.is_read,
        "age": _format_age(item.published_at),
        "cluster_id": item.cluster_id,
        "cluster_size": cluster_size,
        "topic": item.topic,
    }


@router.get("/", response_class=HTMLResponse)
async def digest_page(request: Request, topic: str = ""):
    active_topic = topic if topic else None
    never_fetched = not _LAST_FETCH_FILE.exists()
    last_updated = _get_last_updated()
    stale = is_data_stale()

    digest_items = []
    has_more = False
    with get_db() as conn:
        raw_items = get_digest_items(conn, hours=24 * 7, limit=_PAGE_SIZE + 1, offset=0, topic=active_topic)
        has_more = len(raw_items) > _PAGE_SIZE
        raw_items = raw_items[:_PAGE_SIZE]

        for item in raw_items:
            try:
                record_activity(conn, item.id, "viewed")
            except Exception as exc:
                logger.warning("Could not record viewed activity for item %d: %s", item.id, exc)
            digest_items.append(_build_item_dict(conn, item))

    return templates.TemplateResponse(
        request,
        "digest.html",
        {
            "items": digest_items,
            "last_updated": last_updated,
            "is_stale": stale,
            "never_fetched": never_fetched,
            "active_topic": active_topic or "",
            "topics": TOPICS,
            "has_more": has_more,
            "next_offset": _PAGE_SIZE,
        },
    )


@router.get("/digest/more", response_class=HTMLResponse)
async def digest_more(request: Request, offset: int = 10, limit: int = 10, topic: str = ""):
    active_topic = topic if topic else None
    fetch_limit = min(limit, 20)

    with get_db() as conn:
        raw_items = get_digest_items(
            conn, hours=24 * 7, limit=fetch_limit + 1, offset=offset, topic=active_topic
        )
        has_more = len(raw_items) > fetch_limit
        raw_items = raw_items[:fetch_limit]

        items = [_build_item_dict(conn, item) for item in raw_items]

    return templates.TemplateResponse(
        request,
        "digest_more.html",
        {
            "items": items,
            "has_more": has_more,
            "next_offset": offset + fetch_limit,
            "active_topic": active_topic or "",
            "limit": fetch_limit,
        },
    )
