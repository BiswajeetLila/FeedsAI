"""
app/routes/status.py
Health/status page route. Shows fetch health, uptime, request counters,
LLM call stats, scheduled-task info, and a manual fetch trigger so you
can verify the server is alive and healthy without leaving the browser.
"""
import asyncio
import logging
import shutil
import subprocess
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import observability
from app.db import get_all_sources, get_db
from app.onboarding import setup_required
from app.paths import data_dir, user_root
from app.startup import _LAST_FETCH_FILE, is_data_stale
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_last_fetch() -> str:
    if not _LAST_FETCH_FILE.exists():
        return "Never"
    try:
        return _LAST_FETCH_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return "Unknown"


def _get_scheduled_tasks() -> list[dict]:
    """Best-effort Get-ScheduledTask query. Returns [] on non-Windows or failure."""
    try:
        ps = (
            "Get-ScheduledTask -TaskName 'FeedsAI*' "
            "-ErrorAction SilentlyContinue | ForEach-Object { "
            "$i = Get-ScheduledTaskInfo $_; "
            "[PSCustomObject]@{name=$_.TaskName; state=$_.State.ToString(); "
            "next=$i.NextRunTime.ToString('yyyy-MM-dd HH:mm'); "
            "last=$i.LastRunTime.ToString('yyyy-MM-dd HH:mm')} } | "
            "ConvertTo-Json -Compress"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        import json
        data = json.loads(r.stdout)
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception as exc:
        logger.debug("Could not query Get-ScheduledTask: %s", exc)
        return []


def _collect() -> dict:
    last_fetch = _get_last_fetch()
    stale = is_data_stale()

    source_count = 0
    item_count = 0
    ranked_today = 0
    liked_count = 0
    with get_db() as conn:
        try:
            source_count = len(get_all_sources(conn))
        except Exception as exc:
            logger.warning("Could not get source count: %s", exc)

        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM items").fetchone()
            item_count = row["cnt"] if row else 0
        except Exception as exc:
            logger.warning("Could not get item count: %s", exc)

        try:
            today_start = int(time.time()) - 86400
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM items WHERE score > 0 AND fetched_at > ?",
                (today_start,),
            ).fetchone()
            ranked_today = row["cnt"] if row else 0
        except Exception as exc:
            logger.warning("Could not get ranked_today count: %s", exc)

        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM items WHERE is_liked=1").fetchone()
            liked_count = row["cnt"] if row else 0
        except Exception as exc:
            logger.warning("Could not get liked count: %s", exc)

    boot_dt = datetime.fromtimestamp(observability.BOOT_WALL).strftime("%Y-%m-%d %H:%M:%S")
    req = observability.request_stats
    fs = observability.fetch_state
    fetch_started_dt = (
        datetime.fromtimestamp(fs.started_at).strftime("%Y-%m-%d %H:%M:%S")
        if fs.started_at else "—"
    )
    fetch_finished_dt = (
        datetime.fromtimestamp(fs.finished_at).strftime("%Y-%m-%d %H:%M:%S")
        if fs.finished_at else "—"
    )
    fetch_elapsed = (
        int(time.time() - fs.started_at) if fs.in_progress and fs.started_at else 0
    )

    return {
        "ok": True,
        "setup_required": setup_required(),
        "last_fetch": last_fetch,
        "is_stale": stale,
        "source_count": source_count,
        "item_count": item_count,
        "ranked_today": ranked_today,
        "liked_count": liked_count,
        "uptime": observability.format_uptime(),
        "boot_time": boot_dt,
        "request_total": req.total,
        "last_request_path": req.last_path or "—",
        "last_request_status": req.last_status or "—",
        "status_by_code": dict(req.by_status),
        "llm_stats": observability.llm_snapshot(),
        "llm_availability": {
            "claude": shutil.which("claude") or "",
            "gemini": shutil.which("gemini") or "",
        },
        "user_root": str(user_root()),
        "data_dir": str(data_dir()),
        "fetch_in_progress": fs.in_progress,
        "fetch_started": fetch_started_dt,
        "fetch_finished": fetch_finished_dt,
        "fetch_elapsed": fetch_elapsed,
        "fetch_last_summary": fs.last_summary,
        "fetch_last_error": fs.last_error,
        "scheduled_tasks": _get_scheduled_tasks(),
    }


@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request):
    ctx = _collect()
    return templates.TemplateResponse(request, "status.html", ctx)


@router.get("/status.json")
async def status_json():
    """Machine-readable status — useful for healthcheck scripts."""
    return JSONResponse(_collect())


@router.get("/healthz")
async def healthz():
    """Tiny server-running check for launchers and monitors."""
    return JSONResponse({
        "ok": True,
        "uptime_seconds": round(observability.uptime_seconds(), 1),
        "setup_required": setup_required(),
        "fetch_in_progress": observability.fetch_state.in_progress,
    })


_manual_fetch_task: asyncio.Task | None = None


async def _spawn_manual_fetch() -> None:
    import importlib
    pipeline_mod = importlib.import_module("app.pipeline")
    try:
        await pipeline_mod.run_fetch_cycle()
    except Exception as exc:
        logger.error("Manual fetch failed: %s", exc, exc_info=True)


@router.post("/fetch/trigger")
async def fetch_trigger():
    """
    Kick off a fetch cycle in the background. Idempotent: if one is already
    running (either auto-startup or another manual click), returns 202 and
    does nothing.
    """
    global _manual_fetch_task

    if observability.fetch_state.in_progress:
        return JSONResponse(
            {"ok": True, "queued": False, "reason": "fetch already in progress"},
            status_code=202,
        )

    if _manual_fetch_task and not _manual_fetch_task.done():
        return JSONResponse(
            {"ok": True, "queued": False, "reason": "fetch task already scheduled"},
            status_code=202,
        )

    _manual_fetch_task = asyncio.create_task(_spawn_manual_fetch())
    logger.info("Manual fetch triggered via /fetch/trigger")
    return JSONResponse({"ok": True, "queued": True})
