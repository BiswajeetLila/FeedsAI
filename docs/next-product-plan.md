# FeedsAI Next Product Plan

This plan turns FeedsAI from a developer-run local app into a user-friendly personal feed dashboard. The theme is: make core workflows visible in the UI, keep the app local-first, and spend LLM calls only where they create clear value.

Implementation status as of 2026-05-31: the MVP slices below are implemented behind tests, including single-source fetch, source health, status visibility, and packaging-readiness scaffolding. Later learning/AI/reading-workflow sections remain future work.

## Guiding Decisions

- Keep `FeedsAI.bat` as the default user launch path on Windows.
- Keep the server visible in a terminal for now so users can stop it by closing the window and see basic failures.
- Treat `profile.md` and `sources.yaml` as user-owned local config, but stop requiring manual edits for common changes.
- Prefer deterministic local features for speed: source management, search, why panels, and learning analytics should not need LLM calls.
- Use LLM only for ranking, profile-update proposals, and explicit `/ask` questions.

## Recommended Build Order

1. Polish one-click launch.
2. Add source management UI.
3. Add local search.
4. Add "Why am I seeing this?" panel.
5. Add learning dashboard.
6. Add Windows packaging readiness.

This order matters because source management and search are high-frequency basics. The why panel and learning dashboard then make the ranking system understandable and tunable.

## Self-Review Notes

- `/sources` already exists as the source-quality page. Source management should use `/settings/sources` or `/setup/sources`, not replace `/sources`.
- "Matched interests" belongs in the first version of the why panel, not later. Start with deterministic matching against `profile.md` bullets; only extend ranking output later if needed.
- Profile-update preview can take a long time because it calls the LLM. The learning dashboard should start this as a background job or keep it as a CLI action until there is a proper progress/result state.
- Source edits must use a stable source key, not only title. Titles can collide or be blank.
- Search should have a `LIKE` fallback because some SQLite builds may not support FTS5.

## 1. One-Click App Polish

### User Outcome

A first-time user can double-click one file, get the app in a browser, and understand whether it is running.

### MVP

- Keep `FeedsAI.bat` as the primary entry point.
- Improve `scripts/start_app.ps1` messages:
  - checking Python,
  - checking dependencies,
  - starting server,
  - opening browser,
  - "close this window to stop FeedsAI".
- Add a startup landing path:
  - if setup is missing, open `/setup`,
  - otherwise open `/`.
- Add `/status` link in terminal output.
- Add user docs for creating a desktop shortcut to `FeedsAI.bat`.
- Keep launch idempotent: if the server is already running, open the browser and do not start a second server.

### Later

- Add `scripts/create_shortcut.ps1` to create a desktop shortcut automatically.
- Add a tray app or packaged executable only after the app behavior stabilizes.

### Risks

- Hidden background servers confuse users. Avoid background-only launch until there is a proper stop/restart UI.
- Auto-installing dependencies can fail on locked-down machines. The launcher should fail with a readable message.

## 2. Source Management UI

### User Outcome

Users can add, disable, remove, and test feeds without editing `sources.yaml`.

### MVP

- Add `/settings/sources` for ongoing source edits.
- Keep `/setup` focused on first-run onboarding.
- Keep `/sources` as the read-only source-quality page.
- Show existing sources grouped by type:
  - RSS,
  - Hacker News,
  - arXiv,
  - GitHub releases.
- Add forms for each supported source kind.
- Validate by reusing `app.config.load_sources`.
- Identify existing sources by a stable source key:
  - RSS: `rss:<url>`,
  - Hacker News: `hn:<filter>`,
  - arXiv: `arxiv:<query>`,
  - GitHub releases: `github:<owner/repo>`.
- Write `sources.yaml` atomically:
  - write to temp file,
  - validate,
  - keep a `.bak` backup,
  - replace original.
- Add optional `enabled: true` support to source models and make the pipeline skip disabled sources.
- Add "Fetch this source now" for a single-source test.
- Show source health:
  - last attempted,
  - last success,
  - last error,
  - items fetched,
  - items added.

### Data Model Choice

Keep `sources.yaml` as source of truth for now. Do not move source config into SQLite yet. The YAML file is portable, readable, and already part of the current system.

### Later

- Add enable/disable flags if the source schema supports it.
- Add source health:
  - last fetch status,
  - last error,
  - items fetched,
  - average score.

### Risks

- PyYAML will not preserve comments. That is acceptable if the app owns the generated `sources.yaml`.
- Multiple browser tabs editing sources could overwrite each other. Add a simple file hash or modified-time check before saving.

## 3. Local Search

### User Outcome

Users can instantly find articles by keyword, topic, source, or ranking rationale.

### MVP

- Add SQLite FTS5 table for:
  - title,
  - excerpt,
  - rank rationale,
  - source title,
  - topic.
- Add migration and rebuild helper.
- Update FTS on item insert/rank update.
- Add `/search?q=...` route.
- Add search box in the main header.
- Preserve digest filters in search where useful:
  - topic,
  - saved only,
  - read/unread.
- Rank results by:
  - FTS match,
  - item score,
  - recency.

### Later

- Add filters: topic, source, saved only, read/unread.
- Add search suggestions based on topics and source names.
- Add "search within saved".

### Risks

- Some SQLite builds may lack FTS5. Add a fallback `LIKE` search if FTS5 table creation fails.
- Search should not expose full text if the app does not store full article text.
- Search indexing must update after ranking, because `rank_rationale` arrives after item insert.

## 4. "Why Am I Seeing This?" Panel

### User Outcome

Users can understand and trust each recommendation.

### MVP

Add a section in the item drawer:

- score and tier,
- topic,
- matched interests from `profile.md`,
- ranking rationale,
- reason chips,
- novelty label,
- low-signal flags,
- source quality score,
- related-item cluster size.

No new LLM call. Use existing ranking metadata plus deterministic signals. Matched interests should come from a cheap profile matcher that parses profile bullets/headings and checks them against title, excerpt, topic, and rank rationale.

### Later

- Extend ranking output with explicit matched profile snippets if deterministic matching is too weak.
- Add feedback buttons:
  - "more like this",
  - "less like this",
  - "wrong topic",
  - "bad source".

### Risks

- A vague rationale hurts trust. If rationales are weak, improve `prompts/rank_v1.txt` before adding more UI.
- Do not over-explain every item in the main list; keep details inside the drawer.

## 5. Learning Dashboard

### User Outcome

Users can see what FeedsAI thinks they like before allowing profile changes.

### MVP

Add `/learning` with:

- top topics by engagement,
- top sources by engagement,
- most-liked items,
- most-saved items,
- items skipped or filtered as low-signal,
- "profile update readiness" count showing signals collected vs threshold.

Add a preview button:

- starts a background profile proposal job or points users to the CLI preview,
- writes `profile.md.proposed`,
- shows progress, completion, and a diff or plain proposed profile.

### Later

- Add editable preference cards:
  - boost topic,
  - mute topic,
  - boost source,
  - mute source.
- Add confidence levels based on number and strength of signals.
- Add history of profile changes.

### Risks

- Users may overfit the profile if every small click is treated as preference. The dashboard should separate weak signals from strong signals.
- Profile updates should remain preview-first. Never silently rewrite `profile.md`.
- Do not block a normal page request waiting for a long LLM profile proposal.

## 6. Windows Packaging Readiness

### User Outcome

A normal Windows user can open FeedsAI from one app icon without knowing Python, PowerShell, or batch files.

### MVP

- Keep `FeedsAI.bat` and `scripts/start_app.ps1` as the developer launch path.
- Add a Python desktop launcher entrypoint for `FeedsAI.exe`.
- Choose an available localhost port, start the server, open the browser, and stop cleanly.
- In packaged mode, store user data under `%LOCALAPPDATA%\FeedsAI`.
- In dev mode, keep repo-local files so the app remains easy to edit.
- Add a PyInstaller onedir build script before attempting a full installer.

### Later

- Add an installer with Start Menu and Desktop icons.
- Add a tray app only after the server lifecycle is reliable.
- Consider onefile packaging after onedir startup and asset handling are proven.

### Risks

- Packaged apps fail if mutable data is stored beside the executable. Keep profile, sources, DB, logs, and fetch state in the user data dir.
- Hidden background servers confuse users. Keep visible status and a clear shutdown path.

## Issue Breakdown

### Slice 1: Launcher Polish

- Improve terminal copy in `scripts/start_app.ps1`.
- Open `/setup` or `/` based on setup state.
- Update `USER_README.md` with desktop shortcut steps.
- Add smoke test for launcher helper logic if extracted into a Python-testable function.

### Slice 2: Source Management MVP

- Add source config writer service.
- Add source list/edit forms.
- Add stable source keys and optional `enabled` field.
- Validate before writing.
- Add tests for YAML write/validate, backup creation, and disabled-source skipping.

### Slice 3: Search MVP

- Add FTS migration.
- Add search query helper.
- Add `/search` route and header form.
- Add tests for search indexing and fallback.

### Slice 4: Why Panel

- Extend drawer context with explanation fields.
- Add deterministic profile-interest matcher.
- Add source quality lookup per item.
- Add focused CSS for explanation rows.
- Add tests for explanation data shape.

### Slice 5: Learning Dashboard

- Extract learning analytics from `profile_update.py`.
- Add `/learning` route and template.
- Add background-safe preview action for profile proposal.
- Add tests for analytics aggregation.

## Definition Of Done

- Full test suite passes.
- Main routes smoke tested:
  - `/`,
  - `/setup`,
  - `/sources`,
  - `/search`,
  - `/learning`,
  - `/status`.
- No new automatic LLM calls are added to page load or drawer open.
- `profile.md` and `sources.yaml` remain ignored user-local files.
