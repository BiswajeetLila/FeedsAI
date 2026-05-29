#!/usr/bin/env python
"""
Smoke test: DB, sources.yaml, claude CLI, first feed.
Usage: python scripts/healthcheck.py
Exits 0 if all checks pass, 1 if any fail.
"""
import sys
import shutil
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

CHECKS = []


def check(name):
    """Decorator to register a check function."""
    def decorator(fn):
        CHECKS.append((name, fn))
        return fn
    return decorator


@check("sources.yaml loads")
def check_sources():
    from app.config import load_sources
    s = load_sources()
    return f"{len(s.sources)} sources loaded"


@check("DB schema initializes")
def check_db():
    from app.db import init_schema
    db_path = Path(__file__).parent.parent / "data" / "feeds.db"
    init_schema(db_path)
    return f"DB at {db_path}"


@check("claude CLI on PATH")
def check_claude():
    path = shutil.which("claude")
    if not path:
        return None  # None = warning (not fatal)
    return f"claude at {path}"


@check("gemini CLI on PATH")
def check_gemini():
    path = shutil.which("gemini")
    if not path:
        return None  # warning only
    return f"gemini at {path}"


@check("First RSS feed reachable")
def check_first_feed():
    from app.config import load_sources, RSSSource
    from app.ingest.rss import fetch_rss
    sources = load_sources()
    rss = next((s for s in sources.sources if isinstance(s, RSSSource)), None)
    if not rss:
        return "No RSS sources configured"
    items = fetch_rss(str(rss.url), rss.title)
    if not items:
        return None  # warning
    return f"Fetched {len(items)} items from {rss.title or rss.url}"


def run_checks():
    passed = 0
    warnings = 0
    failed = 0
    for name, fn in CHECKS:
        try:
            result = fn()
            if result is None:
                print(f"  [!] {name}: WARNING (not fatal)")
                warnings += 1
            else:
                print(f"  [+] {name}: {result}")
                passed += 1
        except Exception as e:
            print(f"  [X] {name}: FAILED -- {e}")
            failed += 1
    print(f"\n{passed} passed, {warnings} warnings, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run_checks()
    sys.exit(0 if ok else 1)
