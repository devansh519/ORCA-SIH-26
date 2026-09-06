from app.decision.rules import (
    score_safety_from_weather,
    score_yield_from_marine,
)


def test_safety_unavailable_does_not_become_zero():
    result = score_safety_from_weather(
        {
            "status": "unavailable",
            "variables": {},
            "confidence": 0.0,
        }
    )

    assert result["score"] is None
    assert result["level"] == "INSUFFICIENT_DATA"
    assert result["status"] == "insufficient_data"


def test_safety_uses_real_weather_fields():
    result = score_safety_from_weather(
        {
            "status": "available",
            "confidence": 1.0,
            "variables": {
                "wind_speed_ms": 4.0,
                "wave_height_m": 0.8,
            },
            "alerts": [],
        }
    )

    assert result["score"] == 100.0
    assert result["level"] == "GO"
    assert result["status"] == "available"


def test_red_warning_caps_safety():
    result = score_safety_from_weather(
        {
            "status": "available",
            "confidence": 1.0,
            "variables": {
                "wind_speed_ms": 4.0,
            },
            "alerts": [
                {"severity": "RED"},
            ],
        }
    )

    assert result["score"] <= 30
    assert result["level"] == "AVOID"


def test_yield_requires_live_marine_signal():
    result = score_yield_from_marine(
        {
            "status": "unavailable",
            "variables": {},
            "confidence": 0.0,
        }
    )

    assert result["score"] is None
    assert result["level"] == "INSUFFICIENT_DATA"


def test_yield_uses_chlorophyll_and_sst_separately_from_safety():
    result = score_yield_from_marine(
        {
            "status": "available",
            "confidence": 1.0,
            "variables": {
                "chlorophyll_mg_m3": 1.2,
                "sst_c": 27.0,
            },
        }
    )

    assert result["score"] == 90.0
    assert result["level"] == "GO"
    assert result["status"] == "available"
