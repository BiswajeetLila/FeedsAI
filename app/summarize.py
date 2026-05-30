"""
No-LLM item insight helpers.

The old implementation generated article summaries through Gemini/Claude.
That made drawer opens slow and spent tokens on content the feed already
provided. Keep this module as a compatibility layer, but never call an LLM.
"""
import json
import sqlite3

from app.db import Item
from app.reason_labels import clean_rationale


def build_item_insight(item: Item) -> tuple[str, list[str]]:
    """
    Return instant reader context from feed metadata and ranking output.
    No LLM call, no network, no DB write.
    """
    body = (item.excerpt or "").strip() or (
        "No excerpt available. Open the original article for the full text."
    )

    points: list[str] = []
    rationale = clean_rationale(item.rank_rationale)
    if rationale:
        points.append(f"Why it was picked: {rationale}")
    if item.topic:
        points.append(f"Topic: {item.topic}")
    if item.score > 0:
        points.append(f"Score: {item.score:.1f}/10")

    return body, points


async def summarize_item(item: Item, conn: sqlite3.Connection) -> tuple[str, list[str]]:
    """
    Backwards-compatible no-LLM summary API.

    Existing callers still get a `(text, points)` tuple, but the content comes
    from cached fields only. If a previous DB has an old cached summary, return
    it without generating new summaries.
    """
    if item.ai_summary:
        key_points: list[str] = []
        if item.ai_key_points:
            try:
                decoded = json.loads(item.ai_key_points)
                if isinstance(decoded, list):
                    key_points = [str(point) for point in decoded]
            except (json.JSONDecodeError, TypeError):
                key_points = []
        return item.ai_summary, key_points

    return build_item_insight(item)
