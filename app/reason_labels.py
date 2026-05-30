"""
Deterministic labels for why an item is worth opening.

These are intentionally cheap: existing title/excerpt/ranking metadata only,
no LLM call.
"""
import re
import time

from app.db import Item

_VERSION_PREFIX = re.compile(r"^\[[^\]]+\]\s*")

_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Research", ("paper", "arxiv", "study", "research", "findings", "experiment")),
    ("Release", ("release", "released", "launch", "launched", "version", "changelog")),
    ("Benchmark", ("benchmark", "eval", "evaluation", "leaderboard", "performance")),
    ("Practical", ("guide", "tutorial", "how to", "playbook", "case study", "implementation")),
    ("Funding", ("funding", "raised", "acquires", "acquisition", "merger", "ipo")),
    ("Security", ("security", "vulnerability", "exploit", "breach", "patch", "cve")),
)


def clean_rationale(value: str | None) -> str:
    if not value:
        return ""
    return _VERSION_PREFIX.sub("", value).strip()


def build_reason_chips(
    item: Item,
    cluster_size: int | None = None,
    *,
    now: int | None = None,
    limit: int = 4,
) -> list[str]:
    chips: list[str] = []

    if item.score >= 8.0:
        chips.append("Top fit")
    elif item.score >= 5.0:
        chips.append("Relevant")

    if item.topic:
        chips.append(item.topic.replace("_", " ").title())

    current_time = now if now is not None else int(time.time())
    published_at = item.published_at or item.fetched_at
    if published_at and current_time - published_at <= 6 * 3600:
        chips.append("Fresh")

    if cluster_size and cluster_size > 1:
        chips.append("Developing")

    text = " ".join(
        part for part in (item.title, item.excerpt, item.rank_rationale, item.source_title) if part
    ).lower()
    for label, terms in _PATTERNS:
        if label not in chips and any(term in text for term in terms):
            chips.append(label)
        if len(chips) >= limit:
            break

    if clean_rationale(item.rank_rationale) and "Personal match" not in chips:
        chips.append("Personal match")

    return chips[:limit]
