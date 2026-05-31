from fastapi.testclient import TestClient

from app.main import app


def test_learning_page_renders_dashboard_shell():
    client = TestClient(app)

    response = client.get("/learning")

    assert response.status_code == 200
    assert "Learning" in response.text
    assert "Profile update" in response.text
