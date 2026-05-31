from fastapi.testclient import TestClient

from app.main import app


def test_status_page_shows_running_state_and_runtime_paths(monkeypatch):
    monkeypatch.setattr("app.routes.status._get_scheduled_tasks", lambda: [])
    client = TestClient(app)

    response = client.get("/status")

    assert response.status_code == 200
    assert "System Status" in response.text
    assert "User data" in response.text
    assert "Claude CLI" in response.text


def test_logs_page_renders_log_tail():
    client = TestClient(app)

    response = client.get("/logs")

    assert response.status_code == 200
    assert "Logs" in response.text
