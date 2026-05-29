"""
app/routes/items.py
Item detail, summary, and activity routes.
"""
import html
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.db import get_db, get_item_by_id, mark_item_liked, mark_item_read, record_activity
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/item/{item_id}/summary", response_class=HTMLResponse)
async def item_summary(request: Request, item_id: int):
    """
    HTMX partial: returns summary HTML for drawer.
    If no summary yet: generates it (may take 5-30s).
    Returns a loading state or the actual summary.
    """
    from app.summarize import summarize_item

    with get_db() as conn:
        item = get_item_by_id(conn, item_id)
        if not item:
            return HTMLResponse("<p>Item not found.</p>", status_code=404)

        summary, key_points = await summarize_item(item, conn)
        mark_item_read(conn, item_id)

    escaped_summary = html.escape(summary)
    escaped_points = [html.escape(p) for p in key_points]
    liked_class = "like-btn liked" if item.is_liked else "like-btn"
    liked_label = "&#10084; Liked" if item.is_liked else "&#9825; Like"

    bullets = "".join(f"<li>{p}</li>" for p in escaped_points)
    html_content = f"""
    <div class="summary-content">
        <p>{escaped_summary}</p>
        {"<ul>" + bullets + "</ul>" if bullets else ""}
        <div class="drawer-actions">
            <button class="{liked_class}" data-item-id="{item_id}"
                    onclick="likeArticle({item_id}, this)">
                {liked_label}
            </button>
        </div>
    </div>
    """
    return HTMLResponse(html_content)


@router.get("/item/{item_id}", response_class=HTMLResponse)
async def item_detail(request: Request, item_id: int):
    """Show item detail page with full summary (for mobile / direct link)."""
    from app.summarize import summarize_item

    with get_db() as conn:
        item = get_item_by_id(conn, item_id)
        if not item:
            return HTMLResponse("<p>Item not found.</p>", status_code=404)

        summary, key_points = await summarize_item(item, conn)
        mark_item_read(conn, item_id)

    escaped_summary = html.escape(summary)
    escaped_points = [html.escape(p) for p in key_points]
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
          <p>{escaped_summary}</p>
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
    VALID_EVENTS = {"viewed", "opened", "linked_out", "liked"}
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
