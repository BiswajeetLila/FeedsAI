import sqlite3
import time

from app.db import _SCHEMA_SQL, insert_item_if_new, record_activity, upsert_source
from app.source_quality import get_source_quality


def test_get_source_quality_scores_sources_from_rank_and_engagement():
    conn = sqlite3.connect(":memory:", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    try:
        source_id = upsert_source(conn, kind="rss", url="https://example.com/feed", title="Example")
        now = int(time.time())
        item_id = insert_item_if_new(
            conn,
            source_id=source_id,
            url="https://example.com/1",
            canonical_url="https://example.com/1",
            title="Example item",
            fetched_at=now,
            score=8.0,
            is_read=0,
            total_dwell_seconds=0.0,
        )
        conn.execute("UPDATE items SET is_liked=1, is_saved=1 WHERE id=?", (item_id,))
        record_activity(conn, item_id, "opened")
        record_activity(conn, item_id, "linked_out")
        conn.commit()

        sources = get_source_quality(conn)
    finally:
        conn.close()

    assert len(sources) == 1
    assert sources[0]["title"] == "Example"
    assert sources[0]["avg_score"] == 8.0
    assert sources[0]["liked_count"] == 1
    assert sources[0]["quality_score"] > 8.0
