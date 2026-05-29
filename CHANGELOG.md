# Changelog

All notable changes to FeedsAI Starter.

## [0.1.0] — 2026-05-29

First public release of FeedsAI Starter — a depersonalized fork-and-go
template derived from a personal FeedsAI deployment.

### Added
- **First-run wizard** (`scripts/init.py`): checks `claude` CLI, copies
  `profile.md.example` -> `profile.md`, copies `sources.yaml.example` ->
  `sources.yaml`, runs `uv sync`, runs `scripts/healthcheck.py`. Re-runnable.
- **Generic profile template** (`profile.md.example`): two-section structure
  (Global + regional bonus), three-tier scoring guide. Placeholder text for
  the reader to fill in.
- **Minimal default sources** (`sources.yaml.example`): Simon Willison, Quanta,
  Hacker News, four arXiv categories, three GitHub release feeds. Known-dead
  feeds (OpenAI/Anthropic blogs) documented as such, not active examples.
- **MIT LICENSE**.

### Fixed (carried from upstream)
- **`sources` table population**: `app/pipeline.py` now calls `upsert_source`
  at the start of each source loop and passes `source_id` into
  `insert_item_if_new`, so the `sources` table is populated and items have
  non-null `source_id` after fetch.
- **`is_saved` orphan column removed** from schema and dataclass; the column
  was a remnant of a removed Save-to-Obsidian feature.

### Stack
- Python 3.11+ (uv-managed), FastAPI + HTMX + Jinja2, SQLite WAL.
- Claude CLI subprocess (no paid API).
- feedparser, httpx, rapidfuzz, bleach, filelock, pydantic v2.
- pytest test suite, Windows Task Scheduler integration.
