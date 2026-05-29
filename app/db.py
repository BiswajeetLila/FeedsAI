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

_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_DB = _PROJECT_ROOT / "data" / "feeds.db"
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
  ai_summary TEXT,
  ai_key_points TEXT,
  is_read INTEGER NOT NULL DEFAULT 0,
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


@dataclass
class Source:
    id: int
    kind: str
    url: str
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
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists


def init_schema(db_path: Path = _DEFAULT_DB) -> None:
    """Create all tables and indexes if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_db(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
        _migrate(conn)
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
        ai_summary=row["ai_summary"],
        ai_key_points=row["ai_key_points"],
        is_read=bool(row["is_read"]),
        total_dwell_seconds=row["total_dwell_seconds"],
        topic=row["topic"] if "topic" in keys else None,
        is_liked=bool(row["is_liked"]) if "is_liked" in keys else False,
    )


def _row_to_source(row: sqlite3.Row) -> Source:
    return Source(
        id=row["id"],
        kind=row["kind"],
        url=row["url"],
        title=row["title"],
        added_at=row["added_at"],
    )


# ---------------------------------------------------------------------------
# Source functions
# ---------------------------------------------------------------------------

def upsert_source(conn: sqlite3.Connection, kind: str, url: str, title: str | None) -> int:
    """Insert or update source, return id."""
    now = int(time.time())
    def _run():
        conn.execute(
            "INSERT INTO sources(kind, url, title, added_at) VALUES (?,?,?,?)"
            " ON CONFLICT(url) DO UPDATE SET kind=excluded.kind, title=COALESCE(excluded.title, title)",
            (kind, url, title, now),
        )
        row = conn.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()
        return row["id"]
    return _with_retry(_run)


def get_all_sources(conn: sqlite3.Connection) -> list[Source]:
    """Return all sources."""
    rows = conn.execute("SELECT * FROM sources ORDER BY added_at DESC").fetchall()
    return [_row_to_source(r) for r in rows]


# ---------------------------------------------------------------------------
# Item functions
# ---------------------------------------------------------------------------

_VALID_ITEM_COLUMNS = frozenset({
    "source_id", "url", "canonical_url", "title", "author", "published_at",
    "fetched_at", "excerpt", "full_text", "cluster_id", "score", "rank_rationale",
    "ai_summary", "ai_key_points", "is_read", "total_dwell_seconds"
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
            return cur.lastrowid
        return None

    return _with_retry(_run)


def get_unranked_items(conn: sqlite3.Connection, since_hours: int = 24) -> list[Item]:
    """Items with score=0.0 fetched in last N hours."""
    cutoff = int(time.time()) - since_hours * 3600
    rows = conn.execute(
        "SELECT * FROM items WHERE score=0.0 AND fetched_at >= ? ORDER BY fetched_at DESC",
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

    def _run():
        if topic is not None:
            conn.execute(
                "UPDATE items SET score=?, rank_rationale=?, topic=? WHERE id=?",
                (score, full_rationale, topic, item_id),
            )
        else:
            conn.execute(
                "UPDATE items SET score=?, rank_rationale=? WHERE id=?",
                (score, full_rationale, item_id),
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
) -> list[Item]:
    """Top N items by score from last N hours, one per cluster (highest score wins)."""
    cutoff = int(time.time()) - hours * 3600

    topic_clause = "AND r.topic = ?" if topic else ""
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
        WHERE r.rn = 1 {topic_clause}
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


def get_top_items_without_summary(
    conn: sqlite3.Connection, hours: int = 24, limit: int = 20
) -> list["Item"]:
    """Top-scored items from last N hours that have no ai_summary yet."""
    cutoff = int(time.time()) - hours * 3600
    rows = conn.execute(
        """
        SELECT * FROM items
        WHERE fetched_at >= ? AND score > 0.0 AND (ai_summary IS NULL OR ai_summary = '')
        ORDER BY score DESC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()
    return [_row_to_item(r) for r in rows]


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
