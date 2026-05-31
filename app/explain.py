"""
Deterministic recommendation explanation helpers.
"""
from __future__ import annotations

import re
import sqlite3

from app.content_signals import low_signal_reasons, novelty_label
from app.db import Item
from app.paths import profile_path
from app.reason_labels import build_reason_chips, clean_rationale
from app.source_quality import get_source_quality

PROFILE_PATH = profile_path()
_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in _WORD_RE.findall(value)
        if len(token) >= 4
    }


def _profile_bullets(profile_md: str) -> list[str]:
    bullets = []
    for line in profile_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def matched_profile_interests(
    profile_md: str,
    item_text: str,
    *,
    limit: int = 3,
) -> list[str]:
    item_tokens = _tokens(item_text)
    matches: list[tuple[int, str]] = []
    for bullet in _profile_bullets(profile_md):
        bullet_tokens = _tokens(bullet)
        if not bullet_tokens:
            continue
        overlap = len(item_tokens & bullet_tokens)
        if overlap:
            matches.append((overlap, bullet))
    matches.sort(key=lambda row: row[0], reverse=True)
    return [bullet for _, bullet in matches[:limit]]


def _tier_label(score: float) -> str:
    if score >= 8:
        return "Top pick"
    if score >= 5:
        return "Relevant"
    return "Borderline"


def _source_quality_score(conn: sqlite3.Connection, source_id: int | None) -> float | None:
    if source_id is None:
        return None
    for source in get_source_quality(conn):
        if source["id"] == source_id:
            return float(source["quality_score"])
    return None


def _read_profile() -> str:
    try:
        return PROFILE_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


def build_item_explanation(
    conn: sqlite3.Connection,
    item: Item,
    *,
    profile_md: str | None = None,
    cluster_size: int | None = None,
) -> dict:
    profile = profile_md if profile_md is not None else _read_profile()
    item_text = " ".join(
        value for value in (
            item.title,
            item.excerpt or "",
            item.topic or "",
            clean_rationale(item.rank_rationale),
        )
        if value
    )

    return {
        "score": item.score,
        "tier_label": _tier_label(item.score),
        "topic": item.topic,
        "rationale": clean_rationale(item.rank_rationale),
        "reason_chips": build_reason_chips(item, cluster_size=cluster_size),
        "novelty_label": novelty_label(item, cluster_size=cluster_size),
        "low_signal_flags": low_signal_reasons(item),
        "source_quality_score": _source_quality_score(conn, item.source_id),
        "cluster_size": cluster_size,
        "matched_interests": matched_profile_interests(profile, item_text),
    }
