import time

from app.db import Item
from app.feed_qa import build_feed_context, build_feed_qa_prompt


def _item() -> Item:
    now = int(time.time())
    return Item(
        id=1,
        source_id=None,
        url="https://example.com/1",
        canonical_url="https://example.com/1",
        title="Robotics release improves planning",
        author=None,
        published_at=now,
        fetched_at=now,
        excerpt="A new robotics toolkit improves motion planning for warehouses.",
        full_text=None,
        cluster_id=None,
        score=8.2,
        rank_rationale="[rank_v1] Strong robotics match.",
        ai_summary=None,
        ai_key_points=None,
        is_read=False,
        total_dwell_seconds=0.0,
        source_title="Robotics Feed",
        topic="robotics",
        is_liked=False,
        is_saved=False,
        ranking_status="ranked",
        ranking_error=None,
        ranked_at=now,
    )


def test_build_feed_context_uses_compact_ranked_metadata():
    context = build_feed_context([_item()])

    assert "[1] Robotics release improves planning" in context
    assert "score: 8.2" in context
    assert "why ranked: Strong robotics match." in context


def test_build_feed_qa_prompt_requires_feed_only_answer():
    prompt = build_feed_qa_prompt("What matters?", [_item()])

    assert "using ONLY the feed items" in prompt
    assert "QUESTION:" in prompt
    assert "What matters?" in prompt
