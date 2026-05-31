import sqlite3
import time

from app.db import _SCHEMA_SQL, get_item_by_id, insert_item_if_new, upsert_source
from app.explain import build_item_explanation, matched_profile_interests


def test_matched_profile_interests_uses_profile_bullets_against_item_text():
    profile_md = """
## Tier 1
- Robotics demos with hardware details
- Space missions and propulsion
"""
    item_text = "Warehouse robotics launch includes hardware details and motion planning."

    matches = matched_profile_interests(profile_md, item_text)

    assert matches == ["Robotics demos with hardware details"]


def test_build_item_explanation_includes_score_source_quality_and_flags():
    conn = sqlite3.connect(":memory:", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    try:
        source_id = upsert_source(conn, "rss", "https://example.com/feed", "Example")
        now = int(time.time())
        item_id = insert_item_if_new(
            conn,
            source_id=source_id,
            url="https://example.com/1",
            canonical_url="https://example.com/1",
            title="Shocking top 10 robotics demo",
            fetched_at=now,
            published_at=now,
            excerpt="Thin.",
            score=8.0,
            rank_rationale="[rank_v1] Strong robotics match",
            is_read=0,
            total_dwell_seconds=0.0,
        )
        item = get_item_by_id(conn, item_id)
        explanation = build_item_explanation(
            conn,
            item,
            profile_md="- Robotics demos with hardware details",
            cluster_size=2,
        )
    finally:
        conn.close()

    assert explanation["score"] == 8.0
    assert explanation["tier_label"] == "Top pick"
    assert explanation["source_quality_score"] >= 8.0
    assert "clickbait wording" in explanation["low_signal_flags"]
    assert explanation["cluster_size"] == 2
    assert explanation["matched_interests"] == ["Robotics demos with hardware details"]
