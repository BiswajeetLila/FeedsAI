# FeedsAI Starter

Local-first feed dashboard: FastAPI, HTMX, SQLite, RSS/Hacker News/arXiv/GitHub
release feeds, and profile-driven ranking through local Claude/Gemini CLIs.

New user? Start with [USER_README.md](USER_README.md). Product roadmap:
[docs/next-product-plan.md](docs/next-product-plan.md).

Current milestone: FeedsAI has first-run setup, in-app source management, local
search, a learning dashboard, recommendation explanations, source health, and
Windows packaging-readiness scaffolding.

No cloud database. No analytics. The app binds to `127.0.0.1` and keeps user
data on the local machine.

## Quickstart For Normal Use

On Windows, double-click `FeedsAI.bat`. The app opens in your browser.

- First-time users land on `/setup`.
- Daily use starts at `/`.
- `/status` shows whether the server is running, current fetch state, last
  fetch result, LLM availability, and logs.
- `/settings/sources` lets users add, pause, remove, and test feeds.

## Developer Quickstart

```powershell
git clone https://github.com/<you>/<your-repo>.git
cd <your-repo>

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .

.\FeedsAI.bat
```

Optional manual fetch:

```powershell
.\.venv\Scripts\python.exe scripts\fetch.py --verbose
```

## Core Workflow

1. Fetch reads enabled sources from `sources.yaml`.
2. New items are deduplicated and written to SQLite.
3. Unranked recent items are ranked 0-10 against `profile.md`.
4. The digest shows ranked, balanced, or fresh views.
5. Drawer context, "Why am I seeing this?", search, and learning analytics use
   local stored metadata and do not add summary calls.

LLM usage is intentionally limited to ranking, explicit `/ask` questions, and
profile-update proposals.

## Key Pages

- `/` - digest.
- `/setup` - first-run and preference setup.
- `/settings/sources` - add, pause, remove, and test feeds.
- `/sources` - source usefulness metrics.
- `/search` - local search over title, excerpt, source, topic, and rationale.
- `/learning` - engagement analytics and profile-update readiness.
- `/ask` - ask questions about recent feed items.
- `/status` - server, fetch, data, and LLM status.
- `/logs` - in-app log tail.

## User-Owned Files

- `profile.md` - ranking preferences.
- `sources.yaml` - feed list.
- `data/feeds.db` - SQLite database in dev mode.
- `data/server.log` - rotating server log in dev mode.
- `data/last_fetch.txt` - fetch freshness marker in dev mode.

In packaged mode, mutable user data moves to `%LOCALAPPDATA%\FeedsAI`.

## Packaging Preview

The developer workflow remains repo-first and editable. To build a Windows app
folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_app.ps1
```

Output:

```text
dist\FeedsAI\FeedsAI.exe
```

This is packaging readiness, not a polished installer yet. The next packaging
step is an installer with Start Menu and Desktop shortcuts.

## Source Management

Most users should manage sources at `/settings/sources`. The YAML file remains
the portable source of truth.

Supported source kinds:

| kind | required fields | example |
| --- | --- | --- |
| `rss` | `url` | RSS or Atom feed URL |
| `hn` | optional `filter` | `front_page` |
| `arxiv` | `query` | `cat:cs.AI` |
| `github_releases` | `repo` | `anthropics/claude-code` |

Each source has a stable key, can be disabled, and can be fetched individually
from the settings page.

## Observability

- `/status` - uptime, requests, user data path, fetch state, last fetch result,
  LLM CLI availability, scheduled task info, and manual fetch.
- `/status.json` - machine-readable status.
- `/healthz` - tiny launcher health check.
- `/logs` and `/logs.txt` - recent in-process logs.
- `data/server.log` - rotating file log in dev mode.

## Project Layout

```text
app/
  main.py              FastAPI assembly and lifespan
  paths.py             Dev vs packaged runtime paths
  launcher.py          Start URL, status URL, port helpers
  desktop_launcher.py  Packaged-app entrypoint
  config.py            sources.yaml Pydantic schema and loader
  source_config.py     Safe source config edits
  db.py                SQLite schema and query helpers
  pipeline.py          Fetch, dedup, rank orchestration
  search.py            SQLite FTS/LIKE search
  learning.py          Engagement analytics
  explain.py           Deterministic recommendation explanations
  routes/              Digest, setup, settings, search, learning, status, logs
  templates/           Jinja2 templates

scripts/
  start_app.ps1        FeedsAI.bat launch path
  fetch.py             Standalone fetch CLI
  healthcheck.py       Smoke checks
  update_profile.py    Profile-update proposal CLI
  build_windows_app.ps1 PyInstaller onedir build
```

## Tests

Use a repo-local pytest temp dir on this Windows machine because the default
user temp directory can be inaccessible from the agent process.

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest_tmp
```

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| App opens old behavior | Server was already running | Close the FeedsAI terminal and reopen `FeedsAI.bat` |
| Nothing scored | Claude/Gemini CLI unavailable or rate-limited | Check `/status`, then retry fetch later |
| Source fetch fails | Feed URL or network problem | Open `/settings/sources`, check source health |
| 500 error | Runtime/template issue | Open `/logs` or `data/server.log` |
| Packaged app cannot find data | Path issue | Confirm packaged mode uses `%LOCALAPPDATA%\FeedsAI` |

## License

MIT. See [LICENSE](LICENSE).
