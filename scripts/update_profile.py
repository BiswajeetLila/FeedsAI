#!/usr/bin/env python
"""
Propose a weekly profile.md update based on reading activity.
Usage: python scripts/update_profile.py [--preview] [--days N]
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.profile_update import propose_profile_update


def main() -> None:
    parser = argparse.ArgumentParser(description="Propose profile.md update")
    parser.add_argument("--preview", action="store_true", help="Show proposed diff only, don't prompt")
    parser.add_argument("--days", type=int, default=7, help="Days of activity to analyze (default: 7)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    success = asyncio.run(propose_profile_update(days=args.days, preview=args.preview))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
