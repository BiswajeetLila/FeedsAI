# Changelog

All notable changes to FeedsAI Starter.

## [0.2.0] - 2026-05-31

### Added
- First-run browser setup for interests, avoid-list, starter feeds, and first fetch.
- In-app source management at `/settings/sources`.
- Per-source fetch action and persisted source health.
- Local search with SQLite FTS5 and LIKE fallback.
- Recommendation explanation panel with deterministic profile-interest matching.
- Learning dashboard for engagement analytics and profile-update readiness.
- Status/log pages for server state, fetch progress, LLM availability, and logs.
- Windows packaging-readiness layer:
  - dev vs packaged runtime paths,
  - packaged launcher entrypoint,
  - PyInstaller onedir build script.

### Changed
- `FeedsAI.bat` / `scripts/start_app.ps1` is now the main dev launch path.
- Mutable files stay repo-local in dev mode and move to `%LOCALAPPDATA%\FeedsAI`
  in packaged mode.
- Source config supports `enabled: true/false`.
- Docs now point normal users to the browser UI instead of manual YAML edits.

### Verified
- Full suite: `116 passed, 1 warning`.

## [0.1.0] - 2026-05-29

First public release of FeedsAI Starter: a depersonalized fork-and-go template
derived from a personal FeedsAI deployment.

### Added
- First-run wizard (`scripts/init.py`): checks `claude` CLI, copies example
  config files, runs dependency sync, and runs `scripts/healthcheck.py`.
- Generic profile template (`profile.md.example`).
- Minimal default sources (`sources.yaml.example`).
- MIT license.

### Fixed
- `sources` table population during fetch.
- Removed stale `is_saved` schema/dataclass mismatch from the original release.

### Stack
- Python 3.11+, FastAPI, HTMX, Jinja2, SQLite WAL.
- Claude CLI subprocess ranking.
- feedparser, httpx, rapidfuzz, bleach, filelock, pydantic v2.
- pytest test suite and Windows Task Scheduler integration.
