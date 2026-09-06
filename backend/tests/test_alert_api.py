from fastapi.testclient import TestClient

from app.main import app


def test_alert_routes_are_registered():
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    assert "/api/v1/alerts/check" in paths
    assert "/api/v1/alerts/active" in paths
    assert "/api/v1/alerts/zones" in paths
