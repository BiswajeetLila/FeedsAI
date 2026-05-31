import sqlite3
import time

from app.db import (
    _SCHEMA_SQL,
    insert_item_if_new,
    mark_item_liked,
    mark_item_saved,
    record_activity,
    upsert_source,
)
from app.learning import get_learning_dashboard
from app.profile_update import MIN_SIGNALS_FOR_UPDATE


def test_learning_dashboard_summarizes_engagement_topics_sources_and_readiness():
    conn = sqlite3.connect(":memory:", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    try:
        source_id = upsert_source(conn, "rss", "https://example.com/feed", "Example")
        now = int(time.time())
        item_id = insert_item_if_new(
            conn,
            source_id=source_id,
            url="https://example.com/robot",
            canonical_url="https://example.com/robot",
            title="Robotics planning",
            fetched_at=now,
            excerpt="Hardware details",
            score=8.0,
            rank_rationale="Strong robotics match",
            is_read=0,
            total_dwell_seconds=0.0,
        )
        conn.execute("UPDATE items SET topic='robotics' WHERE id=?", (item_id,))
        mark_item_liked(conn, item_id, True)
        mark_item_saved(conn, item_id, True)
        record_activity(conn, item_id, "opened")
        record_activity(conn, item_id, "linked_out")
        record_activity(conn, item_id, "liked")
        conn.commit()

        dashboard = get_learning_dashboard(conn, days=7)
    finally:
        conn.close()

    assert dashboard["top_topics"][0]["topic"] == "robotics"
    assert dashboard["top_sources"][0]["source_title"] == "Example"
    assert dashboard["most_liked"][0]["title"] == "Robotics planning"
    assert dashboard["most_saved"][0]["title"] == "Robotics planning"
    assert dashboard["signals_needed"] == max(0, MIN_SIGNALS_FOR_UPDATE - dashboard["total_signals"])
