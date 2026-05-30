"""
Tests for app/rank.py — TDD written before implementation.

All call_llm calls are mocked; no real CLI is invoked.
"""
import json
import sqlite3
import pytest
from unittest.mock import AsyncMock, patch

from app.db import Item
from app.llm import LLMResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_item(id: int, title: str = "Test", score: float = 0.0) -> Item:
    return Item(
        id=id,
        source_id=None,
        url=f"http://ex.com/{id}",
        canonical_url=f"http://ex.com/{id}",
        title=title,
        author=None,
        published_at=None,
        fetched_at=0,
        excerpt=None,
        full_text=None,
        cluster_id=None,
        score=score,
        rank_rationale=None,
        ai_summary=None,
        ai_key_points=None,
        is_read=False,
        total_dwell_seconds=0.0,
    )


def make_llm_result(rankings: list[dict]) -> LLMResult:
    """Build a successful LLMResult with a rankings JSON payload."""
    text = json.dumps({"rankings": rankings})
    return LLMResult(text=text, model_used="claude", error=None)


# ---------------------------------------------------------------------------
# Test 1 — Happy path: full batch of 3 items, LLM returns valid JSON
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rank_batch_happy_path():
    items = [make_item(1, "AI news"), make_item(2, "Sports"), make_item(3, "Tech")]
    rankings = [
        {"id": 1, "score": 8.5, "rationale": "Very relevant to AI interests"},
        {"id": 2, "score": 2.0, "rationale": "Not relevant"},
        {"id": 3, "score": 7.0, "rationale": "Somewhat relevant"},
    ]
    mock_result = make_llm_result(rankings)

    with patch("app.rank.call_llm", new=AsyncMock(return_value=mock_result)):
        from app.rank import _rank_batch
        scores = await _rank_batch(items, "I like AI and tech", max_batch=50)

    assert scores[1].score == pytest.approx(8.5)
    assert scores[1].status == "ranked"
    assert scores[2].score == pytest.approx(2.0)
    assert scores[3].score == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# Test 2 — Missing "score" key for one item → 0.0, others scored normally
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rank_batch_missing_score_key():
    items = [make_item(10), make_item(11), make_item(12)]
    rankings = [
        {"id": 10, "score": 6.0, "rationale": "Good"},
        {"id": 11, "rationale": "Missing score field"},   # no "score" key
        {"id": 12, "score": 4.5, "rationale": "Ok"},
    ]
    mock_result = make_llm_result(rankings)

    with patch("app.rank.call_llm", new=AsyncMock(return_value=mock_result)):
        from app.rank import _rank_batch
        scores = await _rank_batch(items, "profile", max_batch=50)

    assert scores[10].score == pytest.approx(6.0)
    assert scores[11].score == pytest.approx(0.0)
    assert scores[11].status == "failed"
    assert scores[11].error == "missing_score"
    assert scores[12].score == pytest.approx(4.5)


# ---------------------------------------------------------------------------
# Test 3 — JSON parse failure → batch halved, second call succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rank_batch_json_failure_halves():
    items = [make_item(20), make_item(21), make_item(22), make_item(23)]

    bad_result = LLMResult(text="not valid json at all", model_used="claude", error=None)
    # After halving, two calls each cover 2 items
    good_result_a = make_llm_result([
        {"id": 20, "score": 5.0, "rationale": "ok"},
        {"id": 21, "score": 6.0, "rationale": "fine"},
    ])
    good_result_b = make_llm_result([
        {"id": 22, "score": 3.0, "rationale": "meh"},
        {"id": 23, "score": 9.0, "rationale": "great"},
    ])

    call_count = 0

    async def mock_llm(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return bad_result
        elif call_count == 2:
            return good_result_a
        else:
            return good_result_b

    with patch("app.rank.call_llm", new=mock_llm):
        from app.rank import _rank_batch
        scores = await _rank_batch(items, "profile", max_batch=4)

    assert scores[20].score == pytest.approx(5.0)
    assert scores[21].score == pytest.approx(6.0)
    assert scores[22].score == pytest.approx(3.0)
    assert scores[23].score == pytest.approx(9.0)
    assert call_count == 3  # 1 failed + 2 halved batches


# ---------------------------------------------------------------------------
# Test 4 — JSON parse failure all the way to batch_size=1 → all get 0.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rank_batch_persistent_failure():
    items = [make_item(30), make_item(31)]
    bad_result = LLMResult(text="still not json", model_used="claude", error=None)

    with patch("app.rank.call_llm", new=AsyncMock(return_value=bad_result)):
        from app.rank import _rank_batch
        scores = await _rank_batch(items, "profile", max_batch=2)

    assert scores[30].score == pytest.approx(0.0)
    assert scores[30].status == "failed"
    assert scores[30].error == "bad_json"
    assert scores[31].score == pytest.approx(0.0)
    assert scores[31].status == "failed"


# ---------------------------------------------------------------------------
# Test 5 — LLM error (result.error='timeout') → all items get 0.0 (no crash)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rank_batch_llm_error():
    items = [make_item(40), make_item(41)]
    error_result = LLMResult(text="", model_used="claude", error="timeout")

    with patch("app.rank.call_llm", new=AsyncMock(return_value=error_result)):
        from app.rank import _rank_batch
        scores = await _rank_batch(items, "profile", max_batch=50)

    assert scores[40].score == pytest.approx(0.0)
    assert scores[40].status == "failed"
    assert scores[40].error == "timeout"
    assert scores[41].score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test 6 — Score > 10 → clamped to 10.0; score < 0 → clamped to 0.0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rank_batch_score_clamping():
    items = [make_item(50), make_item(51)]
    rankings = [
        {"id": 50, "score": 15.0, "rationale": "Way too high"},
        {"id": 51, "score": -3.0, "rationale": "Negative"},
    ]
    mock_result = make_llm_result(rankings)

    with patch("app.rank.call_llm", new=AsyncMock(return_value=mock_result)):
        from app.rank import _rank_batch
        scores = await _rank_batch(items, "profile", max_batch=50)

    assert scores[50].score == pytest.approx(10.0)   # clamped from 15
    assert scores[51].score == pytest.approx(0.0)    # clamped from -3
    assert scores[51].status == "ranked"


# ---------------------------------------------------------------------------
# Test 7 — Prompt version included in rationale string
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rank_batch_prompt_version_in_rationale():
    items = [make_item(60)]
    rankings = [{"id": 60, "score": 7.0, "rationale": "Interesting article"}]
    mock_result = make_llm_result(rankings)

    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            score REAL DEFAULT 0.0,
            rank_rationale TEXT,
            ranking_status TEXT NOT NULL DEFAULT 'unranked',
            ranking_error TEXT,
            ranked_at INTEGER
        )"""
    )
    conn.execute("INSERT INTO items(id, score) VALUES (60, 0.0)")
    conn.commit()

    with patch("app.rank.call_llm", new=AsyncMock(return_value=mock_result)):
        from app.rank import rank_items, PROMPT_VERSION
        scores = await rank_items(items, "profile", conn)

    row = conn.execute("SELECT rank_rationale FROM items WHERE id=60").fetchone()
    assert row is not None
    rationale = row[0]
    assert PROMPT_VERSION in rationale
    assert "Interesting article" in rationale
    row = conn.execute(
        "SELECT ranking_status, ranking_error, ranked_at FROM items WHERE id=60"
    ).fetchone()
    assert row[0] == "ranked"
    assert row[1] is None
    assert row[2] is not None
    conn.close()


# ---------------------------------------------------------------------------
# Test 8 — Items with score > 0.0 are skipped (already ranked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rank_items_skips_already_ranked():
    already_ranked = make_item(70, score=5.0)
    unranked = make_item(71, score=0.0)
    items = [already_ranked, unranked]

    rankings = [{"id": 71, "score": 6.5, "rationale": "New item"}]
    mock_result = make_llm_result(rankings)

    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            score REAL DEFAULT 0.0,
            rank_rationale TEXT,
            ranking_status TEXT NOT NULL DEFAULT 'unranked',
            ranking_error TEXT,
            ranked_at INTEGER
        )"""
    )
    conn.execute("INSERT INTO items(id, score) VALUES (70, 5.0)")
    conn.execute("INSERT INTO items(id, score) VALUES (71, 0.0)")
    conn.commit()

    call_count = 0

    async def mock_llm(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        # The prompt should only contain item 71, not item 70
        assert '"id": 70' not in prompt, "Already-ranked item 70 should be skipped"
        return mock_result

    with patch("app.rank.call_llm", new=mock_llm):
        from app.rank import rank_items
        scores = await rank_items(items, "profile", conn)

    assert 70 not in scores, "Already-ranked item should not appear in returned scores"
    assert scores.get(71) == pytest.approx(6.5)
    # Verify item 70 score was not changed in DB
    row = conn.execute("SELECT score FROM items WHERE id=70").fetchone()
    assert row[0] == pytest.approx(5.0)
    conn.close()


@pytest.mark.asyncio
async def test_rank_items_marks_llm_failure_non_retryable():
    item = make_item(80)
    error_result = LLMResult(text="", model_used="claude", error="timeout")

    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            score REAL DEFAULT 0.0,
            rank_rationale TEXT,
            ranking_status TEXT NOT NULL DEFAULT 'unranked',
            ranking_error TEXT,
            ranked_at INTEGER
        )"""
    )
    conn.execute("INSERT INTO items(id, score) VALUES (80, 0.0)")
    conn.commit()

    with patch("app.rank.call_llm", new=AsyncMock(return_value=error_result)):
        from app.rank import rank_items
        scores = await rank_items([item], "profile", conn)

    assert scores[80] == pytest.approx(0.0)
    row = conn.execute(
        "SELECT ranking_status, ranking_error, ranked_at FROM items WHERE id=80"
    ).fetchone()
    assert row[0] == "failed"
    assert row[1] == "timeout"
    assert row[2] is not None
    conn.close()
