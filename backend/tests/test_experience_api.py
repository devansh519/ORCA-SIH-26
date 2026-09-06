from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_healthcheck_is_available():
    response = client.get("/api/v1/health")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_query_accepts_place_name_without_coordinates():
    response = client.post(
        "/api/v1/experience/query",
        json={
            "user_id": "demo-fisherman",
            "language": "en",
            "voice_input": False,
            "location": {
                "name": "Rameswaram",
            },
            "question": "Is it safe to fish tomorrow?",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["status"] == "completed"
    assert payload["location"]["name"]
    assert payload["location"]["latitude"] is not None
    assert payload["location"]["longitude"] is not None
    assert payload["location_resolution"]["source"] == "Open-Meteo Geocoding API"
    assert payload["scenario"] == "fishing_safety"
    assert "weather" in payload
    assert "marine" in payload
    assert "geospatial" in payload
    assert "decision_engine" in payload
    assert "safety_score" in payload
    assert "yield_score" in payload
    assert payload["orchestration"]["selected_tools"] == [
        "weather",
        "marine",
        "geospatial",
    ]
