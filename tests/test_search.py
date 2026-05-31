import sqlite3
import time

from app.db import _SCHEMA_SQL, insert_item_if_new, update_item_score, upsert_source
from app.search import init_search_schema, rebuild_search_index, search_items


def _conn():
    conn = sqlite3.connect(":memory:", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    init_search_schema(conn)
    return conn


def test_search_finds_items_by_title_excerpt_rationale_source_and_topic():
    conn = _conn()
    try:
        source_id = upsert_source(conn, "rss", "https://robotics.example/feed", "Robotics Weekly")
        now = int(time.time())
        item_id = insert_item_if_new(
            conn,
            source_id=source_id,
            url="https://example.com/robot",
            canonical_url="https://example.com/robot",
            title="Warehouse automation launch",
            fetched_at=now,
            published_at=now,
            excerpt="Mobile robot planning details.",
            score=0.0,
            is_read=0,
            total_dwell_seconds=0.0,
        )
        update_item_score(conn, item_id, 8.0, "Strong hardware robotics match", "rank_v1", topic="robotics")
        rebuild_search_index(conn)

        by_title = search_items(conn, "automation")
        by_rationale = search_items(conn, "hardware")
        by_source = search_items(conn, "Robotics Weekly")
        by_topic = search_items(conn, "robotics")
    finally:
        conn.close()

    assert [item.id for item in by_title] == [item_id]
    assert [item.id for item in by_rationale] == [item_id]
    assert [item.id for item in by_source] == [item_id]
    assert [item.id for item in by_topic] == [item_id]


def test_search_can_filter_saved_items():
    conn = _conn()
    try:
        now = int(time.time())
        saved_id = insert_item_if_new(
            conn,
            source_id=None,
            url="https://example.com/saved",
            canonical_url="https://example.com/saved",
            title="Planning research",
            fetched_at=now,
            excerpt="Robot planning",
            score=7.0,
            is_read=0,
            is_saved=1,
            total_dwell_seconds=0.0,
        )
        insert_item_if_new(
            conn,
            source_id=None,
            url="https://example.com/unsaved",
            canonical_url="https://example.com/unsaved",
            title="Planning note",
            fetched_at=now,
            excerpt="Robot planning",
            score=7.0,
            is_read=0,
            is_saved=0,
            total_dwell_seconds=0.0,
        )
        rebuild_search_index(conn)

        results = search_items(conn, "planning", saved_only=True)
    finally:
        conn.close()

    assert [item.id for item in results] == [saved_id]


def test_search_index_updates_when_items_are_inserted_and_ranked():
    conn = _conn()
    try:
        now = int(time.time())
        item_id = insert_item_if_new(
            conn,
            source_id=None,
            url="https://example.com/new",
            canonical_url="https://example.com/new",
            title="Fresh autonomy note",
            fetched_at=now,
            excerpt="Mobile robots",
            score=0.0,
            is_read=0,
            total_dwell_seconds=0.0,
        )

        assert [item.id for item in search_items(conn, "autonomy")] == [item_id]

        update_item_score(conn, item_id, 7.0, "Relevant warehouse planning", "rank_v1", topic="robotics")

        assert [item.id for item in search_items(conn, "warehouse")] == [item_id]
    finally:
        conn.close()
