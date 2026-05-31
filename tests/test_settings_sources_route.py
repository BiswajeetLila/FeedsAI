from fastapi.testclient import TestClient

from app.main import app


def test_settings_sources_lists_and_adds_sources(tmp_path, monkeypatch):
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        """
schema_version: 1
sources:
  - kind: rss
    url: https://example.com/feed.xml
    title: Example
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.source_config.DEFAULT_SOURCES_PATH", sources_path, raising=False)

    client = TestClient(app)

    page = client.get("/settings/sources")
    assert page.status_code == 200
    assert "Example" in page.text
    assert "https://example.com/feed.xml" in page.text

    response = client.post(
        "/settings/sources/add",
        data={
            "kind": "arxiv",
            "value": "cat:cs.RO",
            "title": "Robotics Papers",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    updated = client.get("/settings/sources")
    assert "Robotics Papers" in updated.text
    assert "cat:cs.RO" in updated.text


def test_settings_sources_fetch_redirects_to_status(tmp_path, monkeypatch):
    sources_path = tmp_path / "sources.yaml"
    sources_path.write_text(
        """
schema_version: 1
sources:
  - kind: rss
    url: https://example.com/feed.xml
    title: Example
""".strip(),
        encoding="utf-8",
    )
    scheduled = []
    monkeypatch.setattr("app.source_config.DEFAULT_SOURCES_PATH", sources_path, raising=False)
    monkeypatch.setattr("app.routes.settings._schedule_source_fetch", scheduled.append)

    client = TestClient(app)

    page = client.get("/settings/sources")
    assert "Fetch now" in page.text

    response = client.post(
        "/settings/sources/fetch",
        data={"key": "rss:https://example.com/feed.xml"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/status"
    assert scheduled == ["rss:https://example.com/feed.xml"]
