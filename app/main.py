"""
app/main.py
FastAPI application entry point for FeedsAI.
"""
import asyncio
import logging
import shutil
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Install ring-buffer + rotating-file log handlers BEFORE app boots so we
# capture startup lines too.
from app import observability  # noqa: E402
from app.paths import logs_dir  # noqa: E402

_LOG_PATH = observability.install_handlers(logs_dir())
logger.info("Server log file: %s", _LOG_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # 1. Initialize DB schema
    from app.db import init_schema
    init_schema()
    logger.info("Database schema initialized.")

    # 2. Check if data is stale and trigger background fetch if needed
    from app.onboarding import setup_required
    if setup_required():
        logger.info("First-run setup required; skipping background fetch until /setup is complete")
    else:
        from app.startup import startup_check
        await startup_check()

    # 3. Check claude CLI on PATH
    if shutil.which("claude") is None:
        logger.warning("'claude' CLI not found on PATH - AI ranking/profile updates will not work")
    else:
        logger.info("'claude' CLI found on PATH.")

    if shutil.which("gemini") is None:
        logger.info("'gemini' CLI not found on PATH; optional fallback unavailable")
    else:
        logger.info("'gemini' CLI found on PATH as optional fallback.")

    logger.info("FeedsAI ready at http://127.0.0.1:8000  (status: /status, logs: /logs)")

    yield
    # --- Shutdown ---
    from app.startup import _fetch_task
    if _fetch_task and not _fetch_task.done():
        _fetch_task.cancel()
        try:
            await _fetch_task
        except asyncio.CancelledError:
            pass
    logger.info("FeedsAI shutting down.")


app = FastAPI(title="FeedsAI", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request metrics middleware — counts every request for /status display.
# ---------------------------------------------------------------------------
@app.middleware("http")
async def _request_metrics(request: Request, call_next):
    start = time.monotonic()
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        status_code = 500
        raise
    finally:
        observability.record_request(request.url.path, status_code)
        # Don't double-log access lines — uvicorn already logs them.
        _ = time.monotonic() - start


# Include routes
from app.routes import ask, digest, items, learning, logs as logs_route, search, settings, setup, sources, status  # noqa: E402

app.include_router(setup.router)
app.include_router(settings.router)
app.include_router(digest.router)
app.include_router(items.router)
app.include_router(ask.router)
app.include_router(search.router)
app.include_router(learning.router)
app.include_router(sources.router)
app.include_router(status.router)
app.include_router(logs_route.router)
