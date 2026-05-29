# FeedsAI Starter

**Version:** 0.1.0

A local-first, LLM-ranked feed reader you tune with a markdown profile.
FastAPI + HTMX. Fetches RSS / Hacker News / arXiv / GitHub release feeds,
ranks each item 0–10 with Claude CLI against `profile.md`, summarizes with
Gemini CLI (Claude fallback), and serves a scored digest at `localhost:8000`.

Fork this template, fill in `profile.md`, point at your feeds, run.

## Feature set

- Profile-driven ranking 0–10 via Claude CLI
- Gemini-first summarization (Claude fallback)
- Topic tabs (configurable per-profile)
- Pre-generated summaries for top items (instant drawer)
- Like button for engagement-driven profile learning
- Show-more pagination, dwell tracking, weekly profile-update job
- **Observability**: live `/status`, `/logs`, rotating `data/server.log`, `scripts/run_server.ps1 -Detach` launcher
- **Quota-aware LLM fallback**: Gemini quota exhaustion detected from stderr, model marked unavailable for session, Claude takes over instantly
- **7-day feed age gate**: items older than 7 days dropped at ingest
- **Task Scheduler**: `FeedsAI_Fetch` (3×/day) + `FeedsAI_ProfileUpdate` (weekly) registration scripts

## First-run setup

```powershell
python scripts/init.py    # copies example files, runs uv sync + healthcheck
# then edit profile.md to your interests, sources.yaml to your feeds
```

## Run / restart

```powershell
.\scripts\run_server.ps1 -Detach    # detached window with live uvicorn logs
# OR
.\scripts\run_server.ps1             # foreground in current shell
```

The script auto-stops any stale uvicorn already bound to port 8000.

## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo — one `CONTEXT.md` at root + `docs/adr/`. See `docs/agents/domain.md`.
