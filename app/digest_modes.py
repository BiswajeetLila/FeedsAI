"""
Ordering modes for the digest.

Modes reorder already-ranked candidates. They do not call LLMs or mutate data.
"""
from app.db import Item

VALID_DIGEST_MODES = ("ranked", "balanced", "fresh")


def normalize_digest_mode(value: str | None) -> str:
    return value if value in VALID_DIGEST_MODES else "ranked"


def apply_digest_mode(items: list[Item], mode: str) -> list[Item]:
    mode = normalize_digest_mode(mode)
    if mode == "fresh":
        return sorted(
            items,
            key=lambda item: (item.published_at or item.fetched_at, item.score),
            reverse=True,
        )
    if mode == "balanced":
        return _balanced(items)
    return list(items)


def _balanced(items: list[Item]) -> list[Item]:
    remaining = list(items)
    selected: list[Item] = []
    topic_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}

    while remaining:
        best_index = 0
        best_value = float("-inf")

        for index, item in enumerate(remaining):
            topic = item.topic or "other"
            source = item.source_title or str(item.source_id or "unknown")
            penalty = (topic_counts.get(topic, 0) * 0.85) + (source_counts.get(source, 0) * 0.55)
            value = item.score - penalty
            if value > best_value:
                best_value = value
                best_index = index

        picked = remaining.pop(best_index)
        selected.append(picked)
        topic = picked.topic or "other"
        source = picked.source_title or str(picked.source_id or "unknown")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

    return selected
