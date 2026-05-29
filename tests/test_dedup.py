"""
tests/test_dedup.py

TDD test suite for app/dedup.py — title fuzzy dedup + cluster assignment.

All 20 labeled test cases as specified, plus structural tests.

Threshold calibration notes (fuzz.ratio on normalised strings, threshold=85):
  - Case 3  "GPT-5 Released by OpenAI" / "OpenAI Releases GPT-5"        ratio≈49  → NO match
  - Case 4  "Apple Announces iPhone 17" / "Apple unveils iPhone 17"      ratio≈83  → NO match (83 < 85)
  - Case 5  "Python 3.13 Released" / "Python 3.13 is out"               ratio≈68  → NO match (borderline, per spec: verify)
  - Case 7  "Meta open-sources Llama 3" / "Meta releases Llama 3 open…" ratio≈59  → NO match (borderline)
  - Case 9  "Python 3.13 Released" / "Python 3.12 Released"             ratio≈95  → MATCH (same structure, differ by one digit)

The spec mandates fuzz.ratio (not token_sort_ratio) at ≥85 after normalisation.
Cases 3, 4, 5, 7 are therefore documented as NON-duplicates at that threshold.
Case 9 is a TRUE-POSITIVE match (deliberate documentation of this edge case).
"""
import time
from dataclasses import dataclass

import pytest

from app.db import Item
from app.ingest.rss import RawItem
from app.dedup import DeduplicationResult, dedup_item, dedup_batch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_item(
    item_id: int,
    canonical_url: str,
    title: str,
    cluster_id: int | None = None,
) -> Item:
    """Construct a minimal Item for dedup tests."""
    return Item(
        id=item_id,
        source_id=None,
        url=canonical_url,
        canonical_url=canonical_url,
        title=title,
        author=None,
        published_at=int(time.time()),
        fetched_at=int(time.time()),
        excerpt=None,
        full_text=None,
        cluster_id=cluster_id,
        score=0.0,
        rank_rationale=None,
        ai_summary=None,
        ai_key_points=None,
        is_read=False,
        total_dwell_seconds=0.0,
    )


def make_raw(url: str, title: str) -> RawItem:
    """Construct a minimal RawItem for dedup tests."""
    return RawItem(
        url=url,
        canonical_url=url,
        title=title,
        author=None,
        published_at=int(time.time()),
        excerpt=None,
        source_title=None,
    )


# ---------------------------------------------------------------------------
# TC-1  Exact URL duplicate → is_duplicate=True
# ---------------------------------------------------------------------------

def test_tc01_exact_url_is_duplicate():
    """TC-1: Same canonical_url → is_duplicate=True."""
    existing = make_item(1, "https://example.com/article", "Some Article", cluster_id=10)
    new = make_raw("https://example.com/article", "Some Article With Slight Title Change")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is True
    assert result.matched_item_id == 1


# ---------------------------------------------------------------------------
# TC-2  Different URL + different title → not a duplicate
# ---------------------------------------------------------------------------

def test_tc02_different_url_different_title_not_duplicate():
    """TC-2: Different canonical_url, different title → is_duplicate=False."""
    existing = make_item(2, "https://example.com/article-a", "OpenAI News Today")
    new = make_raw("https://different.com/article-b", "Google DeepMind Update")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False
    assert result.matched_item_id is None
    assert result.cluster_id is None


# ---------------------------------------------------------------------------
# TC-3  "GPT-5 Released by OpenAI" / "OpenAI Releases GPT-5"
#       fuzz.ratio ≈ 49 after normalisation → NOT a duplicate at threshold=85
# ---------------------------------------------------------------------------

def test_tc03_gpt5_word_order_not_match():
    """TC-3 (documented non-match): fuzz.ratio≈49 — word-order swap is below threshold."""
    existing = make_item(3, "https://a.com/1", "GPT-5 Released by OpenAI")
    new = make_raw("https://b.com/2", "OpenAI Releases GPT-5")
    result = dedup_item(new, [existing])
    # fuzz.ratio on normalised strings ≈ 49, well below 85
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-4  "Apple Announces iPhone 17" / "Apple unveils iPhone 17"
#       fuzz.ratio ≈ 83 → NOT a duplicate (83 < 85)
# ---------------------------------------------------------------------------

def test_tc04_apple_iphone_borderline_no_match():
    """TC-4 (borderline): fuzz.ratio≈83 — just below 85 threshold, no match."""
    existing = make_item(4, "https://a.com/1", "Apple Announces iPhone 17")
    new = make_raw("https://b.com/2", "Apple unveils iPhone 17")
    result = dedup_item(new, [existing])
    # ratio≈83 < 85 threshold
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-5  "Python 3.13 Released" / "Python 3.13 is out"
#       fuzz.ratio ≈ 68 → NOT a duplicate (borderline, verified)
# ---------------------------------------------------------------------------

def test_tc05_python_release_not_match():
    """TC-5 (borderline — verified): fuzz.ratio≈68, does not reach 85 threshold."""
    existing = make_item(5, "https://a.com/1", "Python 3.13 Released")
    new = make_raw("https://b.com/2", "Python 3.13 is out")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-6  "Claude 3 Opus Review" / "Claude 3 Opus reviewed"
#       fuzz.ratio ≈ 95 → MATCH
# ---------------------------------------------------------------------------

def test_tc06_claude_opus_review_match():
    """TC-6: fuzz.ratio≈95 — singular/past-tense variation matches."""
    existing = make_item(6, "https://a.com/1", "Claude 3 Opus Review")
    new = make_raw("https://b.com/2", "Claude 3 Opus reviewed")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is True
    assert result.matched_item_id == 6


# ---------------------------------------------------------------------------
# TC-7  "Meta open-sources Llama 3" / "Meta releases Llama 3 open source"
#       fuzz.ratio ≈ 59 → NOT a duplicate (borderline)
# ---------------------------------------------------------------------------

def test_tc07_meta_llama_borderline_no_match():
    """TC-7 (borderline): fuzz.ratio≈59 — phrasing differs enough, no match."""
    existing = make_item(7, "https://a.com/1", "Meta open-sources Llama 3")
    new = make_raw("https://b.com/2", "Meta releases Llama 3 open source")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-8  "OpenAI announces GPT-5" / "Google DeepMind releases Gemini Ultra 2"
#       Clearly different → no match
# ---------------------------------------------------------------------------

def test_tc08_completely_different_titles_no_match():
    """TC-8: Completely different topics → no match."""
    existing = make_item(8, "https://a.com/1", "OpenAI announces GPT-5")
    new = make_raw("https://b.com/2", "Google DeepMind releases Gemini Ultra 2")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-9  "Python 3.13 Released" / "Python 3.12 Released"
#       fuzz.ratio ≈ 95 → MATCH — documented: this IS a false positive at 85
# ---------------------------------------------------------------------------

def test_tc09_python_version_false_positive():
    """TC-9 (documented false positive): fuzz.ratio≈95 — version numbers 3.12 vs 3.13 score high.
    At threshold=85 these ARE considered duplicates. Known trade-off.
    """
    existing = make_item(9, "https://a.com/1", "Python 3.13 Released")
    new = make_raw("https://b.com/2", "Python 3.12 Released")
    result = dedup_item(new, [existing])
    # ratio≈95 — matches at threshold=85 (documented trade-off)
    assert result.is_duplicate is True
    assert result.matched_item_id == 9


# ---------------------------------------------------------------------------
# TC-10  "Understanding Transformers" / "Understanding Diffusion Models"
#        fuzz.ratio ≈ 68 → no match
# ---------------------------------------------------------------------------

def test_tc10_understanding_different_topics_no_match():
    """TC-10: Shared prefix but different subject → no match."""
    existing = make_item(10, "https://a.com/1", "Understanding Transformers")
    new = make_raw("https://b.com/2", "Understanding Diffusion Models")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-11  "GitHub Copilot Update" / "GitHub Actions Update"
#        fuzz.ratio ≈ 81 → no match (below 85)
# ---------------------------------------------------------------------------

def test_tc11_github_different_product_no_match():
    """TC-11: Similar structure, different GitHub product → no match (ratio≈81)."""
    existing = make_item(11, "https://a.com/1", "GitHub Copilot Update")
    new = make_raw("https://b.com/2", "GitHub Actions Update")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-12  "Rust 1.78 stabilizes new feature" / "Go 1.22 adds slices package"
#        Clearly different → no match
# ---------------------------------------------------------------------------

def test_tc12_rust_vs_go_no_match():
    """TC-12: Different language release announcements → no match."""
    existing = make_item(12, "https://a.com/1", "Rust 1.78 stabilizes new feature")
    new = make_raw("https://b.com/2", "Go 1.22 adds slices package")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-13  Empty title / non-empty title → no match, handled gracefully
# ---------------------------------------------------------------------------

def test_tc13_empty_title_no_match():
    """TC-13: Empty title vs non-empty → no match, no exception."""
    existing = make_item(13, "https://a.com/1", "anything")
    new = make_raw("https://b.com/2", "")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False
    assert result.matched_item_id is None


def test_tc13b_existing_empty_title_no_match():
    """TC-13b: Existing item has empty title → no match, no exception."""
    existing = make_item(130, "https://a.com/1", "")
    new = make_raw("https://b.com/2", "something interesting")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-14  Very long title vs short title → no match (length ratio kills score)
# ---------------------------------------------------------------------------

def test_tc14_long_vs_short_title_no_match():
    """TC-14: Long title vs short title → low ratio, no match."""
    existing = make_item(14, "https://a.com/1",
                         "Very long title that goes on and on about many different things in detail")
    new = make_raw("https://b.com/2", "short")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-15  Punctuation normalisation: "C++ 23: What's New?" / "C++ 23: Whats New"
#        After stripping punctuation, fuzz.ratio ≈ 97 → MATCH
# ---------------------------------------------------------------------------

def test_tc15_punctuation_normalized_match():
    """TC-15: Punctuation stripped before comparison → match."""
    existing = make_item(15, "https://a.com/1", "C++ 23: What's New?")
    new = make_raw("https://b.com/2", "C++ 23: Whats New")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is True
    assert result.matched_item_id == 15


# ---------------------------------------------------------------------------
# TC-16  All caps vs all lower: "OPENAI RELEASES GPT-5" / "openai releases gpt-5"
#        After lowercasing → identical → ratio=100 → MATCH
# ---------------------------------------------------------------------------

def test_tc16_case_insensitive_match():
    """TC-16: Case-insensitive comparison → ratio=100 → match."""
    existing = make_item(16, "https://a.com/1", "OPENAI RELEASES GPT-5")
    new = make_raw("https://b.com/2", "openai releases gpt-5")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is True
    assert result.matched_item_id == 16


# ---------------------------------------------------------------------------
# TC-17  Unicode: "Über die KI-Revolution" / "Über die KI Revolution"
#        After punctuation strip → ratio≈100 → MATCH
# ---------------------------------------------------------------------------

def test_tc17_unicode_match():
    """TC-17: Unicode title with hyphen normalised → match."""
    existing = make_item(17, "https://a.com/1", "Über die KI-Revolution")
    new = make_raw("https://b.com/2", "Über die KI Revolution")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is True
    assert result.matched_item_id == 17


# ---------------------------------------------------------------------------
# TC-18  dedup_batch: 3 items — 1 canonical dupe, 1 title dupe, 1 unique
# ---------------------------------------------------------------------------

def test_tc18_dedup_batch_mixed():
    """TC-18: Batch with url-dupe, title-dupe, and unique item."""
    existing_url_match = make_item(100, "https://exact.com/url", "Some Tech Article", cluster_id=20)
    existing_title_match = make_item(101, "https://other.com/x", "OPENAI RELEASES GPT-5", cluster_id=21)
    existing_unrelated = make_item(102, "https://other.com/y", "Unrelated Article")

    recent_items = [existing_url_match, existing_title_match, existing_unrelated]

    url_dupe = make_raw("https://exact.com/url", "Different Title Here")
    title_dupe = make_raw("https://new.com/a", "openai releases gpt-5")
    unique = make_raw("https://new.com/b", "Brand New Unique Article Nobody Saw Before")

    results = dedup_batch([url_dupe, title_dupe, unique], recent_items)

    assert len(results) == 3

    # URL dupe
    raw0, res0 = results[0]
    assert raw0 is url_dupe
    assert res0.is_duplicate is True
    assert res0.matched_item_id == 100

    # Title dupe (case-insensitive match)
    raw1, res1 = results[1]
    assert raw1 is title_dupe
    assert res1.is_duplicate is True
    assert res1.matched_item_id == 101

    # Unique
    raw2, res2 = results[2]
    assert raw2 is unique
    assert res2.is_duplicate is False


# ---------------------------------------------------------------------------
# TC-19  dedup_batch with empty recent_items → all is_duplicate=False
# ---------------------------------------------------------------------------

def test_tc19_dedup_batch_empty_recent():
    """TC-19: No recent items → nothing can match."""
    items = [
        make_raw("https://a.com/1", "Article One"),
        make_raw("https://a.com/2", "Article Two"),
        make_raw("https://a.com/3", "Article Three"),
    ]
    results = dedup_batch(items, [])
    assert len(results) == 3
    for raw, res in results:
        assert res.is_duplicate is False
        assert res.cluster_id is None
        assert res.matched_item_id is None


# ---------------------------------------------------------------------------
# TC-20  cluster_id propagation: matched item has cluster_id=5 → result returns 5
# ---------------------------------------------------------------------------

def test_tc20_cluster_id_propagation():
    """TC-20: Matched DB item has cluster_id=5 → result.cluster_id=5."""
    existing = make_item(200, "https://a.com/1", "Claude 3 Opus Review", cluster_id=5)
    new = make_raw("https://b.com/2", "Claude 3 Opus reviewed")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is True
    assert result.cluster_id == 5
    assert result.matched_item_id == 200


# ---------------------------------------------------------------------------
# Structural / contract tests
# ---------------------------------------------------------------------------

def test_dedup_result_dataclass_fields():
    """DeduplicationResult has expected fields with correct types."""
    r = DeduplicationResult(is_duplicate=False, cluster_id=None, matched_item_id=None)
    assert r.is_duplicate is False
    assert r.cluster_id is None
    assert r.matched_item_id is None


def test_dedup_item_url_priority_over_title():
    """URL match takes priority: if both url AND title differ but url matches → is_duplicate=True."""
    existing = make_item(300, "https://exact.com/url", "Original Title", cluster_id=7)
    new = make_raw("https://exact.com/url", "Completely Different Title X Y Z")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is True
    assert result.matched_item_id == 300


def test_dedup_item_cluster_id_none_when_no_cluster():
    """When matched item has no cluster_id, result.cluster_id is None."""
    existing = make_item(301, "https://a.com/1", "Claude 3 Opus Review", cluster_id=None)
    new = make_raw("https://b.com/2", "Claude 3 Opus reviewed")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is True
    assert result.cluster_id is None


def test_dedup_item_no_recent_items():
    """No recent items → always returns is_duplicate=False."""
    new = make_raw("https://a.com/1", "Some Article")
    result = dedup_item(new, [])
    assert result.is_duplicate is False
    assert result.cluster_id is None
    assert result.matched_item_id is None


def test_dedup_batch_preserves_order():
    """dedup_batch returns results in the same order as input."""
    recent = [make_item(1, "https://x.com/1", "Existing Article")]
    new_items = [make_raw(f"https://new.com/{i}", f"New Article {i}") for i in range(5)]
    results = dedup_batch(new_items, recent)
    assert len(results) == 5
    for i, (raw, _) in enumerate(results):
        assert raw is new_items[i]


def test_dedup_batch_returns_list_of_tuples():
    """dedup_batch returns list[tuple[RawItem, DeduplicationResult]]."""
    results = dedup_batch([], [])
    assert isinstance(results, list)
    assert results == []


def test_dedup_item_url_match_returns_cluster_id():
    """URL match also returns cluster_id from the matched item."""
    existing = make_item(400, "https://canonical.com/url", "Any Title", cluster_id=42)
    new = make_raw("https://canonical.com/url", "Any Title")
    result = dedup_item(new, [existing])
    assert result.is_duplicate is True
    assert result.cluster_id == 42
