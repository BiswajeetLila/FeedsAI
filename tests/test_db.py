"""
Smoke tests for app/db.py using in-memory SQLite.
"""
import json
import sqlite3
import time

import pytest

from app.db import (
    get_connection,
    init_schema,
    upsert_source,
    get_all_sources,
    insert_item_if_new,
    get_unranked_items,
    update_item_score,
    update_item_summary,
    get_digest_items,
    get_item_by_id,
    mark_item_read,
    mark_item_saved,
    record_activity,
    record_source_fetch_attempt,
    record_source_fetch_result,
    get_config,
    set_config,
    get_or_create_cluster,
    get_source_fetch_health,
    increment_cluster_member,
    get_recent_items_for_dedup,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """In-memory SQLite connection with schema applied."""
    c = sqlite3.connect(":memory:", timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    # init_schema writes its own connection; for in-memory we apply DDL directly
    from app.db import _SCHEMA_SQL
    c.executescript(_SCHEMA_SQL)
    c.commit()
    yield c
    c.close()


def _make_item(conn, canonical_url="https://example.com/1", score=0.0, cluster_id=None, source_id=None):
    """Helper: insert a minimal item, return its id."""
    now = int(time.time())
    item_id = insert_item_if_new(
        conn,
        source_id=source_id,
        url=canonical_url,
        canonical_url=canonical_url,
        title="Test Item",
        fetched_at=now,
        score=score,
        is_read=0,
        total_dwell_seconds=0.0,
        cluster_id=cluster_id,
    )
    conn.commit()
    return item_id


# ---------------------------------------------------------------------------
# Test 1: init_schema — all tables exist
# ---------------------------------------------------------------------------

def test_init_schema_creates_all_tables(tmp_path):
    """init_schema(real path) — verify all tables and indexes exist."""
    from pathlib import Path

    db_file = tmp_path / "test.db"
    init_schema(db_file)

    c = sqlite3.connect(str(db_file))
    c.row_factory = sqlite3.Row

    tables = {
        row[0]
        for row in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    }
    expected = {"config", "sources", "clusters", "items", "activity", "source_fetch_health"}
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    indexes = {
        row[0]
        for row in c.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for idx in ("idx_items_published", "idx_items_score", "idx_items_fetched"):
        assert idx in indexes, f"Missing index: {idx}"

    c.close()


# ---------------------------------------------------------------------------
# Test 2: insert_item_if_new dedup
# ---------------------------------------------------------------------------

def test_insert_item_dedup(conn):
    """INSERT OR IGNORE: second insert with same canonical_url returns None."""
    now = int(time.time())
    kwargs = dict(
        source_id=None,
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        title="Dedup Article",
        fetched_at=now,
        score=0.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    first_id = insert_item_if_new(conn, **kwargs)
    conn.commit()
    assert first_id is not None
    assert isinstance(first_id, int)

    second_id = insert_item_if_new(conn, **kwargs)
    conn.commit()
    assert second_id is None, "Duplicate canonical_url must return None"


# ---------------------------------------------------------------------------
# Test 3: source upsert and retrieval
# ---------------------------------------------------------------------------

def test_upsert_and_get_sources(conn):
    """Insert a source, retrieve it."""
    sid = upsert_source(
        conn,
        kind="rss",
        url="https://feed.example.com/rss",
        title="Example Feed",
        source_key="rss:https://feed.example.com/rss",
    )
    conn.commit()
    assert isinstance(sid, int)

    sources = get_all_sources(conn)
    assert len(sources) == 1
    s = sources[0]
    assert s.kind == "rss"
    assert s.url == "https://feed.example.com/rss"
    assert s.source_key == "rss:https://feed.example.com/rss"
    assert s.title == "Example Feed"

    # Upsert same URL with updated title — id must be unchanged
    sid2 = upsert_source(conn, kind="rss", url="https://feed.example.com/rss", title="Updated Feed")
    conn.commit()
    assert sid2 == sid
    sources = get_all_sources(conn)
    assert len(sources) == 1
    assert sources[0].title == "Updated Feed"


def test_source_fetch_health_records_last_attempt_result_and_error(conn):
    record_source_fetch_attempt(conn, "rss:https://example.com/feed.xml", "rss", "Example")
    record_source_fetch_result(
        conn,
        "rss:https://example.com/feed.xml",
        "rss",
        "Example",
        items_fetched=5,
        items_new=2,
    )
    record_source_fetch_attempt(conn, "hn:front_page", "hn", "Hacker News")
    record_source_fetch_result(
        conn,
        "hn:front_page",
        "hn",
        "Hacker News",
        items_fetched=0,
        items_new=0,
        error="timeout",
    )
    conn.commit()

    health = get_source_fetch_health(conn)

    assert health["rss:https://example.com/feed.xml"]["items_fetched"] == 5
    assert health["rss:https://example.com/feed.xml"]["items_new"] == 2
    assert health["rss:https://example.com/feed.xml"]["last_error"] is None
    assert health["hn:front_page"]["last_error"] == "timeout"


# ---------------------------------------------------------------------------
# Test 4: record_activity updates total_dwell_seconds
# ---------------------------------------------------------------------------

def test_record_activity_updates_dwell(conn):
    """Record activity with dwell_seconds → items.total_dwell_seconds updated."""
    item_id = _make_item(conn)
    assert item_id is not None

    record_activity(conn, item_id=item_id, event="view", dwell_seconds=30.0)
    record_activity(conn, item_id=item_id, event="view", dwell_seconds=15.5)
    conn.commit()

    item = get_item_by_id(conn, item_id)
    assert item is not None
    assert abs(item.total_dwell_seconds - 45.5) < 0.001

    # Check activity rows exist
    rows = conn.execute("SELECT COUNT(*) as cnt FROM activity WHERE item_id=?", (item_id,)).fetchone()
    assert rows["cnt"] == 2


def test_record_activity_no_dwell(conn):
    """record_activity without dwell_seconds does not change total_dwell_seconds."""
    item_id = _make_item(conn)
    record_activity(conn, item_id=item_id, event="open")
    conn.commit()

    item = get_item_by_id(conn, item_id)
    assert item.total_dwell_seconds == 0.0


# ---------------------------------------------------------------------------
# Test 5: get_digest_items returns top-scored item
# ---------------------------------------------------------------------------

def test_get_digest_items_top_score(conn):
    """get_digest_items returns highest-scored items first."""
    now = int(time.time())

    id_low = insert_item_if_new(
        conn,
        url="https://example.com/low",
        canonical_url="https://example.com/low",
        title="Low Score",
        fetched_at=now,
        score=1.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    id_high = insert_item_if_new(
        conn,
        url="https://example.com/high",
        canonical_url="https://example.com/high",
        title="High Score",
        fetched_at=now,
        score=9.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    id_mid = insert_item_if_new(
        conn,
        url="https://example.com/mid",
        canonical_url="https://example.com/mid",
        title="Mid Score",
        fetched_at=now,
        score=5.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    conn.commit()

    items = get_digest_items(conn, hours=24, limit=10)
    assert len(items) == 3
    assert items[0].id == id_high
    assert items[0].score == 9.0
    assert items[1].score == 5.0
    assert items[2].score == 1.0


def test_get_digest_items_one_per_cluster(conn):
    """get_digest_items returns only one item per cluster (highest score)."""
    now = int(time.time())

    # Insert two items that will share a cluster
    id1 = insert_item_if_new(
        conn,
        url="https://example.com/c1a",
        canonical_url="https://example.com/c1a",
        title="Cluster 1 - A",
        fetched_at=now,
        score=7.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    id2 = insert_item_if_new(
        conn,
        url="https://example.com/c1b",
        canonical_url="https://example.com/c1b",
        title="Cluster 1 - B",
        fetched_at=now,
        score=3.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    conn.commit()

    # Create a cluster and assign both items
    cluster_id = get_or_create_cluster(conn, representative_item_id=id1)
    conn.execute("UPDATE items SET cluster_id=? WHERE id=?", (cluster_id, id2))
    conn.commit()

    # One item in its own "cluster" (no cluster_id)
    id3 = insert_item_if_new(
        conn,
        url="https://example.com/solo",
        canonical_url="https://example.com/solo",
        title="Solo Item",
        fetched_at=now,
        score=5.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    conn.commit()

    items = get_digest_items(conn, hours=24, limit=10)
    # Should return 2 items: best from cluster (score=7.0) + solo (score=5.0)
    assert len(items) == 2
    scores = {i.score for i in items}
    assert 7.0 in scores
    assert 5.0 in scores
    assert 3.0 not in scores


def test_get_digest_items_saved_only(conn):
    now = int(time.time())

    saved_id = insert_item_if_new(
        conn,
        url="https://example.com/saved",
        canonical_url="https://example.com/saved",
        title="Saved",
        fetched_at=now,
        score=9.0,
        is_saved=1,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    insert_item_if_new(
        conn,
        url="https://example.com/unsaved",
        canonical_url="https://example.com/unsaved",
        title="Unsaved",
        fetched_at=now,
        score=8.0,
        is_saved=0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    conn.commit()

    items = get_digest_items(conn, hours=24, limit=10, saved_only=True)

    assert [item.id for item in items] == [saved_id]
    assert items[0].is_saved is True


# ---------------------------------------------------------------------------
# Test 6: update_item_score and update_item_summary
# ---------------------------------------------------------------------------

def test_update_item_score(conn):
    item_id = _make_item(conn)
    update_item_score(conn, item_id, score=8.5, rationale="Very relevant", prompt_version="v1")
    conn.commit()

    item = get_item_by_id(conn, item_id)
    assert item.score == 8.5
    assert "[v1]" in item.rank_rationale
    assert "Very relevant" in item.rank_rationale


def test_update_item_summary(conn):
    item_id = _make_item(conn)
    update_item_summary(conn, item_id, summary="Great article", key_points=["point A", "point B"])
    conn.commit()

    item = get_item_by_id(conn, item_id)
    assert item.ai_summary == "Great article"
    key_points = json.loads(item.ai_key_points)
    assert key_points == ["point A", "point B"]


# ---------------------------------------------------------------------------
# Test 7: mark_item_read
# ---------------------------------------------------------------------------

def test_mark_item_read(conn):
    item_id = _make_item(conn)
    item = get_item_by_id(conn, item_id)
    assert item.is_read == False

    mark_item_read(conn, item_id)
    conn.commit()

    item = get_item_by_id(conn, item_id)
    assert item.is_read == True


def test_mark_item_saved(conn):
    item_id = _make_item(conn)
    item = get_item_by_id(conn, item_id)
    assert item.is_saved == False

    mark_item_saved(conn, item_id, saved=True)
    conn.commit()

    item = get_item_by_id(conn, item_id)
    assert item.is_saved == True

    mark_item_saved(conn, item_id, saved=False)
    conn.commit()

    item = get_item_by_id(conn, item_id)
    assert item.is_saved == False


# ---------------------------------------------------------------------------
# Test 8: config get/set
# ---------------------------------------------------------------------------

def test_config_get_set(conn):
    assert get_config(conn, "missing_key") is None
    assert get_config(conn, "missing_key", default="fallback") == "fallback"

    set_config(conn, "last_run", "2026-01-01T00:00:00")
    conn.commit()

    assert get_config(conn, "last_run") == "2026-01-01T00:00:00"

    # Overwrite
    set_config(conn, "last_run", "2026-06-01T12:00:00")
    conn.commit()
    assert get_config(conn, "last_run") == "2026-06-01T12:00:00"


# ---------------------------------------------------------------------------
# Test 9: get_unranked_items
# ---------------------------------------------------------------------------

def test_get_unranked_items(conn):
    now = int(time.time())

    # Unranked (score=0.0, recent)
    insert_item_if_new(
        conn,
        url="https://example.com/unranked",
        canonical_url="https://example.com/unranked",
        title="Unranked",
        fetched_at=now,
        score=0.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    # Already ranked
    insert_item_if_new(
        conn,
        url="https://example.com/ranked",
        canonical_url="https://example.com/ranked",
        title="Ranked",
        fetched_at=now,
        score=5.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    conn.commit()

    unranked = get_unranked_items(conn, since_hours=24)
    assert len(unranked) == 1
    assert unranked[0].title == "Unranked"


# ---------------------------------------------------------------------------
# Test 10: get_recent_items_for_dedup
# ---------------------------------------------------------------------------

def test_get_recent_items_for_dedup(conn):
    now = int(time.time())
    old_time = now - 8 * 86400  # 8 days ago

    insert_item_if_new(
        conn,
        url="https://example.com/recent",
        canonical_url="https://example.com/recent",
        title="Recent",
        fetched_at=now,
        score=0.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    insert_item_if_new(
        conn,
        url="https://example.com/old",
        canonical_url="https://example.com/old",
        title="Old",
        fetched_at=old_time,
        score=0.0,
        is_read=0,
        total_dwell_seconds=0.0,
    )
    conn.commit()

    recent = get_recent_items_for_dedup(conn, days=7)
    assert len(recent) == 1
    assert recent[0].title == "Recent"


# ---------------------------------------------------------------------------
# Test 11: cluster helpers
# ---------------------------------------------------------------------------

def test_cluster_create_and_update(conn):
    item_id = _make_item(conn)

    cluster_id = get_or_create_cluster(conn, representative_item_id=item_id)
    conn.commit()
    assert isinstance(cluster_id, int)

    # The representative item should now have cluster_id set
    item = get_item_by_id(conn, item_id)
    assert item.cluster_id == cluster_id

    # Increment member count by 2 (starts at 1, so should become 3)
    increment_cluster_member(conn, cluster_id=cluster_id, delta=2)
    conn.commit()

    row = conn.execute("SELECT member_count FROM clusters WHERE id=?", (cluster_id,)).fetchone()
    assert row["member_count"] == 3
