import time

from app.db import Item
from app.reason_labels import build_reason_chips, clean_rationale


def _item(**overrides) -> Item:
    now = int(time.time())
    data = {
        "id": 1,
        "source_id": None,
        "url": "https://example.com",
        "canonical_url": "https://example.com",
        "title": "New robotics benchmark release",
        "author": None,
        "published_at": now,
        "fetched_at": now,
        "excerpt": "A practical evaluation of robot planning performance.",
        "full_text": None,
        "cluster_id": None,
        "score": 8.5,
        "rank_rationale": "[rank_v1] Strong match to robotics interests.",
        "ai_summary": None,
        "ai_key_points": None,
        "is_read": False,
        "total_dwell_seconds": 0.0,
        "source_title": "Test Feed",
        "topic": "robotics",
        "is_liked": False,
        "is_saved": False,
        "ranking_status": "ranked",
        "ranking_error": None,
        "ranked_at": now,
    }
    data.update(overrides)
    return Item(**data)


def test_clean_rationale_strips_prompt_version():
    assert clean_rationale("[rank_v1] Useful because it matches") == "Useful because it matches"


def test_build_reason_chips_uses_existing_metadata_only():
    chips = build_reason_chips(_item(), cluster_size=2, now=int(time.time()), limit=4)

    assert chips == ["Top fit", "Robotics", "Fresh", "Developing"]


def test_build_reason_chips_adds_keyword_label_when_space_available():
    chips = build_reason_chips(
        _item(topic=None, published_at=int(time.time()) - 90000),
        cluster_size=None,
        now=int(time.time()),
        limit=4,
    )

    assert "Release" in chips
    assert "Benchmark" in chips
