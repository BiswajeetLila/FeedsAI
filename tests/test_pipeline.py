"""
Integration tests for app/pipeline.py.

Uses unittest.mock.patch for httpx/feedparser-level mocking and in-memory
(tmp_path) SQLite to avoid cross-test pollution.
"""
import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db import _SCHEMA_SQL, init_schema
from app.ingest.rss import RawItem
from app.llm import LLMResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_item(n: int) -> RawItem:
    return RawItem(
        url=f"https://example.com/article/{n}",
        canonical_url=f"https://example.com/article/{n}",
        title=f"Article {n}",
        author=None,
        published_at=int(time.time()),
        excerpt=f"Excerpt for article {n}.",
        source_title="Test Feed",
    )


def _make_rank_result(items: list[RawItem]) -> LLMResult:
    """Build a mock LLM ranking response for the given raw items."""
    # We need item IDs but don't have them yet at call time — use a dynamic mock instead.
    # Return a result that assigns score 7.0 to all items by parsing the prompt.
    return LLMResult(
        text=json.dumps({"rankings": []}),  # empty — overridden by dynamic mock
        model_used="claude",
        error=None,
    )


def _rank_llm_response(prompt: str) -> LLMResult:
    """Parse item IDs out of the rank prompt and return valid rankings for them."""
    try:
        # The prompt contains items_json; extract from it
        start = prompt.index("[{")
        end = prompt.rindex("}]") + 2
        items_json = prompt[start:end]
        items = json.loads(items_json)
        rankings = [{"id": item["id"], "score": 7.0, "rationale": "Good"} for item in items]
        return LLMResult(
            text=json.dumps({"rankings": rankings}),
            model_used="claude",
            error=None,
        )
    except Exception:
        return LLMResult(text=json.dumps({"rankings": []}), model_used="claude", error=None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a fresh DB file with schema applied."""
    db_file = tmp_path / "test_feeds.db"
    init_schema(db_file)
    return db_file


@pytest.fixture
def tmp_lock(tmp_path: Path) -> Path:
    return tmp_path / "fetch.lock"


@pytest.fixture
def tmp_last_fetch(tmp_path: Path) -> Path:
    return tmp_path / "last_fetch.txt"


@pytest.fixture
def profile_file(tmp_path: Path) -> Path:
    p = tmp_path / "profile.md"
    p.write_text("I like AI and technology.", encoding="utf-8")
    return p


@pytest.fixture
def sources_file(tmp_path: Path) -> Path:
    """A minimal valid sources.yaml with one RSS source."""
    p = tmp_path / "sources.yaml"
    p.write_text(
        "schema_version: 1\nsources:\n  - kind: rss\n    url: https://example.com/feed.rss\n    title: Test Feed\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Test 1: Full pipeline run — items inserted and ranked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_full_run(tmp_db, tmp_lock, tmp_last_fetch, profile_file, sources_file):
    """
    Full pipeline run with mocked fetch_source and rank_items.
    Assert items_new=2, items_ranked>0, last_fetch.txt written.
    """
    raw_items = [_make_raw_item(1), _make_raw_item(2)]

    with (
        patch("app.pipeline._LOCK_FILE", tmp_lock),
        patch("app.pipeline._LAST_FETCH_FILE", tmp_last_fetch),
        patch("app.pipeline.fetch_source", return_value=raw_items),
        patch("app.rank.call_llm", new=AsyncMock(side_effect=_rank_llm_response)),
    ):
        from app.pipeline import run_fetch_cycle

        report = await run_fetch_cycle(
            sources_path=str(sources_file),
            profile_path=str(profile_file),
            db_path=tmp_db,
        )

    assert report.items_new == 2, f"Expected 2 new items, got {report.items_new}"
    assert report.sources_attempted == 1
    assert report.items_fetched == 2
    assert len(report.errors) == 0

    # last_fetch.txt must have been written
    assert tmp_last_fetch.exists(), "last_fetch.txt was not created"
    content = tmp_last_fetch.read_text()
    assert "T" in content, f"Unexpected last_fetch.txt content: {content!r}"


# ---------------------------------------------------------------------------
# Test 2: Filelock prevents double run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_filelock_prevents_double_run(tmp_db, tmp_lock, tmp_last_fetch, profile_file, sources_file):
    """
    Manually acquire the lock before calling run_fetch_cycle.
    The pipeline should detect the lock and return an empty report immediately.
    """
    from filelock import FileLock

    tmp_lock.parent.mkdir(parents=True, exist_ok=True)
    held_lock = FileLock(str(tmp_lock), timeout=0)
    held_lock.acquire()

    try:
        with (
            patch("app.pipeline._LOCK_FILE", tmp_lock),
            patch("app.pipeline._LAST_FETCH_FILE", tmp_last_fetch),
        ):
            from app.pipeline import run_fetch_cycle

            report = await run_fetch_cycle(
                sources_path=str(sources_file),
                profile_path=str(profile_file),
                db_path=tmp_db,
            )
    finally:
        held_lock.release()

    # Should return early — empty report
    assert report.items_new == 0
    assert report.sources_attempted == 0
    assert report.items_fetched == 0
    assert not tmp_last_fetch.exists(), "last_fetch.txt should NOT be written when lock is held"


# ---------------------------------------------------------------------------
# Test 3: One source fails, others succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_partial_source_failure(tmp_db, tmp_lock, tmp_last_fetch, profile_file, tmp_path):
    """
    Two sources configured. fetch_source raises for the first, succeeds for the second.
    Errors list must have 1 entry; items from good source are still inserted.
    """
    # Two sources in the yaml
    sources_yaml = tmp_path / "sources2.yaml"
    sources_yaml.write_text(
        (
            "schema_version: 1\nsources:\n"
            "  - kind: rss\n    url: https://fail.example.com/feed.rss\n    title: Bad Feed\n"
            "  - kind: rss\n    url: https://good.example.com/feed.rss\n    title: Good Feed\n"
        ),
        encoding="utf-8",
    )

    good_items = [_make_raw_item(10), _make_raw_item(11)]
    call_count = 0

    def _fetch_side_effect(source):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Network failure for bad source")
        return good_items

    with (
        patch("app.pipeline._LOCK_FILE", tmp_lock),
        patch("app.pipeline._LAST_FETCH_FILE", tmp_last_fetch),
        patch("app.pipeline.fetch_source", side_effect=_fetch_side_effect),
        patch("app.rank.call_llm", new=AsyncMock(side_effect=_rank_llm_response)),
    ):
        from app.pipeline import run_fetch_cycle

        report = await run_fetch_cycle(
            sources_path=str(sources_yaml),
            profile_path=str(profile_file),
            db_path=tmp_db,
        )

    assert len(report.errors) == 1, f"Expected 1 error, got {report.errors}"
    assert report.items_new == 2, f"Expected 2 new items from good source, got {report.items_new}"
    assert report.sources_attempted == 2


# ---------------------------------------------------------------------------
# Test 4: Duplicate items (INSERT OR IGNORE) are not double-counted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_dedup_no_double_count(tmp_db, tmp_lock, tmp_last_fetch, profile_file, sources_file):
    """
    Run the pipeline twice with identical mocked items.
    Second run must have items_new=0 (INSERT OR IGNORE prevents duplicates).
    """
    raw_items = [_make_raw_item(20), _make_raw_item(21)]

    with (
        patch("app.pipeline._LOCK_FILE", tmp_lock),
        patch("app.pipeline._LAST_FETCH_FILE", tmp_last_fetch),
        patch("app.pipeline.fetch_source", return_value=raw_items),
        patch("app.rank.call_llm", new=AsyncMock(side_effect=_rank_llm_response)),
    ):
        from app.pipeline import run_fetch_cycle

        report1 = await run_fetch_cycle(
            sources_path=str(sources_file),
            profile_path=str(profile_file),
            db_path=tmp_db,
        )
        report2 = await run_fetch_cycle(
            sources_path=str(sources_file),
            profile_path=str(profile_file),
            db_path=tmp_db,
        )

    assert report1.items_new == 2, f"First run: expected 2 new, got {report1.items_new}"
    assert report2.items_new == 0, f"Second run: expected 0 new (all duplicates), got {report2.items_new}"


# ---------------------------------------------------------------------------
# Test 5: sources table populated and source_id non-null on items
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_populates_sources_table(
    tmp_db, tmp_lock, tmp_last_fetch, profile_file, sources_file
):
    """
    After a fetch cycle, every item must have a non-null source_id and the
    sources table must contain a row for the configured feed. Regression
    test for the historical bug where the sources table stayed empty and
    items had source_id=NULL.
    """
    raw_items = [_make_raw_item(30), _make_raw_item(31)]

    with (
        patch("app.pipeline._LOCK_FILE", tmp_lock),
        patch("app.pipeline._LAST_FETCH_FILE", tmp_last_fetch),
        patch("app.pipeline.fetch_source", return_value=raw_items),
        patch("app.rank.call_llm", new=AsyncMock(side_effect=_rank_llm_response)),
    ):
        from app.pipeline import run_fetch_cycle

        report = await run_fetch_cycle(
            sources_path=str(sources_file),
            profile_path=str(profile_file),
            db_path=tmp_db,
        )

    assert report.items_new == 2

    conn = sqlite3.connect(tmp_db)
    try:
        conn.row_factory = sqlite3.Row
        sources_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        null_source_id_items = conn.execute(
            "SELECT COUNT(*) FROM items WHERE source_id IS NULL"
        ).fetchone()[0]
        source_row = conn.execute("SELECT kind, url, title FROM sources").fetchone()
    finally:
        conn.close()

    assert sources_count == 1, f"Expected 1 source row, got {sources_count}"
    assert null_source_id_items == 0, (
        f"Expected 0 items with NULL source_id, got {null_source_id_items}"
    )
    assert source_row["kind"] == "rss"
    assert source_row["url"] == "https://example.com/feed.rss"
    assert source_row["title"] == "Test Feed"
