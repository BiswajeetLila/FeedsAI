"""
app/routes/items.py
Item detail, drawer, and activity routes.
"""
import html
import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from app.db import (
    get_db,
    get_item_by_id,
    mark_item_liked,
    mark_item_read,
    mark_item_saved,
    record_activity,
)
from app.engagement import VALID_EVENTS
from app.explain import build_item_explanation
from app.summarize import build_item_insight

logger = logging.getLogger(__name__)

router = APIRouter()


def _cluster_size(conn, item) -> int | None:
    if item.cluster_id is None:
        return None
    row = conn.execute(
        "SELECT member_count FROM clusters WHERE id=?",
        (item.cluster_id,),
    ).fetchone()
    return int(row["member_count"]) if row else None


def _render_why_panel(explanation: dict) -> str:
    rows = [
        ("Score", f"{explanation['score']:.1f}/10 - {explanation['tier_label']}"),
    ]
    if explanation.get("topic"):
        rows.append(("Topic", explanation["topic"]))
    if explanation.get("source_quality_score") is not None:
        rows.append(("Source quality", f"{explanation['source_quality_score']:.1f}"))
    if explanation.get("cluster_size") and explanation["cluster_size"] > 1:
        rows.append(("Related items", str(explanation["cluster_size"])))
    if explanation.get("rationale"):
        rows.append(("Rationale", explanation["rationale"]))

    row_html = "".join(
        f"<div><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"
        for label, value in rows
    )

    def chips(values, class_name=""):
        return "".join(
            f'<span class="reason-chip {class_name}">{html.escape(value)}</span>'
            for value in values
            if value
        )

    matched = chips(explanation.get("matched_interests", []), "match")
    reasons = chips(explanation.get("reason_chips", []))
    novelty = chips([explanation.get("novelty_label")], "novelty")
    flags = chips(explanation.get("low_signal_flags", []), "caution")

    return f"""
    <details class="why-panel">
      <summary>Why am I seeing this?</summary>
      <div class="why-grid">{row_html}</div>
      {f'<div class="reason-row">{matched}</div>' if matched else ''}
      {f'<div class="reason-row">{novelty}{reasons}{flags}</div>' if (novelty or reasons or flags) else ''}
    </details>
    """


@router.get("/item/{item_id}/summary", response_class=HTMLResponse)
async def item_summary(item_id: int):
    """HTMX partial: instant item context for the digest drawer."""
    with get_db() as conn:
        item = get_item_by_id(conn, item_id)
        if not item:
            return HTMLResponse("<p>Item not found.</p>", status_code=404)

        body, points = build_item_insight(item)
        cluster_size = _cluster_size(conn, item)
        explanation = build_item_explanation(conn, item, cluster_size=cluster_size)
        mark_item_read(conn, item_id)

    escaped_body = html.escape(body)
    escaped_points = [html.escape(p) for p in points]
    liked_class = "like-btn liked" if item.is_liked else "like-btn"
    liked_label = "&#10084; Liked" if item.is_liked else "&#9825; Like"
    saved_class = "save-btn saved" if item.is_saved else "save-btn"
    saved_label = "&#9733; Saved" if item.is_saved else "&#9734; Save"

    bullets = "".join(f"<li>{p}</li>" for p in escaped_points)
    why_panel = _render_why_panel(explanation)
    html_content = f"""
    <div class="summary-content">
        <p>{escaped_body}</p>
        {"<ul>" + bullets + "</ul>" if bullets else ""}
        {why_panel}
        <div class="drawer-actions">
            <button class="{liked_class}" data-item-id="{item_id}"
                    onclick="likeArticle({item_id}, this)">
                {liked_label}
            </button>
            <button class="{saved_class}" data-item-id="{item_id}"
                    onclick="saveArticle({item_id}, this)">
                {saved_label}
            </button>
        </div>
    </div>
    """
    return HTMLResponse(html_content)


@router.get("/item/{item_id}", response_class=HTMLResponse)
async def item_detail(item_id: int):
    """Show item detail page for mobile / direct link."""
    with get_db() as conn:
        item = get_item_by_id(conn, item_id)
        if not item:
            return HTMLResponse("<p>Item not found.</p>", status_code=404)

        body, points = build_item_insight(item)
        mark_item_read(conn, item_id)

    escaped_body = html.escape(body)
    escaped_points = [html.escape(p) for p in points]
    bullets = "".join(f"<li>{p}</li>" for p in escaped_points)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{html.escape(item.title)}</title></head>
    <body>
      <article>
        <h1>{html.escape(item.title)}</h1>
        <div class="summary-content">
          <p>{escaped_body}</p>
          {"<ul>" + bullets + "</ul>" if bullets else ""}
          <a href="{html.escape(item.url)}" target="_blank" rel="noopener noreferrer">Read original &#x2197;</a>
        </div>
      </article>
    </body>
    </html>
    """
    return HTMLResponse(html_content)


@router.post("/activity/{item_id}/{event}")
async def record_activity_endpoint(item_id: int, event: str, dwell_seconds: float = 0.0):
    """Record activity event. Used by dwell timer."""
    from fastapi import HTTPException
    if event not in VALID_EVENTS:
        raise HTTPException(status_code=422, detail=f"Invalid event: {event!r}")
    with get_db() as conn:
        record_activity(conn, item_id, event, dwell_seconds if dwell_seconds > 0 else None)
    return {"ok": True}


@router.post("/like/{item_id}")
async def like_item(item_id: int):
    """Toggle like on an item. Liked items boost profile learning."""
    from fastapi import HTTPException

    with get_db() as conn:
        item = get_item_by_id(conn, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        new_state = not item.is_liked
        mark_item_liked(conn, item_id, liked=new_state)
        if new_state:
            record_activity(conn, item_id, "liked")

    return JSONResponse({"liked": new_state})


@router.post("/save/{item_id}")
async def save_item(item_id: int):
    """Toggle saved-for-later state."""
    from fastapi import HTTPException

    with get_db() as conn:
        item = get_item_by_id(conn, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        new_state = not item.is_saved
        mark_item_saved(conn, item_id, saved=new_state)

    return JSONResponse({"saved": new_state})
