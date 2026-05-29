"""
app/dedup.py

Title fuzzy deduplication + URL canonical dedup + cluster assignment.

Algorithm (priority order):
  1. canonical_url exact match → is_duplicate=True
  2. title rapidfuzz.fuzz.ratio ≥ 85 (after normalisation) → is_duplicate=True
  3. No match → is_duplicate=False

Title normalisation: lowercase, strip punctuation, collapse whitespace.
"""
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.db import Item
from app.ingest.rss import RawItem

# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass
class DeduplicationResult:
    is_duplicate: bool          # True = exact URL match or title fuzzy match ≥85%
    cluster_id: int | None      # existing cluster to assign, or None for new items
    matched_item_id: int | None # which existing DB item matched (for cluster lookup)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = title.lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


# ---------------------------------------------------------------------------
# Core dedup logic
# ---------------------------------------------------------------------------

_TITLE_THRESHOLD = 85.0


def dedup_item(
    new_item: RawItem,
    recent_items: list[Item],
) -> DeduplicationResult:
    """
    Check if new_item is a duplicate of any recent_items.

    Priority order:
    1. canonical_url match → is_duplicate=True, matched_item_id=matching item's id
    2. title rapidfuzz.fuzz.ratio ≥85 (normalised) → is_duplicate=True, matched_item_id=match
    3. No match → is_duplicate=False, cluster_id=None, matched_item_id=None

    Returns cluster_id of the matching item (may be None if item has no cluster yet).
    """
    if not recent_items:
        return DeduplicationResult(is_duplicate=False, cluster_id=None, matched_item_id=None)

    # --- Pass 1: canonical_url exact match ---
    for item in recent_items:
        if item.canonical_url == new_item.canonical_url:
            return DeduplicationResult(
                is_duplicate=True,
                cluster_id=item.cluster_id,
                matched_item_id=item.id,
            )

    # --- Pass 2: title fuzzy match ---
    new_norm = _normalize_title(new_item.title)
    if not new_norm:
        # Empty normalized title → skip fuzzy matching
        return DeduplicationResult(is_duplicate=False, cluster_id=None, matched_item_id=None)

    for item in recent_items:
        item_norm = _normalize_title(item.title)
        if not item_norm:
            continue
        score = fuzz.ratio(new_norm, item_norm)
        if score >= _TITLE_THRESHOLD:
            return DeduplicationResult(
                is_duplicate=True,
                cluster_id=item.cluster_id,
                matched_item_id=item.id,
            )

    return DeduplicationResult(is_duplicate=False, cluster_id=None, matched_item_id=None)


def dedup_batch(
    new_items: list[RawItem],
    recent_items: list[Item],
) -> list[tuple[RawItem, DeduplicationResult]]:
    """
    Process a batch of new items efficiently.

    Builds lookup structures once:
      - url_index: {canonical_url: Item} for O(1) URL lookups
      - norm_titles: [(normalised_title, Item)] for linear title scan
    """
    if not new_items:
        return []

    # Build lookup structures once
    url_index: dict[str, Item] = {}
    norm_titles: list[tuple[str, Item]] = []

    for item in recent_items:
        # URL index — first item wins (most recently fetched first from DB)
        if item.canonical_url not in url_index:
            url_index[item.canonical_url] = item
        # Title list — include even if URL already indexed
        item_norm = _normalize_title(item.title)
        if item_norm:
            norm_titles.append((item_norm, item))

    results: list[tuple[RawItem, DeduplicationResult]] = []

    for new_item in new_items:
        # --- Pass 1: canonical_url ---
        matched = url_index.get(new_item.canonical_url)
        if matched is not None:
            results.append((new_item, DeduplicationResult(
                is_duplicate=True,
                cluster_id=matched.cluster_id,
                matched_item_id=matched.id,
            )))
            continue

        # --- Pass 2: title fuzzy ---
        new_norm = _normalize_title(new_item.title)
        if not new_norm:
            results.append((new_item, DeduplicationResult(
                is_duplicate=False, cluster_id=None, matched_item_id=None,
            )))
            continue

        title_match: Item | None = None
        for item_norm, item in norm_titles:
            score = fuzz.ratio(new_norm, item_norm)
            if score >= _TITLE_THRESHOLD:
                title_match = item
                break

        if title_match is not None:
            results.append((new_item, DeduplicationResult(
                is_duplicate=True,
                cluster_id=title_match.cluster_id,
                matched_item_id=title_match.id,
            )))
        else:
            results.append((new_item, DeduplicationResult(
                is_duplicate=False, cluster_id=None, matched_item_id=None,
            )))

    return results
