"""
Learning dashboard aggregation.
"""
from __future__ import annotations

import sqlite3
import time

from app.content_signals import is_low_signal
from app.db import _row_to_item
from app.engagement import compute_engagement_score
from app.profile_update import MIN_SIGNALS_FOR_UPDATE


def get_learning_dashboard(conn: sqlite3.Connection, days: int = 7) -> dict:
    cutoff = int(time.time()) - days * 86400
    rows = conn.execute(
        """
        SELECT
            i.*,
            s.title AS source_title,
            COALESCE(SUM(CASE WHEN a.event = 'viewed' THEN 1 ELSE 0 END), 0) AS viewed_count,
            COALESCE(SUM(CASE WHEN a.event = 'opened' THEN 1 ELSE 0 END), 0) AS opened_count,
            COALESCE(SUM(CASE WHEN a.event = 'linked_out' THEN 1 ELSE 0 END), 0) AS linked_out_count,
            COALESCE(SUM(CASE WHEN a.event = 'liked' THEN 1 ELSE 0 END), 0) AS liked_count
        FROM items i
        LEFT JOIN sources s ON i.source_id = s.id
        LEFT JOIN activity a ON a.item_id = i.id AND a.ts >= ?
        WHERE i.fetched_at >= ?
        GROUP BY i.id
        """,
        (cutoff, cutoff),
    ).fetchall()

    topic_scores: dict[str, float] = {}
    topic_counts: dict[str, int] = {}
    source_scores: dict[str, float] = {}
    source_counts: dict[str, int] = {}
    items = []
    total_signals = 0

    for row in rows:
        item = _row_to_item(row)
        item.source_title = row["source_title"] if row["source_title"] else None
        viewed = int(row["viewed_count"] or 0)
        opened = int(row["opened_count"] or 0)
        linked = int(row["linked_out_count"] or 0)
        liked = max(int(row["liked_count"] or 0), int(item.is_liked))
        score = compute_engagement_score(
            viewed,
            opened,
            linked,
            liked,
            float(item.total_dwell_seconds or 0.0),
        )
        total_signals += opened + liked
        item_data = {
            "id": item.id,
            "title": item.title,
            "url": item.url,
            "topic": item.topic or "other",
            "source_title": item.source_title or "unknown source",
            "engagement_score": round(score, 2),
            "score": item.score,
            "is_liked": item.is_liked,
            "is_saved": item.is_saved,
            "is_low_signal": is_low_signal(item),
        }
        items.append(item_data)

        topic_scores[item_data["topic"]] = topic_scores.get(item_data["topic"], 0.0) + score
        topic_counts[item_data["topic"]] = topic_counts.get(item_data["topic"], 0) + 1
        source_scores[item_data["source_title"]] = source_scores.get(item_data["source_title"], 0.0) + score
        source_counts[item_data["source_title"]] = source_counts.get(item_data["source_title"], 0) + 1

    def ranked_rows(key_name: str, scores: dict[str, float], counts: dict[str, int]) -> list[dict]:
        return [
            {key_name: key, "engagement_score": round(value, 2), "item_count": counts[key]}
            for key, value in sorted(scores.items(), key=lambda row: row[1], reverse=True)
        ]

    return {
        "top_topics": ranked_rows("topic", topic_scores, topic_counts),
        "top_sources": ranked_rows("source_title", source_scores, source_counts),
        "most_liked": [item for item in sorted(items, key=lambda row: row["engagement_score"], reverse=True) if item["is_liked"]],
        "most_saved": [item for item in sorted(items, key=lambda row: row["engagement_score"], reverse=True) if item["is_saved"]],
        "low_signal_items": [item for item in items if item["is_low_signal"]],
        "total_signals": total_signals,
        "signals_threshold": MIN_SIGNALS_FOR_UPDATE,
        "signals_needed": max(0, MIN_SIGNALS_FOR_UPDATE - total_signals),
        "ready_for_profile_update": total_signals >= MIN_SIGNALS_FOR_UPDATE,
    }
