"""
app/pipeline.py
Orchestrator for the full feed fetch cycle.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock, Timeout
from app.config import load_sources
from app.db import (
    _DEFAULT_DB,
    get_connection,
    get_or_create_cluster,
    get_recent_items_for_dedup,
    get_top_items_without_summary,
    get_unranked_items,
    increment_cluster_member,
    init_schema,
    insert_item_if_new,
    upsert_source,
)
from app.dedup import dedup_item
from app.ingest import fetch_source
from app.rank import rank_items


def _source_identifier(source) -> str:
    """
    Build a stable per-source identifier for the `sources.url` column.

    `upsert_source` uses URL as the conflict key, but only `rss` actually has
    a URL field. Synthesize a URI-like identifier for the others so each
    source.yaml entry maps to exactly one `sources` row.
    """
    kind = source.kind
    if kind == "rss":
        return str(source.url)
    if kind == "hn":
        return f"hn://{getattr(source, 'filter', 'front_page')}"
    if kind == "arxiv":
        return f"arxiv://{source.query}"
    if kind == "github_releases":
        return f"github://{source.repo}"
    return f"{kind}://unknown"

_PROJECT_ROOT = Path(__file__).parent.parent
_LOCK_FILE = _PROJECT_ROOT / "data" / "fetch.lock"
_LAST_FETCH_FILE = _PROJECT_ROOT / "data" / "last_fetch.txt"

# Drop items whose published_at is older than this. Protects against feeds
# (notably OpenAI/Anthropic blogs and arXiv categories) returning their full
# archive on every fetch, which otherwise floods the digest with multi-year-old
# items. Items with no published_at are kept — we don't have an age to test.
MAX_ITEM_AGE_DAYS = 7
MAX_ITEM_AGE_SECONDS = MAX_ITEM_AGE_DAYS * 86400

logger = logging.getLogger(__name__)


@dataclass
class FetchReport:
    sources_attempted: int = 0
    items_fetched: int = 0
    items_new: int = 0
    items_ranked: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


async def run_fetch_cycle(
    sources_path: str = "sources.yaml",
    profile_path: str = "profile.md",
    db_path: Path | None = None,
    source_filter: str | None = None,  # if set, only fetch this source (by title)
    dry_run: bool = False,             # if True, fetch but don't write to DB
) -> FetchReport:
    """
    Full fetch cycle:
    1. Acquire filelock (non-blocking). If locked: log + return empty report.
    2. init_schema() to ensure DB exists.
    3. Load sources.yaml via load_sources().
    4. For each source: call fetch_source(source) — catch errors per-source.
    5. For each raw item: insert_item_if_new → if new, run dedup_item, assign cluster.
    6. Get unranked items → rank_items(items, profile_md, conn).
    7. Write last_fetch.txt with current ISO timestamp.
    8. Return FetchReport with counts.
    """
    report = FetchReport()
    start_time = time.monotonic()

    # Tell /status we're working.
    try:
        from app import observability
        observability.fetch_started()
    except Exception:
        pass

    # --- Resolve paths ---
    sources_resolved = (
        Path(sources_path) if Path(sources_path).is_absolute()
        else _PROJECT_ROOT / sources_path
    )
    profile_resolved = (
        Path(profile_path) if Path(profile_path).is_absolute()
        else _PROJECT_ROOT / profile_path
    )

    # --- Resolve DB path ---
    if db_path is None:
        db_path = _DEFAULT_DB

    # --- Ensure data dir exists for lock file ---
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    # --- Acquire file lock (non-blocking) ---
    lock = FileLock(str(_LOCK_FILE), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        logger.info("run_fetch_cycle: lock is held by another process; skipping run")
        try:
            from app import observability
            observability.fetch_finished(summary="skipped (lock held)", error="")
        except Exception:
            pass
        return report

    try:
        # --- Ensure schema ---
        init_schema(db_path)

        # --- Load sources ---
        try:
            sources_file = load_sources(sources_resolved)
        except Exception as exc:
            logger.error("run_fetch_cycle: failed to load sources from %s: %s", sources_resolved, exc)
            report.errors.append(f"load_sources: {exc}")
            try:
                from app import observability
                observability.fetch_finished(summary="failed", error=f"load_sources: {exc}")
            except Exception:
                pass
            return report

        sources = sources_file.sources

        # --- Load profile ---
        try:
            profile_md = profile_resolved.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("run_fetch_cycle: profile file not found at %s; using empty profile", profile_resolved)
            profile_md = ""
        except Exception as exc:
            logger.warning("run_fetch_cycle: could not read profile %s: %s; using empty", profile_resolved, exc)
            profile_md = ""

        # --- Open DB connection for the whole cycle ---
        conn = get_connection(db_path)
        try:
            # --- Per-source fetch + insert ---
            for source in sources:
                # Apply source filter if specified
                if source_filter and (source.title or "").lower() != source_filter.lower():
                    continue

                report.sources_attempted += 1
                try:
                    raw_items = fetch_source(source)
                except Exception as exc:
                    msg = f"fetch_source({source}): {exc}"
                    logger.warning("run_fetch_cycle: %s", msg)
                    report.errors.append(msg)
                    continue

                report.items_fetched += len(raw_items)

                if dry_run:
                    # In dry_run mode: count items but don't persist
                    continue

                # Persist (or refresh) the source row so we can attach a
                # source_id to every item from this feed. Best-effort: if
                # upsert fails for any reason, fall back to NULL source_id
                # rather than failing the whole fetch.
                try:
                    source_id = upsert_source(
                        conn,
                        kind=source.kind,
                        url=_source_identifier(source),
                        title=getattr(source, "title", None),
                    )
                except Exception as exc:
                    logger.warning(
                        "run_fetch_cycle: upsert_source failed for %s: %s",
                        source, exc,
                    )
                    source_id = None

                # Load recent items once per source for dedup comparison
                recent_items = get_recent_items_for_dedup(conn, days=7)

                items_skipped_age = 0
                for raw_item in raw_items:
                    now = int(time.time())

                    # Age gate: drop items older than MAX_ITEM_AGE_DAYS based
                    # on the feed's own published timestamp. Items with no
                    # published_at fall through (no age available -> keep).
                    if (
                        raw_item.published_at is not None
                        and raw_item.published_at < now - MAX_ITEM_AGE_SECONDS
                    ):
                        items_skipped_age += 1
                        continue

                    item_id = insert_item_if_new(
                        conn,
                        source_id=source_id,
                        url=raw_item.url,
                        canonical_url=raw_item.canonical_url,
                        title=raw_item.title,
                        author=raw_item.author,
                        published_at=raw_item.published_at,
                        fetched_at=now,
                        excerpt=raw_item.excerpt,
                        score=0.0,
                        is_read=0,
                        total_dwell_seconds=0.0,
                    )

                    if item_id is not None:
                        report.items_new += 1

                        # Dedup check
                        dedup_result = dedup_item(raw_item, recent_items)

                        if dedup_result.is_duplicate and dedup_result.cluster_id is not None:
                            # Assign to existing cluster
                            conn.execute(
                                "UPDATE items SET cluster_id=? WHERE id=?",
                                (dedup_result.cluster_id, item_id),
                            )
                            increment_cluster_member(conn, dedup_result.cluster_id)
                        elif dedup_result.is_duplicate and dedup_result.matched_item_id is not None:
                            # Matched item exists but has no cluster yet — create one
                            cluster_id = get_or_create_cluster(conn, dedup_result.matched_item_id)
                            conn.execute(
                                "UPDATE items SET cluster_id=? WHERE id=?",
                                (cluster_id, item_id),
                            )
                            increment_cluster_member(conn, cluster_id)

                conn.commit()

                if items_skipped_age:
                    logger.info(
                        "Skipped %d items older than %d days from %s",
                        items_skipped_age, MAX_ITEM_AGE_DAYS, source,
                    )

            if not dry_run:
                # --- Rank unranked items ---
                unranked = get_unranked_items(conn, since_hours=24)
                if unranked:
                    try:
                        scores = await rank_items(unranked, profile_md, conn)
                        conn.commit()
                        report.items_ranked = len([s for s in scores.values() if s > 0.0])
                    except Exception as exc:
                        logger.warning("run_fetch_cycle: rank_items failed: %s", exc)
                        report.errors.append(f"rank_items: {exc}")

                # --- Pre-generate summaries for top 20 scored items ---
                await _pre_summarize_top(conn)

        finally:
            conn.close()

        # --- Write last_fetch.txt (skipped in dry_run) ---
        if not dry_run:
            try:
                _LAST_FETCH_FILE.parent.mkdir(parents=True, exist_ok=True)
                _LAST_FETCH_FILE.write_text(
                    datetime.now(timezone.utc).isoformat(),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning("run_fetch_cycle: could not write last_fetch.txt: %s", exc)

    finally:
        lock.release()

    report.duration_seconds = time.monotonic() - start_time
    logger.info(
        "run_fetch_cycle: done in %.2fs — sources=%d fetched=%d new=%d ranked=%d errors=%d",
        report.duration_seconds,
        report.sources_attempted,
        report.items_fetched,
        report.items_new,
        report.items_ranked,
        len(report.errors),
    )

    try:
        from app import observability
        summary = (
            f"fetched={report.items_fetched} new={report.items_new} "
            f"ranked={report.items_ranked} errors={len(report.errors)} "
            f"in {report.duration_seconds:.1f}s"
        )
        observability.fetch_finished(summary=summary, error="")
    except Exception:
        pass

    return report


async def _pre_summarize_top(conn, top_n: int = 20) -> None:
    """Pre-generate AI summaries for top-scored items so drawer clicks are instant."""
    from app.summarize import summarize_item

    items = get_top_items_without_summary(conn, hours=24, limit=top_n)
    if not items:
        return

    logger.info("Pre-generating summaries for %d top items...", len(items))
    sem = asyncio.Semaphore(2)  # 2 concurrent Claude calls

    async def _one(item):
        async with sem:
            try:
                await summarize_item(item, conn)
            except Exception as exc:
                logger.warning("pre-summarize failed item %d: %s", item.id, exc)

    await asyncio.gather(*[_one(item) for item in items])
    try:
        conn.commit()
    except Exception:
        pass
    logger.info("Pre-summarize done.")
