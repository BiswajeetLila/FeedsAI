# FeedsAI Next Product Plan

This plan turns FeedsAI from a developer-run local app into a user-friendly personal feed dashboard. The theme is: make core workflows visible in the UI, keep the app local-first, and spend LLM calls only where they create clear value.

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

This order matters because source management and search are high-frequency basics. The why panel and learning dashboard then make the ranking system understandable and tunable.

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

- Add `/setup/sources` or extend `/setup`.
- Show existing sources grouped by type:
  - RSS,
  - Hacker News,
  - arXiv,
  - GitHub releases.
- Add forms for each supported source kind.
- Validate by reusing `app.config.load_sources`.
- Write `sources.yaml` atomically:
  - write to temp file,
  - validate,
  - replace original.
- Add "Fetch this source now" for a single-source test.

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
- Multiple browser tabs editing sources could overwrite each other. MVP can ignore this; later add updated-at checks.

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

## 4. "Why Am I Seeing This?" Panel

### User Outcome

Users can understand and trust each recommendation.

### MVP

Add a section in the item drawer:

- score and tier,
- topic,
- ranking rationale,
- reason chips,
- novelty label,
- low-signal flags,
- source quality score,
- related-item cluster size.

No new LLM call. Use existing ranking metadata plus deterministic signals.

### Later

- Show matched profile snippets if ranking prompt/output starts returning them.
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

- runs the existing profile proposal in preview mode,
- writes `profile.md.proposed`,
- shows a diff or plain proposed profile.

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

## Issue Breakdown

### Slice 1: Launcher Polish

- Improve terminal copy in `scripts/start_app.ps1`.
- Open `/setup` or `/` based on setup state.
- Update `USER_README.md` with desktop shortcut steps.
- Add smoke test for launcher helper logic if extracted into a Python-testable function.

### Slice 2: Source Management MVP

- Add source config writer service.
- Add source list/edit forms.
- Validate before writing.
- Add tests for YAML write/validate.

### Slice 3: Search MVP

- Add FTS migration.
- Add search query helper.
- Add `/search` route and header form.
- Add tests for search indexing and fallback.

### Slice 4: Why Panel

- Extend drawer context with explanation fields.
- Add source quality lookup per item.
- Add focused CSS for explanation rows.
- Add tests for explanation data shape.

### Slice 5: Learning Dashboard

- Extract learning analytics from `profile_update.py`.
- Add `/learning` route and template.
- Add preview action for profile proposal.
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
