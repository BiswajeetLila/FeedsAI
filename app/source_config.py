"""
Read and write user-owned sources.yaml safely.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from app.config import load_sources
from app.paths import sources_path

DEFAULT_SOURCES_PATH = sources_path()


def _source_value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _load_raw(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists():
        return {"schema_version": 1, "sources": []}
    data = yaml.load(resolved.read_text(encoding="utf-8"), Loader=yaml.SafeLoader) or {}
    sources = data.get("sources") or []
    return {"schema_version": data.get("schema_version", 1), "sources": sources}


def source_key(source: Any) -> str:
    kind = _source_value(source, "kind")
    if kind == "rss":
        return f"rss:{_source_value(source, 'url', '')}"
    if kind == "hn":
        return f"hn:{_source_value(source, 'filter', 'front_page')}"
    if kind == "arxiv":
        return f"arxiv:{_source_value(source, 'query', '')}"
    if kind == "github_releases":
        return f"github:{_source_value(source, 'repo', '')}"
    return f"{kind}:unknown"


def source_label(source: Any) -> str:
    title = _source_value(source, "title")
    if title:
        return str(title)
    kind = _source_value(source, "kind")
    if kind == "rss":
        return str(_source_value(source, "url", "RSS feed"))
    if kind == "hn":
        return "Hacker News"
    if kind == "arxiv":
        return f"arXiv {_source_value(source, 'query', '')}"
    if kind == "github_releases":
        return str(_source_value(source, "repo", "GitHub releases"))
    return str(kind or "Source")


def list_source_entries(path: str | Path = DEFAULT_SOURCES_PATH) -> list[dict[str, Any]]:
    data = _load_raw(path)
    entries: list[dict[str, Any]] = []
    for source in data["sources"]:
        entry = dict(source)
        entry["enabled"] = bool(entry.get("enabled", True))
        entry["key"] = source_key(entry)
        entries.append(entry)
    return entries


def _write_sources(path: Path, sources: list[dict[str, Any]]) -> None:
    payload = {"schema_version": 1, "sources": sources}
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    load_sources(tmp_path)

    if path.exists():
        shutil.copy2(path, Path(str(path) + ".bak"))
    os.replace(tmp_path, path)


def add_source_entry(path: str | Path, source: dict[str, Any]) -> None:
    resolved = Path(path)
    data = _load_raw(resolved)
    source = dict(source)
    source.setdefault("enabled", True)
    key = source_key(source)
    if any(source_key(existing) == key for existing in data["sources"]):
        raise ValueError(f"source already exists: {key}")
    _write_sources(resolved, [*data["sources"], source])


def set_source_enabled(path: str | Path, key: str, enabled: bool) -> None:
    resolved = Path(path)
    data = _load_raw(resolved)
    changed = False
    for source in data["sources"]:
        if source_key(source) == key:
            source["enabled"] = enabled
            changed = True
            break
    if not changed:
        raise ValueError(f"source not found: {key}")
    _write_sources(resolved, data["sources"])


def remove_source_entry(path: str | Path, key: str) -> None:
    resolved = Path(path)
    data = _load_raw(resolved)
    sources = [source for source in data["sources"] if source_key(source) != key]
    if len(sources) == len(data["sources"]):
        raise ValueError(f"source not found: {key}")
    _write_sources(resolved, sources)
