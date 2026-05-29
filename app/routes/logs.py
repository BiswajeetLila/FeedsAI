"""
app/routes/logs.py
Live log tail page. Reads from the in-process ring buffer (no disk hit).
Auto-refreshes every 3s via meta-refresh; also has an HTMX endpoint for
in-place updates.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from app import observability
from app.templates_config import templates

router = APIRouter()


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, n: int = 200):
    lines = observability.tail_logs(n)
    return templates.TemplateResponse(
        request,
        "logs.html",
        {"lines": lines, "n": n},
    )


@router.get("/logs.txt", response_class=PlainTextResponse)
async def logs_plain(n: int = 200):
    return "\n".join(observability.tail_logs(n))
