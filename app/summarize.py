"""
app/summarize.py
AI summarization logic for individual feed items.
"""
import html as html_lib
import json
import logging
import sqlite3
from pathlib import Path

from app.db import Item, update_item_summary
from app.llm import LLMResult, call_llm

logger = logging.getLogger(__name__)

PROMPT_VERSION = "summarize_v1"
_PROMPT_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "summarize_v1.txt").read_text()


async def summarize_item(item: Item, conn: sqlite3.Connection) -> tuple[str, list[str]]:
    """
    Generate AI summary for item. Caches result in DB.
    Returns (summary_text, key_points_list).

    If item.ai_summary is already set: return cached version without LLM call.
    Otherwise: call LLM, parse JSON, store via update_item_summary, return.

    On LLM error or JSON parse failure: return (fallback_text, []) where
    fallback_text = item.excerpt or "Summary unavailable."
    Never raises.
    """
    # --- Return cached summary if available ---
    if item.ai_summary:
        key_points: list[str] = []
        if item.ai_key_points:
            try:
                key_points = json.loads(item.ai_key_points)
            except (json.JSONDecodeError, TypeError):
                key_points = []
        return item.ai_summary, key_points

    fallback = item.excerpt or "Summary unavailable."

    # --- Build prompt using str.replace to avoid JSON brace issues ---
    prompt = (
        _PROMPT_TEMPLATE
        .replace("{title}", item.title or "")
        .replace("{excerpt}", item.excerpt or "")
        .replace("{url}", item.url or "")
    )

    # --- Call LLM (gemini-first for summaries; claude fallback) ---
    try:
        result: LLMResult = await call_llm(prompt, prefer="gemini")
    except Exception as exc:
        logger.warning("summarize_item: unexpected exception calling LLM for item %d: %s", item.id, exc)
        return fallback, []

    if result.error is not None:
        logger.warning(
            "summarize_item: LLM error=%r for item %d; using fallback",
            result.error,
            item.id,
        )
        return fallback, []

    # --- Parse JSON response ---
    try:
        # Strip markdown code fences if present
        text = result.text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first and last fence lines
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(text)
        summary: str = data["summary"]
        key_points_raw = data.get("key_points", [])
        if not isinstance(key_points_raw, list):
            key_points_raw = []
        key_points = [str(p) for p in key_points_raw]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "summarize_item: JSON parse failed for item %d: %s; using fallback",
            item.id,
            exc,
        )
        return fallback, []

    # --- Persist to DB ---
    try:
        update_item_summary(conn, item.id, summary, key_points)
    except Exception as exc:
        logger.warning("summarize_item: failed to persist summary for item %d: %s", item.id, exc)
        # Still return the summary even if we can't persist

    return summary, key_points
