"""
First-time setup routes.
"""
import asyncio
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.onboarding import build_profile, build_sources, setup_required, write_setup
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    return templates.TemplateResponse(
        request,
        "setup.html",
        {"setup_required": setup_required()},
    )


@router.post("/setup")
async def save_setup(
    reader_name: str = Form(""),
    archetype: str = Form(""),
    top_interests: str = Form(""),
    secondary_interests: str = Form(""),
    avoid_topics: str = Form(""),
    region: str = Form(""),
    include_hn: bool = Form(False),
    include_simon: bool = Form(False),
    include_quanta: bool = Form(False),
    arxiv_queries: str = Form(""),
    rss_urls: str = Form(""),
    github_repos: str = Form(""),
    run_fetch: bool = Form(False),
):
    profile_md = build_profile(
        reader_name=reader_name,
        archetype=archetype,
        top_interests=top_interests,
        secondary_interests=secondary_interests,
        avoid_topics=avoid_topics,
        region=region,
    )
    sources_yaml = build_sources(
        include_hn=include_hn,
        include_simon=include_simon,
        include_quanta=include_quanta,
        arxiv_queries=arxiv_queries,
        rss_urls=rss_urls,
        github_repos=github_repos,
    )
    write_setup(profile_md, sources_yaml)
    logger.info("First-run setup saved profile.md and sources.yaml")

    if run_fetch:
        import importlib
        pipeline_mod = importlib.import_module("app.pipeline")
        asyncio.create_task(pipeline_mod.run_fetch_cycle())
        return RedirectResponse("/status", status_code=303)

    return RedirectResponse("/", status_code=303)
