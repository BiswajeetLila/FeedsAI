#!/usr/bin/env python
"""
Fetch all sources, dedup, rank.
Usage: python scripts/fetch.py [--source TITLE] [--dry-run] [--verbose]
"""
import argparse
import asyncio
import logging
import logging.handlers
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline import run_fetch_cycle


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(name)s %(levelname)s %(message)s"

    # Console handler
    logging.basicConfig(level=level, format=fmt)

    # Rotating file handler — rotates at midnight, keeps 30 days
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"fetch-{date.today().isoformat()}.log"

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=30
    )
    file_handler.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(file_handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and rank feeds")
    parser.add_argument("--source", help="Fetch only this source (by title)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't write to DB")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    report = asyncio.run(run_fetch_cycle(
        source_filter=args.source,
        dry_run=args.dry_run,
    ))
    if args.dry_run:
        print("[DRY RUN] Fetched but nothing written to DB")
    print(f"Fetch complete: {report.items_new} new, {report.items_ranked} ranked, {len(report.errors)} errors")
    if report.errors:
        for err in report.errors:
            print(f"  ERROR: {err}", file=sys.stderr)
    sys.exit(1 if report.errors else 0)


if __name__ == "__main__":
    main()
