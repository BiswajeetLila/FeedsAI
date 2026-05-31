from pathlib import Path

import pytest

from app.source_config import (
    add_source_entry,
    list_source_entries,
    remove_source_entry,
    set_source_enabled,
    source_key,
    source_label,
)
from app.config import RSSSource


def _write_sources(path: Path) -> None:
    path.write_text(
        """
schema_version: 1
sources:
  - kind: rss
    url: https://example.com/feed.xml
    title: Example
  - kind: github_releases
    repo: owner/repo
    enabled: false
""".strip(),
        encoding="utf-8",
    )


def test_source_key_is_stable_per_source_kind():
    assert source_key({"kind": "rss", "url": "https://example.com/feed.xml"}) == "rss:https://example.com/feed.xml"
    assert source_key({"kind": "hn", "filter": "front_page"}) == "hn:front_page"
    assert source_key({"kind": "arxiv", "query": "cat:cs.AI"}) == "arxiv:cat:cs.AI"
    assert source_key({"kind": "github_releases", "repo": "owner/repo"}) == "github:owner/repo"


def test_source_key_and_label_accept_typed_sources():
    source = RSSSource(kind="rss", url="https://example.com/feed.xml", title="Example")

    assert source_key(source) == "rss:https://example.com/feed.xml"
    assert source_label(source) == "Example"


def test_list_source_entries_defaults_enabled_true(tmp_path):
    path = tmp_path / "sources.yaml"
    _write_sources(path)

    entries = list_source_entries(path)

    assert entries[0]["key"] == "rss:https://example.com/feed.xml"
    assert entries[0]["enabled"] is True
    assert entries[1]["key"] == "github:owner/repo"
    assert entries[1]["enabled"] is False


def test_add_toggle_and_remove_source_entry_write_backup(tmp_path):
    path = tmp_path / "sources.yaml"
    _write_sources(path)

    add_source_entry(path, {"kind": "arxiv", "query": "cat:cs.RO", "title": "Robotics"})
    set_source_enabled(path, "rss:https://example.com/feed.xml", False)
    remove_source_entry(path, "github:owner/repo")

    entries = list_source_entries(path)
    keys = [entry["key"] for entry in entries]
    assert keys == ["rss:https://example.com/feed.xml", "arxiv:cat:cs.RO"]
    assert entries[0]["enabled"] is False
    assert (tmp_path / "sources.yaml.bak").exists()


def test_add_source_entry_rejects_duplicates(tmp_path):
    path = tmp_path / "sources.yaml"
    _write_sources(path)

    with pytest.raises(ValueError, match="already exists"):
        add_source_entry(path, {"kind": "rss", "url": "https://example.com/feed.xml"})
