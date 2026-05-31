"""
Local search route.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.db import get_db
from app.search import search_items
from app.templates_config import templates

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = "",
    topic: str = "",
    saved: int = 0,
    unread: int = 0,
):
    results = []
    if q.strip():
        with get_db() as conn:
            results = search_items(
                conn,
                q,
                topic=topic or None,
                saved_only=saved == 1,
                unread_only=unread == 1,
            )
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "q": q,
            "results": results,
            "topic": topic,
            "saved": saved == 1,
            "unread": unread == 1,
        },
    )
