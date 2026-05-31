"""
Runtime paths for dev and packaged FeedsAI.

Dev mode keeps user-owned files in the repo for easy iteration. Packaged mode
stores mutable files under LOCALAPPDATA so the installed app directory can stay
read-only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "FeedsAI"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False)) or os.environ.get("FEEDSAI_PACKAGED") == "1"


def package_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return project_root()


def user_root() -> Path:
    override = os.environ.get("FEEDSAI_USER_ROOT")
    if override:
        return Path(override)
    if is_packaged():
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / APP_NAME
    return project_root()


def data_dir() -> Path:
    return user_root() / "data"


def logs_dir() -> Path:
    return data_dir()


def default_db_path() -> Path:
    return data_dir() / "feeds.db"


def profile_path() -> Path:
    return user_root() / "profile.md"


def sources_path() -> Path:
    return user_root() / "sources.yaml"


def fetch_lock_path() -> Path:
    return data_dir() / "fetch.lock"


def last_fetch_path() -> Path:
    return data_dir() / "last_fetch.txt"


def resolve_user_path(path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return user_root() / resolved


def resource_path(*parts: str) -> Path:
    return package_root().joinpath(*parts)
