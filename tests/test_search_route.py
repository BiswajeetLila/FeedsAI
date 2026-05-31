from fastapi.testclient import TestClient

from app.main import app


def test_search_page_renders_query_form_and_results_shell():
    client = TestClient(app)

    response = client.get("/search?q=robotics")

    assert response.status_code == 200
    assert "Search" in response.text
    assert 'name="q"' in response.text
    assert "robotics" in response.text
