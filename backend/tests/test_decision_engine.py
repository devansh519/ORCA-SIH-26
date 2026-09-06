from app.decision.engine import DecisionEngine


def test_engine_keeps_safety_and_yield_separate():
    engine = DecisionEngine()

    result = engine.evaluate(
        weather={
            "status": "available",
            "confidence": 1.0,
            "variables": {
                "wind_speed_ms": 7.0,
                "wave_height_m": 1.5,
            },
            "alerts": [],
        },
        marine={
            "status": "available",
            "confidence": 1.0,
            "variables": {
                "chlorophyll_mg_m3": 1.2,
                "sst_c": 27.0,
            },
        },
        geospatial={
            "status": "available",
            "inside": False,
            "distance_km": 4.0,
        },
    )

    assert result.safety.score is not None
    assert result.yield_assessment.score is not None
    assert result.safety.score != result.yield_assessment.score
    assert result.recommendation == result.safety.level
    assert "weather" in result.evidence_used
    assert "marine" in result.evidence_used


def test_engine_refuses_safety_recommendation_without_weather():
    engine = DecisionEngine()

    result = engine.evaluate(
        weather={
            "status": "unavailable",
            "variables": {},
            "confidence": 0.0,
        },
        marine={
            "status": "available",
            "confidence": 1.0,
            "variables": {
                "chlorophyll_mg_m3": 1.2,
            },
        },
        geospatial={
            "status": "available",
            "inside": False,
            "distance_km": 0.49,
        },
    )

    assert result.safety.score is None
    assert result.safety.level == "INSUFFICIENT_DATA"
    assert result.yield_assessment.score is not None
    assert result.recommendation == "INSUFFICIENT_DATA"
    assert result.status == "insufficient_data"


def test_engine_serializes_for_api():
    engine = DecisionEngine()

    result = engine.evaluate(
        weather={
            "status": "available",
            "confidence": 0.9,
            "variables": {
                "wind_speed_ms": 4.0,
            },
            "alerts": [],
        },
        marine={
            "status": "unavailable",
            "variables": {},
            "confidence": 0.0,
        },
        geospatial={
            "status": "available",
            "inside": False,
            "distance_km": 4.0,
        },
    )

    payload = result.model_dump(mode="json")

    assert payload["safety"]["score"] == 100.0
    assert payload["yield_assessment"]["score"] is None
    assert payload["recommendation"] == "GO"
