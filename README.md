# FeedsAI Starter

> A local-first, LLM-ranked feed reader you tune with a markdown file.

New user? Start with [USER_README.md](USER_README.md). Product plan: [docs/next-product-plan.md](docs/next-product-plan.md).

Fork this template, write a `profile.md` describing what you care about, point
`sources.yaml` at your feeds, run. The app fetches RSS / Hacker News / arXiv /
GitHub release feeds, ranks every item 0–10 with Claude CLI against your
profile, and serves a scored digest at `http://localhost:8000`.

No cloud database. No API keys to manage. No analytics. Runs on your machine,
reads your data, dies when you close it.

**Stack:** Python 3.11+ · FastAPI · HTMX · SQLite · Claude CLI · Windows-friendly.

---

## Quickstart

```bash
# 1. Use this template (GitHub "Use this template" button), then clone your copy.
git clone https://github.com/<you>/<your-repo>.git
cd <your-repo>

# 2. First-run wizard — checks claude CLI, copies example files, runs uv sync + healthcheck.
python scripts/init.py

# 3. Edit profile.md to reflect what you actually want to read.
#    Edit sources.yaml if the default feed list doesn't match your taste.

# 4. First fetch (takes a few minutes — every item is ranked by Claude).
python scripts/fetch.py --verbose

# 5. Start the web server.
.\scripts\run_server.ps1 -Detach    # Windows: detached window with live logs
# (or: uv run uvicorn app.main:app --port 8000  on macOS/Linux)

# 6. Open browser.
start http://localhost:8000          # Windows
# open http://localhost:8000         # macOS
```

That's it. The digest auto-refreshes 3×/day if you register the Task Scheduler
job (Windows) or set up a cron equivalent.

---

## How ranking works

1. Each fetch cycle pulls items from every source listed in `sources.yaml`,
   dedupes them (canonical URL + fuzzy title), and writes them to SQLite.
2. Every unranked item from the last 24 h is batched (50 at a time) and sent
   to Claude CLI as JSON, with the contents of `profile.md` as the rubric.
3. Claude returns a `{"rankings": [{"id": N, "score": 0.0-10.0, "rationale":
   "...", "topic": "..."}]}` per batch. Scores land in `items.score`, the
   tier badge is derived: ≥8 = Top pick, ≥5 = Relevant, else Borderline.
4. Drawer clicks are instant because they use feed excerpts plus the ranking
   rationale already produced during scoring.
5. The digest at `/` shows the top 10 ranked items from the last 7 d, filterable
   by topic tab.

The whole loop is profile-driven. If you don't like what you're being served,
the answer is almost always "rewrite `profile.md` to be more specific."

---

## Customize

### `profile.md`

Your interest profile. Two sections by convention: **Global** content and a
**regional bonus** (+1.5 to local items). Tiers inside each section: 8–10
(must-read), 5–7 (interested), 0–4 (avoid). Be specific — examples beat
adjectives. See `profile.md.example` for the structure.

A weekly job (`scripts/update_profile.py --preview`) reads your engagement
data and proposes edits to `profile.md` based on what you actually opened,
liked, or lingered on. Review the diff in your terminal, apply if it looks
right.

### `sources.yaml`

The feed list. Supported `kind:` values:

| kind              | required fields | example                                       |
|-------------------|-----------------|-----------------------------------------------|
| `rss`             | `url`           | any RSS 2.0 or Atom feed                      |
| `hn`              | (none)          | Hacker News front page via Firebase API       |
| `arxiv`           | `query`         | `cat:cs.AI`, `cat:cs.RO`, `cat:astro-ph`, ... |
| `github_releases` | `repo`          | `anthropics/claude-code`                      |

See `sources.yaml.example` for the full schema with comments. Add a feed and
the next fetch picks it up.

### `prompts/rank_v1.txt`

The LLM ranking prompt template. Edit if rankings start misfiring. Versioned
filenames let you A/B compare.

---

## Run / restart

```powershell
.\scripts\run_server.ps1 -Detach    # detached window with live uvicorn logs
# OR
.\scripts\run_server.ps1             # foreground in current shell
```

The script auto-stops any stale uvicorn already bound to port 8000.

On macOS/Linux:

```bash
uv run uvicorn app.main:app --port 8000
```

---

## Observability — is the server actually running?

Three independent answers:

1. **`/status`** — uptime, total requests, by-status breakdown, last-fetch
   summary, per-model LLM call stats (claude / gemini), fetch-in-progress
   banner, "Fetch now" button, scheduled-task panel. Auto-refresh 10 s.
2. **`/logs`** — tails the in-process ring buffer (last 200 lines, auto-refresh
   3 s, WARNING/ERROR colour-coded). `/logs.txt` for plain-text piping.
3. **`data/server.log`** — rotating file handler (2 MB × 3). Tail with
   `Get-Content data\server.log -Wait` (Windows) or `tail -f data/server.log`.

`/status.json` returns the same data as JSON for cron healthchecks.

---

## Daily operation

| When                | What you do                                  | What happens                                                  |
|---------------------|----------------------------------------------|---------------------------------------------------------------|
| Morning             | Open `localhost:8000`                        | Read top 10. Click items to expand instant feed context.      |
| Anytime             | `python scripts/fetch.py --verbose`          | Manual refresh — useful when Task Scheduler missed a run.     |
| Edit `sources.yaml` | Add or remove feeds                          | Next fetch picks up the change.                               |
| Edit `profile.md`   | Shift interests                              | New items get the new ranking; old scores persist.            |
| Weekly              | `python scripts/update_profile.py --preview` | Review engagement-driven profile edits, apply via `git diff`. |
| Check health        | `localhost:8000/status`                      | Last fetch, item / source counts, LLM stats, source warnings. |

---

## Privacy / data

- Everything is local. SQLite file at `data/feeds.db`, logs at `data/server.log`,
  fetch state at `data/last_fetch.txt`.
- No analytics. No telemetry. The web app binds to `127.0.0.1` by default.
- The only network calls go to: the feed URLs in your `sources.yaml`, the
  GitHub release API for `github_releases` sources, and the Claude CLI
  (which talks to Anthropic).
- Want to point at a public IP for phone access? Edit
  `scripts/run_server.ps1` to bind `0.0.0.0` and gate via your own VPN /
  Tailscale / reverse-proxy auth. There is no built-in auth — by design.

---

## Project layout

```
app/
├── main.py                # FastAPI assembly + lifespan
├── startup.py             # Background fetch on app start if data > 2h stale
├── config.py              # sources.yaml Pydantic schema + loader
├── db.py                  # SQLite schema + typed query functions
├── llm.py                 # claude/gemini CLI wrapper (async subprocess)
├── pipeline.py            # Orchestrator: fetch -> dedup -> rank
├── dedup.py               # rapidfuzz title match
├── rank.py                # Batch LLM scoring with halving retry
├── summarize.py           # No-LLM drawer insight compatibility helpers
├── profile_update.py      # Engagement -> proposed profile.md diff
├── ingest/                # rss, hn, arxiv, github_releases
├── routes/                # digest, items, status, logs
├── observability.py       # Uptime, counters, LLM stats, log handlers
└── templates/             # Jinja2 templates

scripts/
├── init.py                # First-run setup wizard
├── fetch.py               # Standalone fetch CLI
├── healthcheck.py         # Smoke test (DB, sources, claude CLI, first feed)
├── update_profile.py      # Weekly profile-update job
├── run_server.ps1         # Launch uvicorn (foreground or detached window)
├── register_task.ps1      # Windows Task Scheduler registration
└── task_status.ps1        # Inspect scheduled job state

tests/                     # pytest test suite
prompts/                   # Versioned LLM prompt templates
docs/                      # Agent conventions (issue tracker, triage, domain)
```

---

## Troubleshooting

| Symptom                                       | Likely cause                                | Fix                                                                  |
|-----------------------------------------------|---------------------------------------------|----------------------------------------------------------------------|
| Nothing scored, all "Borderline"              | Claude rate-limited mid-fetch               | Run `scripts/fetch.py --verbose` again later                         |
| Drawer content is thin                         | Feed did not provide an excerpt             | Open original article; add a better feed if this source is sparse    |
| 500 error on `/`                              | Template / data shape changed               | Check `/logs` page or `data/server.log`                              |
| Drawer click does nothing                     | uvicorn died; browser is showing stale HTML | `.\scripts\run_server.ps1 -Detach`, refresh tab                      |
| `claude` CLI not found                        | PATH issue                                  | `where.exe claude` should point to your install                      |
| Items not deduplicating                       | Threshold too high for your sources         | Lower `RAPIDFUZZ_THRESHOLD` in `app/dedup.py` (default 85)           |
| "Bozo feed" warnings                          | Feed XML malformed by source                | feedparser still extracts entries; can ignore or replace the URL     |
| Fresh fetch but `last_fetch.txt` not updated  | Lock held / process killed mid-cycle        | Delete `data\fetch.lock`, re-run                                     |

---

## Tests

```powershell
.venv\Scripts\pytest.exe tests/ -q
```

---

## License

MIT. See `LICENSE`.
