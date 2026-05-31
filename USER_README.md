# FeedsAI User Guide

FeedsAI is a private, local feed dashboard. It reads news and technical sources, ranks items against your interests, and helps you build a daily reading queue.

Upcoming product plan: [docs/next-product-plan.md](docs/next-product-plan.md).

## First Start

1. Double-click `FeedsAI.bat`.
2. Your browser opens at `http://127.0.0.1:8000`.
3. If this is your first run, the setup page opens.
4. Add your interests, topics to avoid, and a few feeds you want to follow.
5. Leave **Fetch after saving** checked and save setup.

The first fetch can take a few minutes because new items are ranked for you.

## Daily Use

- Open `FeedsAI.bat`.
- Read the main digest.
- Click an item to expand it.
- Use **Read original** when something is worth opening.
- Use **Like** to teach the app what you want more of.
- Use **Save** to build a reading queue.
- Use the header search box to find older items by title, excerpt, topic, source, or ranking rationale.
- Open `/status` whenever you want to confirm the server is running, see fetch progress, or trigger a fetch.

## Digest Modes

- **Ranked**: best personal matches first.
- **Balanced**: mixes topics and sources so one feed does not dominate.
- **Fresh**: newest useful items first.

Use topic tabs to focus the dashboard. Use **Show low-signal** only when you want to inspect filtered-out items.

## Useful Pages

- `/` - your feed digest.
- `/ask` - ask a question about recent feed items.
- `/search` - search saved and recent feed items.
- `/learning` - see what the app thinks you like.
- `/sources` - see which sources are producing useful items.
- `/settings/sources` - add, pause, remove, or test sources.
- `/status` - check if the app is running and whether fetches are working.
- `/logs` - view recent app logs.
- `/setup` - update your interests and sources.

## Managing Sources

Open `/settings/sources` to add, pause, remove, or test one feed with **Fetch now**. Use `/sources` when you want to inspect which sources are producing useful items.

Supported source types:

- RSS or Atom feed URL,
- Hacker News front page,
- arXiv query,
- GitHub releases repo in `owner/repo` format.

## How It Learns

FeedsAI learns from:

- items you open,
- original links you visit,
- items you like,
- time spent reading,
- saved items.

It does not use AI to summarize every article. AI is used for ranking, profile learning, and questions you ask on `/ask`.

## Stopping The App

Close the terminal window that opened with `FeedsAI.bat`.

Your data stays on your machine in the `data/` folder. Your personal `profile.md` and `sources.yaml` are not meant to be committed to Git.

## Desktop Shortcut

On Windows, right-click `FeedsAI.bat`, choose **Show more options**, then **Send to > Desktop (create shortcut)**. Use that shortcut as the one-click launcher.

## Packaged App Preview

Developers can build a Windows app folder with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows_app.ps1
```

The packaged launcher is `dist\FeedsAI\FeedsAI.exe`. In packaged mode, user data is stored under `%LOCALAPPDATA%\FeedsAI`; in dev mode, the repo-local files stay editable.
