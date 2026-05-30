"""
Source quality route.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.db import get_db
from app.source_quality import get_source_quality
from app.templates_config import templates

router = APIRouter()


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    with get_db() as conn:
        sources = get_source_quality(conn)
    return templates.TemplateResponse(
        request,
        "source_quality.html",
        {"sources": sources},
    )
