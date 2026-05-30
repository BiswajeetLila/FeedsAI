import time

from app.db import Item
from app.digest_modes import apply_digest_mode, normalize_digest_mode


def _item(item_id: int, *, score: float, topic: str, source: str, published_at: int) -> Item:
    return Item(
        id=item_id,
        source_id=None,
        url=f"https://example.com/{item_id}",
        canonical_url=f"https://example.com/{item_id}",
        title=f"Item {item_id}",
        author=None,
        published_at=published_at,
        fetched_at=published_at,
        excerpt="Excerpt",
        full_text=None,
        cluster_id=None,
        score=score,
        rank_rationale=None,
        ai_summary=None,
        ai_key_points=None,
        is_read=False,
        total_dwell_seconds=0.0,
        source_title=source,
        topic=topic,
        is_liked=False,
        is_saved=False,
        ranking_status="ranked",
        ranking_error=None,
        ranked_at=published_at,
    )


def test_normalize_digest_mode_defaults_unknown_values():
    assert normalize_digest_mode("balanced") == "balanced"
    assert normalize_digest_mode("weird") == "ranked"


def test_fresh_mode_orders_by_recency_before_score():
    now = int(time.time())
    older_high = _item(1, score=9.0, topic="ai", source="A", published_at=now - 3600)
    fresh_low = _item(2, score=6.0, topic="ai", source="A", published_at=now)

    assert apply_digest_mode([older_high, fresh_low], "fresh")[0].id == 2


def test_balanced_mode_penalizes_repeated_topic_and_source():
    now = int(time.time())
    items = [
        _item(1, score=9.0, topic="ai", source="A", published_at=now),
        _item(2, score=8.8, topic="ai", source="A", published_at=now),
        _item(3, score=8.6, topic="robotics", source="B", published_at=now),
    ]

    ordered = apply_digest_mode(items, "balanced")

    assert [item.id for item in ordered[:2]] == [1, 3]
