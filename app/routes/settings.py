"""
Settings routes for user-managed local config.
"""
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import observability, source_config
from app.db import get_db, get_source_fetch_health
from app.templates_config import templates

router = APIRouter()
logger = logging.getLogger(__name__)


def _source_from_form(kind: str, value: str, title: str) -> dict:
    clean_value = value.strip()
    source: dict = {"kind": kind, "enabled": True}
    if title.strip():
        source["title"] = title.strip()

    if kind == "rss":
        source["url"] = clean_value
    elif kind == "hn":
        source["filter"] = clean_value or "front_page"
        source.setdefault("title", "Hacker News")
    elif kind == "arxiv":
        source["query"] = clean_value
    elif kind == "github_releases":
        source["repo"] = clean_value
    else:
        raise ValueError(f"Unsupported source kind: {kind}")
    return source


def _sources_with_health() -> list[dict]:
    entries = source_config.list_source_entries(source_config.DEFAULT_SOURCES_PATH)
    try:
        with get_db() as conn:
            health_by_key = get_source_fetch_health(conn)
    except Exception as exc:
        logger.warning("Could not load source health: %s", exc)
        health_by_key = {}

    for entry in entries:
        health = dict(health_by_key.get(entry["key"], {}))
        for field in ("last_attempted_at", "last_success_at"):
            if health.get(field):
                health[f"{field}_label"] = datetime.fromtimestamp(health[field]).strftime("%Y-%m-%d %H:%M")
        entry["health"] = health
    return entries


async def _run_source_fetch(key: str) -> None:
    import importlib
    pipeline_mod = importlib.import_module("app.pipeline")
    try:
        await pipeline_mod.run_fetch_cycle(source_key_filter=key)
    except Exception as exc:
        logger.error("Source fetch failed for %s: %s", key, exc, exc_info=True)


def _schedule_source_fetch(key: str) -> asyncio.Task:
    return asyncio.create_task(_run_source_fetch(key))


@router.get("/settings/sources", response_class=HTMLResponse)
async def settings_sources(request: Request):
    entries = _sources_with_health()
    return templates.TemplateResponse(
        request,
        "settings_sources.html",
        {"sources": entries, "error": ""},
    )


@router.post("/settings/sources/add")
async def settings_sources_add(
    kind: str = Form(...),
    value: str = Form(""),
    title: str = Form(""),
):
    source = _source_from_form(kind, value, title)
    source_config.add_source_entry(source_config.DEFAULT_SOURCES_PATH, source)
    return RedirectResponse("/settings/sources", status_code=303)


@router.post("/settings/sources/toggle")
async def settings_sources_toggle(
    key: str = Form(...),
    enabled: bool = Form(False),
):
    source_config.set_source_enabled(source_config.DEFAULT_SOURCES_PATH, key, enabled)
    return RedirectResponse("/settings/sources", status_code=303)


@router.post("/settings/sources/remove")
async def settings_sources_remove(key: str = Form(...)):
    source_config.remove_source_entry(source_config.DEFAULT_SOURCES_PATH, key)
    return RedirectResponse("/settings/sources", status_code=303)


@router.post("/settings/sources/fetch")
async def settings_sources_fetch(key: str = Form(...)):
    if not observability.fetch_state.in_progress:
        _schedule_source_fetch(key)
        logger.info("Manual source fetch triggered for %s", key)
    return RedirectResponse("/status", status_code=303)
