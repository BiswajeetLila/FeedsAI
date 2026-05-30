"""
Source quality metrics derived from rank and engagement data.
"""
import sqlite3
import time


def get_source_quality(conn: sqlite3.Connection, days: int = 14) -> list[dict]:
    cutoff = int(time.time()) - days * 86400
    rows = conn.execute(
        """
        WITH item_activity AS (
            SELECT
                item_id,
                SUM(CASE WHEN event = 'opened' THEN 1 ELSE 0 END) AS opens,
                SUM(CASE WHEN event = 'linked_out' THEN 1 ELSE 0 END) AS linkouts
            FROM activity
            WHERE ts >= ?
            GROUP BY item_id
        )
        SELECT
            s.id,
            s.kind,
            s.url,
            s.title,
            COUNT(i.id) AS item_count,
            COALESCE(AVG(i.score), 0.0) AS avg_score,
            COALESCE(SUM(i.is_liked), 0) AS liked_count,
            COALESCE(SUM(i.is_saved), 0) AS saved_count,
            COALESCE(SUM(ia.opens), 0) AS opened_count,
            COALESCE(SUM(ia.linkouts), 0) AS linked_out_count
        FROM sources s
        LEFT JOIN items i ON i.source_id = s.id AND i.fetched_at >= ?
        LEFT JOIN item_activity ia ON ia.item_id = i.id
        GROUP BY s.id
        ORDER BY avg_score DESC, liked_count DESC, opened_count DESC, item_count DESC
        """,
        (cutoff, cutoff),
    ).fetchall()

    quality = []
    for row in rows:
        item_count = int(row["item_count"] or 0)
        avg_score = float(row["avg_score"] or 0.0)
        liked = int(row["liked_count"] or 0)
        saved = int(row["saved_count"] or 0)
        opened = int(row["opened_count"] or 0)
        linked = int(row["linked_out_count"] or 0)
        quality_score = avg_score + (liked * 0.35) + (saved * 0.2) + (linked * 0.15) + (opened * 0.05)
        quality.append({
            "id": row["id"],
            "kind": row["kind"],
            "url": row["url"],
            "title": row["title"] or row["url"],
            "item_count": item_count,
            "avg_score": round(avg_score, 2),
            "liked_count": liked,
            "saved_count": saved,
            "opened_count": opened,
            "linked_out_count": linked,
            "quality_score": round(quality_score, 2),
        })

    return quality
