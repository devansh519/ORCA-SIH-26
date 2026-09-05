from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_rameswaram_demo_scenario_is_accepted_and_returns_typed_context():
    response = client.post(
        "/api/v1/experience/query",
        json={
            "user_id": "demo-fisherman-01",
            "language": "ta",
            "voice_input": True,
            "location": {
                "name": "Rameswaram",
                "latitude": 9.2886,
                "longitude": 79.3129,
            },
            "question": "Is it safe to fish tomorrow near Rameswaram?",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["status"] == "accepted"
    assert payload["scenario"] == "rameswaram_fishing_safety"
    assert payload["location"]["name"] == "Rameswaram"
    assert payload["request"]["language"] == "ta"
    assert payload["request"]["question"] == "Is it safe to fish tomorrow near Rameswaram?"
    assert payload["orchestration"]["entrypoint"] == "experience_api"
    assert payload["orchestration"]["next_stage"] == "context_and_intent"
    assert payload["golden_schema"]["source"] == "experience_api"
    assert payload["golden_schema"]["location"]["lat"] == 9.2886
    assert payload["golden_schema"]["location"]["lon"] == 79.3129


def test_healthcheck_is_available():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
