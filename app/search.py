"""
Local item search using SQLite FTS5 with LIKE fallback.
"""
from __future__ import annotations

import re
import sqlite3

from app.db import Item, _row_to_item

_TERMS_RE = re.compile(r"[A-Za-z0-9_]+")


def init_search_schema(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
                item_id UNINDEXED,
                title,
                excerpt,
                rank_rationale,
                source_title,
                topic
            )
            """
        )
        return True
    except sqlite3.OperationalError:
        return False


def _has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='items_fts'"
    ).fetchone()
    return row is not None


def _fts_query(query: str) -> str:
    terms = _TERMS_RE.findall(query)
    return " OR ".join(f"{term}*" for term in terms)


def rebuild_search_index(conn: sqlite3.Connection) -> None:
    if not init_search_schema(conn):
        return
    conn.execute("DELETE FROM items_fts")
    rows = conn.execute(
        """
        SELECT i.id, i.title, i.excerpt, i.rank_rationale, i.topic, s.title AS source_title
        FROM items i
        LEFT JOIN sources s ON i.source_id = s.id
        """
    ).fetchall()
    conn.executemany(
        """
        INSERT INTO items_fts(item_id, title, excerpt, rank_rationale, source_title, topic)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["id"],
                row["title"] or "",
                row["excerpt"] or "",
                row["rank_rationale"] or "",
                row["source_title"] or "",
                row["topic"] or "",
            )
            for row in rows
        ],
    )


def upsert_search_item(conn: sqlite3.Connection, item_id: int) -> None:
    if not _has_fts(conn):
        return
    row = conn.execute(
        """
        SELECT i.id, i.title, i.excerpt, i.rank_rationale, i.topic, s.title AS source_title
        FROM items i
        LEFT JOIN sources s ON i.source_id = s.id
        WHERE i.id=?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        return
    conn.execute("DELETE FROM items_fts WHERE item_id=?", (item_id,))
    conn.execute(
        """
        INSERT INTO items_fts(item_id, title, excerpt, rank_rationale, source_title, topic)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            row["id"],
            row["title"] or "",
            row["excerpt"] or "",
            row["rank_rationale"] or "",
            row["source_title"] or "",
            row["topic"] or "",
        ),
    )


def search_items(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
    topic: str | None = None,
    saved_only: bool = False,
    unread_only: bool = False,
) -> list[Item]:
    clean_query = query.strip()
    if not clean_query:
        return []

    clauses = []
    params: list = []
    if topic:
        clauses.append("i.topic = ?")
        params.append(topic)
    if saved_only:
        clauses.append("i.is_saved = 1")
    if unread_only:
        clauses.append("i.is_read = 0")
    where_tail = (" AND " + " AND ".join(clauses)) if clauses else ""

    rows = _search_fts(conn, clean_query, where_tail, params, limit)
    if rows is None:
        rows = _search_like(conn, clean_query, where_tail, params, limit)

    items = []
    for row in rows:
        item = _row_to_item(row)
        item.source_title = row["source_title"] if row["source_title"] else None
        items.append(item)
    return items


def _search_fts(
    conn: sqlite3.Connection,
    query: str,
    where_tail: str,
    params: list,
    limit: int,
):
    if not _has_fts(conn):
        return None
    fts_query = _fts_query(query)
    if not fts_query:
        return None
    try:
        return conn.execute(
            f"""
            SELECT i.*, s.title AS source_title, bm25(items_fts) AS rank
            FROM items_fts
            JOIN items i ON i.id = items_fts.item_id
            LEFT JOIN sources s ON i.source_id = s.id
            WHERE items_fts MATCH ? {where_tail}
            ORDER BY rank, i.score DESC, COALESCE(i.published_at, i.fetched_at) DESC
            LIMIT ?
            """,
            [fts_query, *params, limit],
        ).fetchall()
    except sqlite3.OperationalError:
        return None


def _search_like(
    conn: sqlite3.Connection,
    query: str,
    where_tail: str,
    params: list,
    limit: int,
):
    like = f"%{query}%"
    return conn.execute(
        f"""
        SELECT i.*, s.title AS source_title
        FROM items i
        LEFT JOIN sources s ON i.source_id = s.id
        WHERE (
            i.title LIKE ?
            OR COALESCE(i.excerpt, '') LIKE ?
            OR COALESCE(i.rank_rationale, '') LIKE ?
            OR COALESCE(i.topic, '') LIKE ?
            OR COALESCE(s.title, '') LIKE ?
        ) {where_tail}
        ORDER BY i.score DESC, COALESCE(i.published_at, i.fetched_at) DESC
        LIMIT ?
        """,
        [like, like, like, like, like, *params, limit],
    ).fetchall()
