from __future__ import annotations

from typing import Any


# These are transparent MVP scoring thresholds, not official IMD or fishing
# safety limits. They are deliberately isolated here so they can be replaced
# by authoritative hazard thresholds later without changing the engine.
WIND_SAFE_MAX_MS = 5.0
WIND_CAUTION_MAX_MS = 8.0
WIND_AVOID_MAX_MS = 12.0

WAVE_SAFE_MAX_M = 1.0
WAVE_CAUTION_MAX_M = 2.0
WAVE_AVOID_MAX_M = 3.0

BOUNDARY_CAUTION_DISTANCE_KM = 1.0


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _first_number(variables: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _number(variables.get(key))
        if value is not None:
            return value
    return None


def extract_wind_speed_ms(weather: dict[str, Any]) -> float | None:
    variables = weather.get("variables")
    if not isinstance(variables, dict):
        return None
    return _first_number(
        variables,
        (
            "wind_speed_ms",
            "wind_speed_m_s",
            "wind_ms",
            "wind_speed",
        ),
    )


def extract_wave_height_m(weather: dict[str, Any]) -> float | None:
    variables = weather.get("variables")
    if not isinstance(variables, dict):
        return None
    return _first_number(
        variables,
        (
            "wave_height_m",
            "significant_wave_height_m",
            "wave_height",
        ),
    )


def extract_chlorophyll_mg_m3(marine: dict[str, Any]) -> float | None:
    variables = marine.get("variables")
    if not isinstance(variables, dict):
        return None
    return _first_number(
        variables,
        (
            "chlorophyll_mg_m3",
            "chlorophyll_a_mg_m3",
            "chlorophyll",
        ),
    )


def extract_sst_c(marine: dict[str, Any]) -> float | None:
    variables = marine.get("variables")
    if not isinstance(variables, dict):
        return None
    return _first_number(
        variables,
        (
            "sst_c",
            "sea_surface_temperature_c",
            "sea_surface_temperature",
            "sst",
        ),
    )


def _severity_rank(value: Any) -> int:
    if not isinstance(value, str):
        return 0
    normalized = value.strip().lower()
    return {
        "red": 4,
        "extreme": 4,
        "severe": 4,
        "orange": 3,
        "high": 3,
        "yellow": 2,
        "moderate": 2,
        "green": 1,
        "low": 1,
        "none": 0,
    }.get(normalized, 0)


def extract_max_alert_severity(weather: dict[str, Any]) -> str | None:
    alerts = weather.get("alerts")
    if not isinstance(alerts, list) or not alerts:
        return None

    best_value: str | None = None
    best_rank = 0

    for alert in alerts:
        if isinstance(alert, dict):
            severity = alert.get("severity") or alert.get("level")
        else:
            severity = alert

        rank = _severity_rank(severity)
        if rank > best_rank:
            best_rank = rank
            best_value = str(severity)

    return best_value


def score_safety_from_weather(
    weather: dict[str, Any],
    geospatial: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate a transparent safety score from live weather/hazard evidence.

    A numeric score is returned only when at least one recognized live weather
    safety factor exists. Missing weather data never becomes a zero.
    """

    if weather.get("status") != "available":
        return {
            "score": None,
            "level": "INSUFFICIENT_DATA",
            "reasoning": ["Live weather/hazard data is unavailable."],
            "factors": {},
            "confidence": 0.0,
            "status": "insufficient_data",
        }

    variables = weather.get("variables")
    if not isinstance(variables, dict):
        variables = {}

    wind = extract_wind_speed_ms(weather)
    wave = extract_wave_height_m(weather)
    severity = extract_max_alert_severity(weather)

    recognized = any(
        value is not None
        for value in (wind, wave, severity)
    )

    if not recognized:
        return {
            "score": None,
            "level": "INSUFFICIENT_DATA",
            "reasoning": [
                "The weather provider is available but supplied no recognized "
                "wind, wave, or warning severity fields."
            ],
            "factors": {},
            "confidence": 0.0,
            "status": "insufficient_data",
        }

    score = 100.0
    reasoning: list[str] = []
    factors: dict[str, Any] = {}

    if wind is not None:
        factors["wind_speed_ms"] = wind
        if wind > WIND_AVOID_MAX_MS:
            score -= 55
            reasoning.append(
                f"Wind speed {wind:.1f} m/s is above the MVP avoid threshold."
            )
        elif wind > WIND_CAUTION_MAX_MS:
            score -= 35
            reasoning.append(
                f"Wind speed {wind:.1f} m/s is in the MVP high-risk range."
            )
        elif wind > WIND_SAFE_MAX_MS:
            score -= 18
            reasoning.append(
                f"Wind speed {wind:.1f} m/s is in the MVP caution range."
            )
        else:
            reasoning.append(
                f"Wind speed {wind:.1f} m/s is within the MVP lower-risk range."
            )

    if wave is not None:
        factors["wave_height_m"] = wave
        if wave > WAVE_AVOID_MAX_M:
            score -= 45
            reasoning.append(
                f"Wave height {wave:.1f} m is above the MVP avoid threshold."
            )
        elif wave > WAVE_CAUTION_MAX_M:
            score -= 30
            reasoning.append(
                f"Wave height {wave:.1f} m is in the MVP high-risk range."
            )
        elif wave > WAVE_SAFE_MAX_M:
            score -= 15
            reasoning.append(
                f"Wave height {wave:.1f} m is in the MVP caution range."
            )
        else:
            reasoning.append(
                f"Wave height {wave:.1f} m is within the MVP lower-risk range."
            )

    if severity is not None:
        factors["max_alert_severity"] = severity
        rank = _severity_rank(severity)
        if rank >= 4:
            score = min(score, 20)
            reasoning.append(
                f"Weather warning severity is {severity}; the engine applies "
                "an avoid-level cap."
            )
        elif rank == 3:
            score = min(score, 45)
            reasoning.append(
                f"Weather warning severity is {severity}; the engine applies "
                "a high-risk cap."
            )
        elif rank == 2:
            score = min(score, 65)
            reasoning.append(
                f"Weather warning severity is {severity}; the engine applies "
                "a caution cap."
            )

    if geospatial and geospatial.get("status") == "available":
        distance = _number(geospatial.get("distance_km"))
        if distance is not None and distance <= BOUNDARY_CAUTION_DISTANCE_KM:
            factors["eez_boundary_distance_km"] = distance
            score = min(score, 60)
            reasoning.append(
                f"The location is {distance:.2f} km from the EEZ boundary; "
                "the engine flags boundary proximity for caution."
            )

        if geospatial.get("intersects_eez") is True:
            factors["route_intersects_eez"] = True
            score = min(score, 40)
            reasoning.append(
                "The supplied route intersects EEZ geometry; the engine "
                "flags this as a high-risk operational condition."
            )

    score = max(0.0, min(100.0, score))

    if score <= 30:
        level = "AVOID"
    elif score <= 60:
        level = "CAUTION"
    else:
        level = "GO"

    return {
        "score": score,
        "level": level,
        "reasoning": reasoning,
        "factors": factors,
        "confidence": _confidence_from_evidence(
            weather=weather,
            recognized_count=sum(
                value is not None for value in (wind, wave, severity)
            ),
            max_factors=3,
        ),
        "status": "available",
    }


def score_yield_from_marine(
    marine: dict[str, Any],
) -> dict[str, Any]:
    """Calculate a conservative MVP yield score from recognized marine data.

    This is intentionally a narrow signal-based score, not a fish-abundance
    prediction model. A numeric score requires live marine variables.
    """

    if marine.get("status") != "available":
        return {
            "score": None,
            "level": "INSUFFICIENT_DATA",
            "reasoning": ["Live marine data is unavailable."],
            "factors": {},
            "confidence": 0.0,
            "status": "insufficient_data",
        }

    chlorophyll = extract_chlorophyll_mg_m3(marine)
    sst = extract_sst_c(marine)

    if chlorophyll is None and sst is None:
        return {
            "score": None,
            "level": "INSUFFICIENT_DATA",
            "reasoning": [
                "The marine provider is available but supplied no recognized "
                "chlorophyll or SST fields."
            ],
            "factors": {},
            "confidence": 0.0,
            "status": "insufficient_data",
        }

    score = 50.0
    reasoning: list[str] = []
    factors: dict[str, Any] = {}

    # Chlorophyll contributes the strongest MVP signal because it is a
    # productivity proxy. These are intentionally broad demo bands, not a
    # fish-location prediction model.
    if chlorophyll is not None:
        factors["chlorophyll_mg_m3"] = chlorophyll
        if chlorophyll >= 1.0:
            score += 30
            reasoning.append(
                f"Chlorophyll {chlorophyll:.2f} mg/m³ indicates stronger "
                "surface productivity in this MVP rule set."
            )
        elif chlorophyll >= 0.3:
            score += 15
            reasoning.append(
                f"Chlorophyll {chlorophyll:.2f} mg/m³ indicates moderate "
                "surface productivity in this MVP rule set."
            )
        else:
            score -= 10
            reasoning.append(
                f"Chlorophyll {chlorophyll:.2f} mg/m³ is low in this MVP "
                "rule set."
            )

    # SST is deliberately a weak supporting factor; without species-specific
    # habitat data we do not claim that one temperature is "good for fish".
    if sst is not None:
        factors["sst_c"] = sst
        if 24.0 <= sst <= 30.0:
            score += 10
            reasoning.append(
                f"SST {sst:.1f} °C falls inside the broad tropical-water "
                "support band used by this MVP rule set."
            )
        else:
            reasoning.append(
                f"SST {sst:.1f} °C is outside the broad tropical-water "
                "support band used by this MVP rule set."
            )

    score = max(0.0, min(100.0, score))

    if score >= 75:
        level = "GO"
    elif score >= 45:
        level = "CAUTION"
    else:
        level = "AVOID"

    recognized_count = sum(
        value is not None for value in (chlorophyll, sst)
    )

    return {
        "score": score,
        "level": level,
        "reasoning": reasoning,
        "factors": factors,
        "confidence": _confidence_from_evidence(
            marine=marine,
            recognized_count=recognized_count,
            max_factors=2,
        ),
        "status": "available",
    }


def _confidence_from_evidence(
    *,
    weather: dict[str, Any] | None = None,
    marine: dict[str, Any] | None = None,
    recognized_count: int,
    max_factors: int,
) -> float:
    provider_confidence = 0.0
    if weather and weather.get("status") == "available":
        provider_confidence = max(
            provider_confidence,
            _number(weather.get("confidence")) or 0.0,
        )
    if marine and marine.get("status") == "available":
        provider_confidence = max(
            provider_confidence,
            _number(marine.get("confidence")) or 0.0,
        )

    coverage = recognized_count / max_factors
    return round(
        max(0.0, min(1.0, provider_confidence * (0.5 + 0.5 * coverage))),
        3,
    )
