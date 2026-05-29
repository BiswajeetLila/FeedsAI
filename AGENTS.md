# FeedsAI Starter

**Version:** 0.1.0

Local-first feed reader: FastAPI + HTMX. Fetches RSS / Hacker News / arXiv / GitHub
release feeds, ranks each item 0–10 with Claude CLI against `profile.md`, summarizes
with Gemini CLI, presents a scored digest at `localhost:8000`.

## Feature set

- Profile-driven ranking 0–10 via Claude CLI
- Gemini-first summarization (Claude fallback)
- Topic tabs (configurable per-profile)
- Pre-generated summaries for top items (instant drawer)
- Like button for engagement-driven profile learning
- Show-more pagination, dwell tracking, weekly profile-update job
- Observability: `/status`, `/logs`, rotating `data/server.log`, `scripts/run_server.ps1 -Detach`
- Quota-aware LLM fallback: stderr-detected `QUOTA_EXHAUSTED` marks model unavailable for session
- 7-day age gate on ingest (`MAX_ITEM_AGE_DAYS=7` in `app/pipeline.py`); digest filter uses `COALESCE(published_at, fetched_at)`
- Task Scheduler: fetch 3x/day + weekly profile-update (registered via `scripts/register_task.ps1`)

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo — one `CONTEXT.md` at root + `docs/adr/`. See `docs/agents/domain.md`.
