"""
app/routes/digest.py
Main digest page route.
"""
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.content_signals import is_low_signal, low_signal_reasons, novelty_label
from app.db import get_db, get_digest_items, record_activity
from app.digest_modes import VALID_DIGEST_MODES, apply_digest_mode, normalize_digest_mode
from app.onboarding import setup_required
from app.reason_labels import build_reason_chips
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
_OVERFETCH_FACTOR = 3


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
    low_signal = is_low_signal(item)
    novel = novelty_label(item, cluster_size=cluster_size)
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
        "is_liked": item.is_liked,
        "is_saved": item.is_saved,
        "age": _format_age(item.published_at),
        "cluster_id": item.cluster_id,
        "cluster_size": cluster_size,
        "topic": item.topic,
        "reason_chips": build_reason_chips(item, cluster_size=cluster_size),
        "quality_flags": low_signal_reasons(item),
        "is_low_signal": low_signal,
        "novelty_label": novel,
    }


@router.get("/", response_class=HTMLResponse)
async def digest_page(
    request: Request,
    topic: str = "",
    saved: int = 0,
    show_low_signal: int = 0,
    mode: str = "ranked",
):
    if setup_required():
        return RedirectResponse("/setup", status_code=303)

    active_topic = topic if topic else None
    saved_only = saved == 1
    show_low_signal_bool = show_low_signal == 1
    digest_mode = normalize_digest_mode(mode)
    never_fetched = not _LAST_FETCH_FILE.exists()
    last_updated = _get_last_updated()
    stale = is_data_stale()

    digest_items = []
    has_more = False
    with get_db() as conn:
        raw_limit = (_PAGE_SIZE * _OVERFETCH_FACTOR) + 1
        raw_items = get_digest_items(
            conn,
            hours=24 * 7,
            limit=raw_limit,
            offset=0,
            topic=active_topic,
            saved_only=saved_only,
        )
        has_more = len(raw_items) > raw_limit - 1
        raw_items = apply_digest_mode(raw_items, digest_mode)
        hidden_low_signal = 0

        for item in raw_items:
            try:
                record_activity(conn, item.id, "viewed")
            except Exception as exc:
                logger.warning("Could not record viewed activity for item %d: %s", item.id, exc)
            item_dict = _build_item_dict(conn, item)
            if item_dict["is_low_signal"] and not show_low_signal_bool:
                hidden_low_signal += 1
                continue
            digest_items.append(item_dict)
            if len(digest_items) >= _PAGE_SIZE:
                break

    return templates.TemplateResponse(
        request,
        "digest.html",
        {
            "items": digest_items,
            "last_updated": last_updated,
            "is_stale": stale,
            "never_fetched": never_fetched,
            "active_topic": active_topic or "",
            "saved_only": saved_only,
            "show_low_signal": show_low_signal_bool,
            "hidden_low_signal": hidden_low_signal,
            "digest_mode": digest_mode,
            "digest_modes": VALID_DIGEST_MODES,
            "topics": TOPICS,
            "has_more": has_more,
            "next_offset": raw_limit - 1,
        },
    )


@router.get("/digest/more", response_class=HTMLResponse)
async def digest_more(
    request: Request,
    offset: int = 10,
    limit: int = 10,
    topic: str = "",
    saved: int = 0,
    show_low_signal: int = 0,
    mode: str = "ranked",
):
    active_topic = topic if topic else None
    saved_only = saved == 1
    show_low_signal_bool = show_low_signal == 1
    digest_mode = normalize_digest_mode(mode)
    fetch_limit = min(limit, 20)

    with get_db() as conn:
        raw_limit = (fetch_limit * _OVERFETCH_FACTOR) + 1
        raw_items = get_digest_items(
            conn,
            hours=24 * 7,
            limit=raw_limit,
            offset=offset,
            topic=active_topic,
            saved_only=saved_only,
        )
        has_more = len(raw_items) > raw_limit - 1
        raw_items = apply_digest_mode(raw_items, digest_mode)

        items = []
        for item in raw_items:
            item_dict = _build_item_dict(conn, item)
            if item_dict["is_low_signal"] and not show_low_signal_bool:
                continue
            items.append(item_dict)
            if len(items) >= fetch_limit:
                break

    return templates.TemplateResponse(
        request,
        "digest_more.html",
        {
            "items": items,
            "has_more": has_more,
            "next_offset": offset + raw_limit - 1,
            "active_topic": active_topic or "",
            "saved_only": saved_only,
            "show_low_signal": show_low_signal_bool,
            "digest_mode": digest_mode,
            "limit": fetch_limit,
        },
    )
