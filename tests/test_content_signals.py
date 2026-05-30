import time

from app.content_signals import is_low_signal, low_signal_reasons, novelty_label
from app.db import Item


def _item(**overrides) -> Item:
    now = int(time.time())
    data = {
        "id": 1,
        "source_id": None,
        "url": "https://example.com",
        "canonical_url": "https://example.com",
        "title": "Shocking top 10 AI secrets",
        "author": None,
        "published_at": now,
        "fetched_at": now,
        "excerpt": "Thin.",
        "full_text": None,
        "cluster_id": None,
        "score": 3.0,
        "rank_rationale": None,
        "ai_summary": None,
        "ai_key_points": None,
        "is_read": False,
        "total_dwell_seconds": 0.0,
        "source_title": "Test Feed",
        "topic": "ai",
        "is_liked": False,
        "is_saved": False,
        "ranking_status": "ranked",
        "ranking_error": None,
        "ranked_at": now,
    }
    data.update(overrides)
    return Item(**data)


def test_low_signal_hides_only_low_score_junk():
    item = _item()

    assert "clickbait wording" in low_signal_reasons(item)
    assert is_low_signal(item) is True


def test_low_signal_never_hides_saved_or_high_score_items():
    assert is_low_signal(_item(is_saved=True)) is False
    assert is_low_signal(_item(score=8.0)) is False


def test_novelty_label_prefers_unclustered_fresh_high_score_items():
    now = int(time.time())

    assert novelty_label(_item(score=7.5), cluster_size=None, now=now) == "Novel"
    assert novelty_label(_item(score=7.5), cluster_size=3, now=now) == ""
