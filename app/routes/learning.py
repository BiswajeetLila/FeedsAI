"""
Learning dashboard route.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.db import get_db
from app.learning import get_learning_dashboard
from app.templates_config import templates

router = APIRouter()


@router.get("/learning", response_class=HTMLResponse)
async def learning_page(request: Request):
    with get_db() as conn:
        dashboard = get_learning_dashboard(conn)
    return templates.TemplateResponse(
        request,
        "learning.html",
        {"dashboard": dashboard},
    )
