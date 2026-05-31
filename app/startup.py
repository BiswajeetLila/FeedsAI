"""
app/startup.py
Lifespan startup logic for FeedsAI.
"""
import asyncio
import logging
from datetime import datetime, timezone

from app.paths import last_fetch_path

logger = logging.getLogger(__name__)

_fetch_task: asyncio.Task | None = None

_LAST_FETCH_FILE = last_fetch_path()
STALE_THRESHOLD_SECONDS = 7200  # 2 hours


def is_data_stale() -> bool:
    """Returns True if last_fetch.txt missing or > 2h old."""
    if not _LAST_FETCH_FILE.exists():
        return True
    try:
        text = _LAST_FETCH_FILE.read_text(encoding="utf-8").strip()
        last_fetch = datetime.fromisoformat(text)
        # Ensure timezone-aware comparison
        if last_fetch.tzinfo is None:
            last_fetch = last_fetch.replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        age_seconds = (now - last_fetch).total_seconds()
        return age_seconds > STALE_THRESHOLD_SECONDS
    except Exception as exc:
        logger.warning("Could not parse last_fetch.txt: %s", exc)
        return True


async def _background_fetch() -> None:
    """Run fetch pipeline in background without blocking startup."""
    try:
        logger.info("Starting background fetch (data was stale)...")
        # Import here to avoid circular imports and to allow Task 5 to implement pipeline
        import importlib
        pipeline_mod = importlib.import_module("app.pipeline")
        if hasattr(pipeline_mod, "run_fetch_cycle"):
            # run_fetch_cycle itself calls observability.fetch_started/finished
            # so /status reflects in-progress state.
            await pipeline_mod.run_fetch_cycle()
            logger.info("Background fetch complete.")
        else:
            logger.warning("app.pipeline.run_fetch_cycle not found — skipping background fetch")
    except ImportError:
        logger.warning("app.pipeline not available — skipping background fetch")
    except Exception as exc:
        logger.error("Background fetch failed: %s", exc, exc_info=True)
        try:
            from app import observability
            observability.fetch_finished(summary="", error=str(exc))
        except Exception:
            pass


async def startup_check() -> None:
    """
    Called from FastAPI lifespan. Triggers background fetch if data is stale.
    Reads data/last_fetch.txt (ISO timestamp). If missing or older than 2h,
    triggers fetch in background (asyncio.create_task).
    Never blocks startup.
    """
    global _fetch_task
    if is_data_stale():
        logger.info("Data is stale — scheduling background fetch")
        _fetch_task = asyncio.create_task(_background_fetch())
        logger.info("Background fetch started (data was stale)")
    else:
        logger.info("Data is fresh — skipping background fetch")
