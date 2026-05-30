"""
Ask-your-feed support.

The LLM is used only when the user asks a question. Context is compact recent
feed metadata, not full article text or generated summaries.
"""
import sqlite3

from app.db import Item, get_digest_items
from app.llm import call_llm
from app.reason_labels import clean_rationale

_PROMPT_TEMPLATE = """\
Answer the user's question using ONLY the feed items below.
If the items do not contain enough evidence, say what is missing.
Keep the answer concise. Cite item numbers like [1] when making claims.

QUESTION:
{question}

FEED ITEMS:
{context}
"""


def build_feed_context(items: list[Item]) -> str:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        excerpt = (item.excerpt or "").strip()[:280]
        rationale = clean_rationale(item.rank_rationale)[:180]
        parts = [
            f"[{index}] {item.title}",
            f"url: {item.url}",
            f"source: {item.source_title or 'unknown'}",
            f"topic: {item.topic or 'other'}",
            f"score: {item.score:.1f}",
        ]
        if excerpt:
            parts.append(f"excerpt: {excerpt}")
        if rationale:
            parts.append(f"why ranked: {rationale}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def build_feed_qa_prompt(question: str, items: list[Item]) -> str:
    return _PROMPT_TEMPLATE.format(
        question=question.strip(),
        context=build_feed_context(items) or "(no recent feed items)",
    )


async def answer_feed_question(
    conn: sqlite3.Connection,
    question: str,
    *,
    days: int = 7,
    limit: int = 25,
) -> tuple[str, list[Item], str | None]:
    items = get_digest_items(conn, hours=days * 24, limit=limit, offset=0)
    answer, error = await answer_feed_question_from_items(question, items)
    return answer, items, error


async def answer_feed_question_from_items(
    question: str,
    items: list[Item],
) -> tuple[str, str | None]:
    prompt = build_feed_qa_prompt(question, items)
    result = await call_llm(prompt, timeout=90)
    if result.error is not None:
        return "", result.error
    return result.text.strip(), None
