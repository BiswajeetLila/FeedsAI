"""
Ask-your-feed route.
"""
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.db import get_db, get_digest_items
from app.feed_qa import answer_feed_question_from_items
from app.templates_config import templates

router = APIRouter()


@router.get("/ask", response_class=HTMLResponse)
async def ask_page(request: Request):
    return templates.TemplateResponse(
        request,
        "ask.html",
        {"question": "", "answer": "", "error": "", "items_used": []},
    )


@router.post("/ask", response_class=HTMLResponse)
async def ask_submit(request: Request, question: str = Form(...)):
    clean_question = question.strip()
    answer = ""
    error = ""
    items_used = []

    if clean_question:
        with get_db() as conn:
            items_used = get_digest_items(conn, hours=7 * 24, limit=25, offset=0)
        answer, error = await answer_feed_question_from_items(clean_question, items_used)

    return templates.TemplateResponse(
        request,
        "ask.html",
        {
            "question": clean_question,
            "answer": answer,
            "error": error or "",
            "items_used": items_used,
        },
    )
