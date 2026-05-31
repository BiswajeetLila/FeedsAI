"""
SQLite schema and database layer for FeedsAI.
"""
import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.paths import default_db_path

_DEFAULT_DB = default_db_path()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS config(
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS sources(
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  url TEXT UNIQUE NOT NULL,
  source_key TEXT,
  title TEXT,
  added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS clusters(
  id INTEGER PRIMARY KEY,
  representative_item_id INTEGER,
  member_count INTEGER NOT NULL DEFAULT 1,
  label TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY,
  source_id INTEGER REFERENCES sources(id),
  url TEXT NOT NULL,
  canonical_url TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  published_at INTEGER,
  fetched_at INTEGER NOT NULL,
  excerpt TEXT,
  full_text TEXT,
  cluster_id INTEGER REFERENCES clusters(id),
  score REAL NOT NULL DEFAULT 0.0,
  rank_rationale TEXT,
  topic TEXT,
  ranking_status TEXT NOT NULL DEFAULT 'unranked',
  ranking_error TEXT,
  ranked_at INTEGER,
  ai_summary TEXT,
  ai_key_points TEXT,
  is_read INTEGER NOT NULL DEFAULT 0,
  is_liked INTEGER NOT NULL DEFAULT 0,
  is_saved INTEGER NOT NULL DEFAULT 0,
  total_dwell_seconds REAL NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_score ON items(score DESC, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_fetched ON items(fetched_at DESC);

CREATE TABLE IF NOT EXISTS activity(
  id INTEGER PRIMARY KEY,
  item_id INTEGER REFERENCES items(id),
  event TEXT NOT NULL,
  dwell_seconds REAL,
  ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS source_fetch_health(
  source_key TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  label TEXT,
  last_attempted_at INTEGER,
  last_success_at INTEGER,
  last_error TEXT,
  items_fetched INTEGER NOT NULL DEFAULT 0,
  items_new INTEGER NOT NULL DEFAULT 0
);
"""

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Item:
    id: int
    source_id: int | None
    url: str
    canonical_url: str
    title: str
    author: str | None
    published_at: int | None
    fetched_at: int
    excerpt: str | None
    full_text: str | None
    cluster_id: int | None
    score: float
    rank_rationale: str | None
    ai_summary: str | None
    ai_key_points: str | None  # stored as JSON string
    is_read: bool
    total_dwell_seconds: float
    source_title: str | None = None  # populated by get_digest_items JOIN
    topic: str | None = None
    is_liked: bool = False
    is_saved: bool = False
    ranking_status: str = "unranked"
    ranking_error: str | None = None
    ranked_at: int | None = None


@dataclass
class Source:
    id: int
    kind: str
    url: str
    source_key: str | None
    title: str | None
    added_at: int


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

def _with_retry(fn, max_retries=3, base_delay=0.5):
    """Retry fn on sqlite OperationalError (database is locked)."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < max_retries:
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def get_connection(db_path: Path = _DEFAULT_DB) -> sqlite3.Connection:
    """Open WAL-mode SQLite connection with timeout and row_factory."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(db_path: Path = _DEFAULT_DB):
    """Context manager: auto-commit on success, auto-rollback on error."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def _migrate(conn: sqlite3.Connection) -> None:
    """Safe additive migrations — ignore if column already exists."""
    migrations = [
        "ALTER TABLE items ADD COLUMN topic TEXT",
        "ALTER TABLE items ADD COLUMN is_liked INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE items ADD COLUMN is_saved INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE items ADD COLUMN ranking_status TEXT NOT NULL DEFAULT 'unranked'",
        "ALTER TABLE items ADD COLUMN ranking_error TEXT",
        "ALTER TABLE items ADD COLUMN ranked_at INTEGER",
        "ALTER TABLE sources ADD COLUMN source_key TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists

    try:
        conn.execute(
            """
            UPDATE items
            SET ranking_status='ranked',
                ranking_error=NULL,
                ranked_at=COALESCE(ranked_at, fetched_at)
            WHERE ranking_status='unranked'
              AND (rank_rationale IS NOT NULL OR score > 0.0)
            """
        )
    except sqlite3.OperationalError:
        pass


def init_schema(db_path: Path = _DEFAULT_DB) -> None:
    """Create all tables and indexes if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_db(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
        _migrate(conn)
        try:
            from app.search import init_search_schema
            init_search_schema(conn)
        except Exception:
            logger.debug("Search schema initialisation skipped", exc_info=True)
    logger.info("Schema initialised at %s", db_path)


# ---------------------------------------------------------------------------
# Row → dataclass helpers
# ---------------------------------------------------------------------------

def _row_to_item(row: sqlite3.Row) -> Item:
    keys = row.keys()
    return Item(
        id=row["id"],
        source_id=row["source_id"],
        url=row["url"],
        canonical_url=row["canonical_url"],
        title=row["title"],
        author=row["author"],
        published_at=row["published_at"],
        fetched_at=row["fetched_at"],
        excerpt=row["excerpt"],
        full_text=row["full_text"],
        cluster_id=row["cluster_id"],
        score=row["score"],
        rank_rationale=row["rank_rationale"],
        ranking_status=row["ranking_status"] if "ranking_status" in keys else "unranked",
        ranking_error=row["ranking_error"] if "ranking_error" in keys else None,
        ranked_at=row["ranked_at"] if "ranked_at" in keys else None,
        ai_summary=row["ai_summary"],
        ai_key_points=row["ai_key_points"],
        is_read=bool(row["is_read"]),
        total_dwell_seconds=row["total_dwell_seconds"],
        topic=row["topic"] if "topic" in keys else None,
        is_liked=bool(row["is_liked"]) if "is_liked" in keys else False,
        is_saved=bool(row["is_saved"]) if "is_saved" in keys else False,
    )


def _row_to_source(row: sqlite3.Row) -> Source:
    keys = row.keys()
    return Source(
        id=row["id"],
        kind=row["kind"],
        url=row["url"],
        source_key=row["source_key"] if "source_key" in keys else None,
        title=row["title"],
        added_at=row["added_at"],
    )


# ---------------------------------------------------------------------------
# Source functions
# ---------------------------------------------------------------------------

def upsert_source(
    conn: sqlite3.Connection,
    kind: str,
    url: str,
    title: str | None,
    source_key: str | None = None,
) -> int:
    """Insert or update source, return id."""
    now = int(time.time())
    def _run():
        conn.execute(
            "INSERT INTO sources(kind, url, source_key, title, added_at) VALUES (?,?,?,?,?)"
            " ON CONFLICT(url) DO UPDATE SET kind=excluded.kind,"
            " source_key=COALESCE(excluded.source_key, source_key),"
            " title=COALESCE(excluded.title, title)",
            (kind, url, source_key, title, now),
        )
        row = conn.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()
        return row["id"]
    return _with_retry(_run)


def get_all_sources(conn: sqlite3.Connection) -> list[Source]:
    """Return all sources."""
    rows = conn.execute("SELECT * FROM sources ORDER BY added_at DESC").fetchall()
    return [_row_to_source(r) for r in rows]


def record_source_fetch_attempt(
    conn: sqlite3.Connection,
    source_key: str,
    kind: str,
    label: str | None,
) -> None:
    now = int(time.time())

    def _run():
        conn.execute(
            """
            INSERT INTO source_fetch_health(
                source_key, kind, label, last_attempted_at, last_error,
                items_fetched, items_new
            )
            VALUES (?, ?, ?, ?, NULL, 0, 0)
            ON CONFLICT(source_key) DO UPDATE SET
                kind=excluded.kind,
                label=excluded.label,
                last_attempted_at=excluded.last_attempted_at,
                last_error=NULL,
                items_fetched=0,
                items_new=0
            """,
            (source_key, kind, label, now),
        )

    _with_retry(_run)


def record_source_fetch_result(
    conn: sqlite3.Connection,
    source_key: str,
    kind: str,
    label: str | None,
    items_fetched: int,
    items_new: int,
    error: str | None = None,
) -> None:
    now = int(time.time())
    success_at = now if error is None else None

    def _run():
        conn.execute(
            """
            INSERT INTO source_fetch_health(
                source_key, kind, label, last_attempted_at, last_success_at,
                last_error, items_fetched, items_new
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                kind=excluded.kind,
                label=excluded.label,
                last_success_at=COALESCE(excluded.last_success_at, last_success_at),
                last_error=excluded.last_error,
                items_fetched=excluded.items_fetched,
                items_new=excluded.items_new
            """,
            (source_key, kind, label, now, success_at, error, items_fetched, items_new),
        )

    _with_retry(_run)


def get_source_fetch_health(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT source_key, kind, label, last_attempted_at, last_success_at,
               last_error, items_fetched, items_new
        FROM source_fetch_health
        """
    ).fetchall()
    return {
        row["source_key"]: {
            "source_key": row["source_key"],
            "kind": row["kind"],
            "label": row["label"],
            "last_attempted_at": row["last_attempted_at"],
            "last_success_at": row["last_success_at"],
            "last_error": row["last_error"],
            "items_fetched": row["items_fetched"],
            "items_new": row["items_new"],
        }
        for row in rows
    }


# ---------------------------------------------------------------------------
# Item functions
# ---------------------------------------------------------------------------

_VALID_ITEM_COLUMNS = frozenset({
    "source_id", "url", "canonical_url", "title", "author", "published_at",
    "fetched_at", "excerpt", "full_text", "cluster_id", "score", "rank_rationale",
    "ranking_status", "ranking_error", "ranked_at", "ai_summary", "ai_key_points",
    "is_read", "is_saved", "total_dwell_seconds",
})


def insert_item_if_new(conn: sqlite3.Connection, **kwargs) -> int | None:
    """INSERT OR IGNORE. Returns new id or None if duplicate canonical_url."""
    invalid = set(kwargs.keys()) - _VALID_ITEM_COLUMNS
    if invalid:
        raise ValueError(f"Invalid item columns: {invalid}")
    cols = list(kwargs.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    values = [kwargs[c] for c in cols]

    def _run():
        cur = conn.execute(
            f"INSERT OR IGNORE INTO items({col_names}) VALUES ({placeholders})",
            values,
        )
        if cur.lastrowid and cur.rowcount > 0:
            try:
                from app.search import upsert_search_item
                upsert_search_item(conn, cur.lastrowid)
            except Exception:
                logger.debug("Search index update skipped for item %s", cur.lastrowid, exc_info=True)
            return cur.lastrowid
        return None

    return _with_retry(_run)


def get_unranked_items(conn: sqlite3.Connection, since_hours: int = 24) -> list[Item]:
    """Items not yet ranked, fetched in last N hours."""
    cutoff = int(time.time()) - since_hours * 3600
    rows = conn.execute(
        """
        SELECT * FROM items
        WHERE ranking_status='unranked' AND score <= 0.0 AND fetched_at >= ?
        ORDER BY fetched_at DESC
        """,
        (cutoff,),
    ).fetchall()
    return [_row_to_item(r) for r in rows]


def update_item_score(
    conn: sqlite3.Connection,
    item_id: int,
    score: float,
    rationale: str,
    prompt_version: str,
    topic: str | None = None,
) -> None:
    """Update score + rank_rationale (include prompt_version in rationale string)."""
    full_rationale = f"[{prompt_version}] {rationale}"
    ranked_at = int(time.time())

    def _run():
        if topic is not None:
            conn.execute(
                """
                UPDATE items
                SET score=?, rank_rationale=?, topic=?,
                    ranking_status='ranked', ranking_error=NULL, ranked_at=?
                WHERE id=?
                """,
                (score, full_rationale, topic, ranked_at, item_id),
            )
        else:
            conn.execute(
                """
                UPDATE items
                SET score=?, rank_rationale=?,
                    ranking_status='ranked', ranking_error=NULL, ranked_at=?
                WHERE id=?
                """,
                (score, full_rationale, ranked_at, item_id),
            )

    _with_retry(_run)
    try:
        from app.search import upsert_search_item
        upsert_search_item(conn, item_id)
    except Exception:
        logger.debug("Search index update skipped for item %s", item_id, exc_info=True)


def update_item_rank_failure(
    conn: sqlite3.Connection,
    item_id: int,
    error: str,
    prompt_version: str,
) -> None:
    """Mark item ranking as failed so the fetch loop does not retry forever."""
    ranked_at = int(time.time())
    rationale = f"[{prompt_version}] ranking failed: {error}"

    def _run():
        conn.execute(
            """
            UPDATE items
            SET ranking_status='failed',
                ranking_error=?,
                rank_rationale=?,
                ranked_at=?
            WHERE id=?
            """,
            (error, rationale, ranked_at, item_id),
        )

    _with_retry(_run)


def update_item_summary(
    conn: sqlite3.Connection,
    item_id: int,
    summary: str,
    key_points: list[str],
) -> None:
    """Store ai_summary + ai_key_points (JSON-encode the list)."""
    key_points_json = json.dumps(key_points)

    def _run():
        conn.execute(
            "UPDATE items SET ai_summary=?, ai_key_points=? WHERE id=?",
            (summary, key_points_json, item_id),
        )

    _with_retry(_run)


def get_digest_items(
    conn: sqlite3.Connection,
    hours: int = 24,
    limit: int = 10,
    offset: int = 0,
    topic: str | None = None,
    saved_only: bool = False,
) -> list[Item]:
    """Top N items by score from last N hours, one per cluster (highest score wins)."""
    cutoff = int(time.time()) - hours * 3600

    topic_clause = "AND r.topic = ?" if topic else ""
    saved_clause = "AND r.is_saved = 1" if saved_only else ""
    params: list = [cutoff]
    if topic:
        params.append(topic)
    params.extend([limit, offset])

    rows = conn.execute(
        f"""
        WITH ranked AS (
            SELECT i.*,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(i.cluster_id, -i.id)
                    ORDER BY i.score DESC, i.published_at DESC
                ) AS rn
            FROM items i
            WHERE COALESCE(i.published_at, i.fetched_at) >= ?
        )
        SELECT r.*, s.title AS source_title
        FROM ranked r
        LEFT JOIN sources s ON r.source_id = s.id
        WHERE r.rn = 1 {topic_clause} {saved_clause}
        ORDER BY r.score DESC, r.published_at DESC
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()

    items = []
    for r in rows:
        item = _row_to_item(r)
        item.source_title = r["source_title"] if r["source_title"] else None
        items.append(item)
    return items


def get_item_by_id(conn: sqlite3.Connection, item_id: int) -> Item | None:
    """Fetch single item by id."""
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def mark_item_read(conn: sqlite3.Connection, item_id: int) -> None:
    """Set is_read=1."""
    def _run():
        conn.execute("UPDATE items SET is_read=1 WHERE id=?", (item_id,))

    _with_retry(_run)


def mark_item_liked(conn: sqlite3.Connection, item_id: int, liked: bool = True) -> None:
    """Toggle is_liked flag."""
    def _run():
        conn.execute("UPDATE items SET is_liked=? WHERE id=?", (int(liked), item_id))

    _with_retry(_run)


def mark_item_saved(conn: sqlite3.Connection, item_id: int, saved: bool = True) -> None:
    """Toggle saved-for-later flag."""
    def _run():
        conn.execute("UPDATE items SET is_saved=? WHERE id=?", (int(saved), item_id))

    _with_retry(_run)


# ---------------------------------------------------------------------------
# Activity functions
# ---------------------------------------------------------------------------

def record_activity(
    conn: sqlite3.Connection,
    item_id: int,
    event: str,
    dwell_seconds: float | None = None,
) -> None:
    """Insert activity row + update items.total_dwell_seconds if dwell provided."""
    now = int(time.time())

    def _run():
        conn.execute(
            "INSERT INTO activity(item_id, event, dwell_seconds, ts) VALUES (?, ?, ?, ?)",
            (item_id, event, dwell_seconds, now),
        )
        if dwell_seconds is not None:
            conn.execute(
                "UPDATE items SET total_dwell_seconds = total_dwell_seconds + ? WHERE id=?",
                (dwell_seconds, item_id),
            )

    _with_retry(_run)


# ---------------------------------------------------------------------------
# Config functions
# ---------------------------------------------------------------------------

def get_config(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    """Read from config table."""
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_config(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write to config table."""
    def _run():
        conn.execute(
            "INSERT INTO config(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    _with_retry(_run)


# ---------------------------------------------------------------------------
# Cluster functions
# ---------------------------------------------------------------------------

def get_or_create_cluster(conn: sqlite3.Connection, representative_item_id: int) -> int:
    """Create cluster for item, return cluster_id."""
    now = int(time.time())

    def _run():
        cur = conn.execute(
            "INSERT INTO clusters(representative_item_id, member_count, created_at, updated_at) VALUES (?, 1, ?, ?)",
            (representative_item_id, now, now),
        )
        cluster_id = cur.lastrowid
        # Link the representative item to this cluster
        conn.execute(
            "UPDATE items SET cluster_id=? WHERE id=?",
            (cluster_id, representative_item_id),
        )
        return cluster_id

    return _with_retry(_run)


def increment_cluster_member(
    conn: sqlite3.Connection, cluster_id: int, delta: int = 1
) -> None:
    """Atomically increment member_count by delta and update updated_at."""
    now = int(time.time())

    def _run():
        conn.execute(
            "UPDATE clusters SET member_count = member_count + ?, updated_at=? WHERE id=?",
            (delta, now, cluster_id),
        )

    _with_retry(_run)


def get_recent_items_for_dedup(conn: sqlite3.Connection, days: int = 7) -> list[Item]:
    """Return items from last N days for dedup comparison."""
    cutoff = int(time.time()) - days * 86400
    rows = conn.execute(
        "SELECT * FROM items WHERE fetched_at >= ? ORDER BY fetched_at DESC",
        (cutoff,),
    ).fetchall()
    return [_row_to_item(r) for r in rows]
