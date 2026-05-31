import sys

from app import paths


def test_dev_paths_default_to_project_root(monkeypatch):
    monkeypatch.delenv("FEEDSAI_PACKAGED", raising=False)
    monkeypatch.delenv("FEEDSAI_USER_ROOT", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert paths.user_root() == paths.project_root()
    assert paths.default_db_path() == paths.project_root() / "data" / "feeds.db"
    assert paths.sources_path() == paths.project_root() / "sources.yaml"


def test_packaged_paths_use_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("FEEDSAI_PACKAGED", "1")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("FEEDSAI_USER_ROOT", raising=False)

    assert paths.user_root() == tmp_path / "FeedsAI"
    assert paths.profile_path() == tmp_path / "FeedsAI" / "profile.md"
    assert paths.default_db_path() == tmp_path / "FeedsAI" / "data" / "feeds.db"


def test_user_root_override_wins(monkeypatch, tmp_path):
    override = tmp_path / "custom"
    monkeypatch.setenv("FEEDSAI_PACKAGED", "1")
    monkeypatch.setenv("FEEDSAI_USER_ROOT", str(override))

    assert paths.user_root() == override
    assert paths.resolve_user_path("sources.yaml") == override / "sources.yaml"
