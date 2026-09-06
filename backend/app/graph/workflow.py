"""
ORCA workflow execution layer.

Fresh replacement based directly on the current uploaded workflow.

Integrated change:
- Adds the deterministic ORCA DecisionEngine after evidence fusion.
- Preserves the existing boundary/geofence classifier and PostGIS path.
- Preserves the existing WeatherTool, MarineDataTool, and GeospatialTool calls.
- Keeps geospatial question answers operation-specific.
- Produces safety and fishing-yield scores independently.
- Never fabricates a score when the relevant evidence is unavailable.
"""


from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.decision.engine import DecisionEngine
from app.orchestrator.core import IncomingRequest, classify_intent
from app.tools.geospatial import GeospatialTool
from app.tools.marine import MarineDataTool
from app.tools.weather import WeatherTool

from .state import ORCAState


# ============================================================================
# CONSTANTS
# ============================================================================

BOUNDARY_QUERY = "boundary_geofence_query"

# Deterministic decision engine. Tool calls remain in this workflow;
# the engine only evaluates the evidence returned by those tools.
decision_engine = DecisionEngine()


# ============================================================================
# HELPERS
# ============================================================================


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_target_time(value: Any) -> datetime:
    """
    Ensure forecast tools never receive None as target_time.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    # The current demo does not require a forecast date for boundary checks.
    # A concrete UTC timestamp keeps the state safe for weather/marine tools.
    return datetime.now(timezone.utc)


def _is_boundary_query(text: str) -> bool:
    """
    Detect explicit maritime-boundary / EEZ / geofence questions.

    This is intentionally deterministic and runs before the existing core
    classifier because the current core QueryType contract does not contain
    a boundary-specific query type.
    """
    value = (text or "").strip().lower()

    terms = (
        "international maritime boundary",
        "maritime boundary",
        "international boundary",
        "imbl",
        "eez",
        "exclusive economic zone",
        "territorial waters",
        "territorial sea",
        "geofence",
        "geo fence",
        "boundary",
        "inside the boundary",
        "outside the boundary",
        "near the boundary",
        "near boundary",
        "cross the boundary",
        "crossing the boundary",
        "near eez",
        "inside eez",
        "outside eez",
        # Tamil
        "கடல் எல்லை",
        "சர்வதேச கடல் எல்லை",
        "எல்லைக்கு அருகில்",
        "எல்லை அருகில்",
        "எல்லைக்குள்",
        "எல்லைக்கு வெளியே",
    )

    return any(term in value for term in terms)


def _detect_geospatial_operation(text: str, route: list[Any] | None = None) -> str:
    """
    Decide what the user is actually asking the geospatial tool to do.

    Supported real operations:
      - point_containment: inside/outside EEZ
      - point_distance: distance to nearest EEZ boundary
      - route_intersection: route/EEZ intersection
      - unsupported_coastline: coastline/land-distance requests are not
        answered from the EEZ dataset.
      - point_analysis: generic geospatial request
    """
    value = (text or "").strip().lower()

    if route and len(route) >= 2:
        return "route_intersection"

    distance_terms = (
        "how far",
        "distance",
        "km from",
        "kilometre",
        "kilometer",
        "away from",
        "how close",
        "close to",
        "near the boundary",
        "near boundary",
    )
    coastline_terms = (
        "coastal land",
        "coastline",
        "coast line",
        "shore",
        "shoreline",
        "land from",
        "land distance",
        "distance from land",
    )
    route_terms = (
        "route",
        "path",
        "trip line",
        "does my route",
        "will my route",
        "cross the boundary",
        "cross eeZ",
    )
    containment_terms = (
        "am i inside",
        "inside the eez",
        "inside eez",
        "within the eez",
        "within eez",
        "in the eez",
        "outside the eez",
        "outside eez",
        "inside the maritime boundary",
        "inside the boundary",
        "within the maritime boundary",
    )

    if any(term in value for term in coastline_terms):
        return "unsupported_coastline"

    if any(term in value for term in route_terms):
        return "route_intersection"

    if any(term in value for term in distance_terms):
        return "point_distance"

    if any(term in value for term in containment_terms):
        return "point_containment"

    return "point_analysis"


def _select_tools(query_type: str) -> list[str]:
    """
    Deterministic tool selection.

    Boundary queries use only geospatial because they require a spatial
    containment/distance calculation, not a weather or marine forecast.
    """

    if query_type == BOUNDARY_QUERY:
        return ["geospatial"]

    if query_type == "reactive_voice_query":
        return ["weather", "marine", "geospatial"]

    if query_type == "proactive_alert":
        return ["weather", "geospatial"]

    if query_type == "authority_district_hazard_dashboard":
        return ["weather", "geospatial"]

    if query_type == "researcher_trend_analysis":
        return ["marine"]

    # Preserve the previous demo behavior: an unclassified request still
    # gets the geospatial path rather than silently doing nothing.
    return ["geospatial"]


def _incoming_request(state: ORCAState) -> IncomingRequest:
    return IncomingRequest(
        user_role=state["user_role"],
        trigger_type=state["trigger_type"],
        input_modality=state["input_modality"],
        text=state.get("text", ""),
        hazard_zone_overlap=state.get(
            "hazard_zone_overlap",
            False,
        ),
    )


# ============================================================================
# CLASSIFICATION
# ============================================================================


async def classify_node(state: ORCAState) -> ORCAState:
    """
    Classify and route the request.

    Boundary intent is handled first.
    All other intents continue through the existing ORCA core classifier.
    """

    text = state.get("text", "")
    incoming = _incoming_request(state)

    # Fisherman safety questions must take the reactive safety path.
    # This is intentionally checked before the boundary detector because a
    # valid safety question may also mention an EEZ/boundary (for example,
    # "is it safe to fish near the boundary?"). The reactive path still runs
    # the geospatial check, so boundary evidence is not lost.
    if (
        incoming.user_role == "fisherman"
        and incoming.trigger_type == "user_query"
        and any(
            keyword.lower() in incoming.text.lower()
            for keyword in (
                "safe",
                "fish",
                "tomorrow",
                "go",
                "danger",
                "போகலாமா",
                "பாதுகாப்பா",
            )
        )
    ):
        query_type = "reactive_voice_query"
    elif _is_boundary_query(text):
        query_type = BOUNDARY_QUERY
    else:
        query_type = classify_intent(incoming)

    state["query_type"] = query_type
    state["selected_tools"] = _select_tools(query_type)

    # Fix the previous None target-time failure for Weather/Marine.
    state["target_time"] = _resolve_target_time(
        state.get("target_time")
    )

    state["execution_status"] = "classified"

    print(
        f"[ORCA] intent={query_type} "
        f"tools={state['selected_tools']}"
    )

    return state


# ============================================================================
# TOOL RUNNERS
# ============================================================================


async def _run_weather(
    state: ORCAState,
    tool: WeatherTool,
) -> dict[str, Any]:
    latitude = state.get("latitude")
    longitude = state.get("longitude")

    if latitude is None or longitude is None:
        return {
            "status": "unavailable",
            "source": "weather",
            "reason": "coordinates_missing",
            "variables": {},
            "quality": "UNAVAILABLE",
            "confidence": 0.0,
        }

    return await tool.fetch(
        latitude=latitude,
        longitude=longitude,
        target_time=_resolve_target_time(
            state.get("target_time")
        ),
    )


async def _run_marine(
    state: ORCAState,
    tool: MarineDataTool,
) -> dict[str, Any]:
    latitude = state.get("latitude")
    longitude = state.get("longitude")

    if latitude is None or longitude is None:
        return {
            "status": "unavailable",
            "source": "marine",
            "reason": "coordinates_missing",
            "variables": {},
            "quality": "UNAVAILABLE",
            "confidence": 0.0,
        }

    return await tool.fetch(
        latitude=latitude,
        longitude=longitude,
        target_time=_resolve_target_time(
            state.get("target_time")
        ),
    )


async def _run_geospatial(
    state: ORCAState,
    tool: GeospatialTool,
) -> dict[str, Any]:
    """
    Execute the geospatial operation requested by the user's question.

    The existing live GeospatialTool remains the source of truth:
      is_inside_eez(...) -> real PostGIS point result
      check_route(...)   -> real PostGIS route result

    We only choose which operation to call and normalize the response.
    No geospatial values are fabricated.
    """
    latitude = state.get("latitude")
    longitude = state.get("longitude")
    route = state.get("route") or []
    question = state.get("text", "")

    operation = _detect_geospatial_operation(question, route)

    if operation == "unsupported_coastline":
        return {
            "status": "unavailable",
            "operation": operation,
            "question": question,
            "source": "Marine Regions World EEZ v12",
            "reason": (
                "coastline_geometry_not_configured: the current live "
                "geospatial dataset supports EEZ boundary analysis, not "
                "distance to Indian coastal land."
            ),
            "inside": None,
            "distance_km": None,
            "confidence": 0.0,
            "quality": "UNAVAILABLE",
        }

    if latitude is None or longitude is None:
        return {
            "status": "unavailable",
            "operation": operation,
            "question": question,
            "source": "Marine Regions World EEZ v12",
            "reason": "coordinates_missing",
            "inside": None,
            "distance_km": None,
            "confidence": 0.0,
            "quality": "UNAVAILABLE",
        }

    if operation == "route_intersection":
        if len(route) < 2:
            return {
                "status": "unavailable",
                "operation": operation,
                "question": question,
                "source": "Marine Regions World EEZ v12",
                "reason": "route_coordinates_missing",
                "inside": None,
                "distance_km": None,
                "confidence": 0.0,
                "quality": "UNAVAILABLE",
            }

        result = await tool.check_route(route)
        result = dict(result)
        result["operation"] = "route_intersection"
        result["question"] = question
        return result

    result = await tool.is_inside_eez(
        latitude=latitude,
        longitude=longitude,
    )
    result = dict(result)
    result["operation"] = operation
    result["question"] = question
    return result


# ============================================================================
# TOOL EXECUTION
# ============================================================================


async def execute_tools_node(
    state: ORCAState,
) -> ORCAState:
    """
    Execute selected tools concurrently.

    A failure in one tool does not erase results from other tools.
    """

    selected = state.get("selected_tools", [])

    tool_instances: dict[str, Any] = {
        "weather": WeatherTool(),
        "marine": MarineDataTool(),
        "geospatial": GeospatialTool(),
    }

    runners: dict[str, Any] = {
        "weather": _run_weather,
        "marine": _run_marine,
        "geospatial": _run_geospatial,
    }

    async def execute_one(
        name: str,
    ) -> tuple[str, dict[str, Any]]:
        try:
            result = await runners[name](
                state,
                tool_instances[name],
            )
            return name, result

        except Exception as exc:
            error = (
                f"{name}: {type(exc).__name__}: {exc}"
            )
            state["execution_errors"].append(error)

            return name, {
                "status": "unavailable",
                "source": name,
                "reason": "tool_execution_failed",
                "detail": str(exc),
                "variables": {},
                "quality": "UNAVAILABLE",
                "confidence": 0.0,
            }

    if selected:
        results = await asyncio.gather(
            *(execute_one(name) for name in selected)
        )
    else:
        results = []

    for name, result in results:
        state["tool_results"][name] = result

        if name == "weather":
            state["weather_result"] = result
        elif name == "marine":
            state["marine_result"] = result
        elif name == "geospatial":
            state["geospatial_result"] = result

    state["execution_status"] = (
        "tools_completed"
        if not state["execution_errors"]
        else "partial"
    )

    return state


# ============================================================================
# FUSION
# ============================================================================


def _build_sources(
    state: ORCAState,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []

    for name, result in state.get(
        "tool_results",
        {},
    ).items():
        if not isinstance(result, dict):
            continue

        sources.append(
            {
                "tool": name,
                "source": result.get("source"),
                "timestamp": result.get("timestamp"),
                "quality": result.get("quality"),
                "confidence": result.get("confidence"),
                "status": result.get("status"),
            }
        )

    return sources


async def fuse_node(
    state: ORCAState,
) -> ORCAState:
    """
    Evidence-preserving fusion.

    No weather/marine values are invented.
    """

    state["sources"] = _build_sources(state)

    state["fused_data"] = {
        "query_type": state.get("query_type"),
        "location": {
            "latitude": state.get("latitude"),
            "longitude": state.get("longitude"),
        },
        "target_time": state.get("target_time"),
        "weather": state.get("weather_result"),
        "marine": state.get("marine_result"),
        "geospatial": state.get("geospatial_result"),
        "sources": state.get("sources", []),
    }

    state["execution_status"] = "fused"

    return state


# ============================================================================
# DECISION
# ============================================================================


async def decide_node(
    state: ORCAState,
) -> ORCAState:
    """
    Evaluate fused evidence with the deterministic DecisionEngine.

    Safety and fishing-yield scores are always independent:
      - safety uses weather/hazard evidence;
      - yield uses marine evidence;
      - neither is fabricated when its source is unavailable.

    Pure geospatial questions keep their operation-specific answer even when
    weather/marine evidence is unavailable, so boundary questions do not turn
    into an unrelated safety-data error.
    """
    weather = state.get("weather_result") or {}
    marine = state.get("marine_result") or {}
    geo = state.get("geospatial_result") or {}

    decision = decision_engine.evaluate(
        weather=weather,
        marine=marine,
        geospatial=geo,
    )

    state["safety_score"] = decision.safety.score
    state["safety_score_reasoning"] = (
        " ".join(decision.safety.reasoning)
        if decision.safety.reasoning
        else None
    )
    state["yield_score"] = decision.yield_assessment.score
    state["yield_reasoning"] = (
        " ".join(decision.yield_assessment.reasoning)
        if decision.yield_assessment.reasoning
        else None
    )

    query_type = state.get("query_type")
    operation = geo.get("operation") or _detect_geospatial_operation(
        state.get("text", ""),
        state.get("route") or [],
    )

    # ------------------------------------------------------------------
    # Pure geospatial path: preserve the useful spatial result.
    # ------------------------------------------------------------------
    if query_type == BOUNDARY_QUERY:
        if geo.get("status") != "available":
            state["recommendation"] = "DATA_UNAVAILABLE"
            state["recommendation_text"] = (
                geo.get("reason")
                if operation == "unsupported_coastline"
                else "A reliable geospatial result is not available for this request."
            )
        elif operation == "point_distance":
            distance = geo.get("distance_km")
            if distance is None:
                state["recommendation"] = "DISTANCE_UNAVAILABLE"
                state["recommendation_text"] = (
                    "The nearest EEZ-boundary distance is unavailable."
                )
            else:
                state["recommendation"] = "EEZ_BOUNDARY_DISTANCE"
                state["recommendation_text"] = (
                    f"The supplied location is approximately "
                    f"{float(distance):.2f} km from the nearest EEZ boundary."
                )
        elif operation == "point_containment":
            inside = geo.get("inside")
            if inside is True:
                state["recommendation"] = "INSIDE_EEZ"
                state["recommendation_text"] = (
                    "Yes. The supplied location is inside an EEZ polygon."
                )
            elif inside is False:
                state["recommendation"] = "OUTSIDE_EEZ"
                state["recommendation_text"] = (
                    "No. The supplied location is outside the EEZ polygons "
                    "in the dataset."
                )
            else:
                state["recommendation"] = "CONTAINMENT_UNAVAILABLE"
                state["recommendation_text"] = (
                    "The EEZ containment result is unavailable."
                )
        elif operation == "route_intersection":
            intersects = geo.get("intersects_eez")
            distance = (
                geo.get("minimum_distance_km")
                if geo.get("minimum_distance_km") is not None
                else geo.get("distance_km")
            )

            if intersects is True:
                state["recommendation"] = "BOUNDARY_CROSSING"
                state["recommendation_text"] = (
                    "The supplied route intersects an EEZ boundary."
                )
            elif intersects is False:
                state["recommendation"] = "ROUTE_CLEAR"
                if distance is not None:
                    state["recommendation_text"] = (
                        "The supplied route does not intersect an EEZ boundary. "
                        f"Its minimum distance to the EEZ geometry is "
                        f"approximately {float(distance):.2f} km."
                    )
                else:
                    state["recommendation_text"] = (
                        "The supplied route does not intersect an EEZ boundary."
                    )
            else:
                state["recommendation"] = "ROUTE_CHECK_UNAVAILABLE"
                state["recommendation_text"] = (
                    "The route could not be compared with the EEZ geometry."
                )
        else:
            inside = geo.get("inside")
            distance = geo.get("distance_km")

            if inside is True:
                state["recommendation"] = "INSIDE_EEZ"
                state["recommendation_text"] = (
                    "The supplied location is inside an EEZ."
                )
            elif inside is False:
                state["recommendation"] = "OUTSIDE_EEZ"
                state["recommendation_text"] = (
                    "The supplied location is outside the EEZ."
                )
                if distance is not None:
                    state["recommendation_text"] += (
                        f" It is approximately {float(distance):.2f} km "
                        "from the nearest EEZ boundary."
                    )
            else:
                state["recommendation"] = "DATA_AVAILABLE"
                state["recommendation_text"] = (
                    "The geospatial tool returned a valid EEZ result."
                )

    # ------------------------------------------------------------------
    # Multi-tool / fishing decision path.
    # ------------------------------------------------------------------
    else:
        state["recommendation"] = decision.recommendation
        # Keep the deterministic recommendation, but answer the actual user
        # question from the live weather/marine evidence instead of returning
        # the same generic sentence for every query.
        state["recommendation_text"] = _build_question_specific_answer(state)

    # Keep the structured engine result in state for API/observability.
    state["decision_engine"] = decision.model_dump(mode="json")
    state["execution_status"] = "decided"
    return state


# ============================================================================
# QUESTION-SPECIFIC ANSWER BUILDER
# ============================================================================


def _question_focus(text: str) -> str:
    """Return the narrow information focus requested by the user."""
    value = (text or "").lower()

    # The dashboard may send conversation context followed by the current
    # question. Prefer the explicit current-question section when present.
    if "current user question:" in value:
        value = value.rsplit("current user question:", 1)[1].strip()

    if any(term in value for term in (
        "wind speed", "wind", "காற்றின் வேகம்", "காற்று வேகம்",
    )):
        return "wind"
    if any(term in value for term in (
        "wave condition", "wave conditions", "wave height", "waves",
        "swell", "அலை", "அலைகள்",
    )):
        return "waves"
    if any(term in value for term in (
        "temperature", "sea surface temperature", "sst", "வெப்பநிலை",
    )):
        return "sst"
    if any(term in value for term in (
        "rain", "rainfall", "precipitation", "மழை",
    )):
        return "rain"
    if any(term in value for term in (
        "gust", "wind gust", "காற்றடிப்பு",
    )):
        return "gust"
    if any(term in value for term in (
        "pressure", "அழுத்தம்",
    )):
        return "pressure"
    if any(term in value for term in (
        "cloud", "cloud cover", "மேக",
    )):
        return "cloud"
    return "safety"


def _first_number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _build_question_specific_answer(state: ORCAState) -> str:
    """Build a useful answer from live tool evidence without inventing data."""
    question = state.get("text", "")
    focus = _question_focus(question)
    weather = state.get("weather_result") or {}
    marine = state.get("marine_result") or {}
    weather_vars = weather.get("variables") or {}
    marine_vars = marine.get("variables") or {}
    decision = state.get("decision_engine") or {}
    recommendation = state.get("recommendation") or "INSUFFICIENT_DATA"

    if focus == "wind":
        value = _first_number(weather_vars.get("wind_speed_ms"))
        if value is not None:
            return f"Tomorrow's forecast wind speed near {state.get('location_name') or 'the requested location'} is about {value:.1f} m/s. The current safety assessment is {recommendation}."

    if focus == "gust":
        value = _first_number(weather_vars.get("wind_gusts_ms"))
        if value is not None:
            return f"Tomorrow's forecast wind gusts near {state.get('location_name') or 'the requested location'} are about {value:.1f} m/s. The current safety assessment is {recommendation}."

    if focus == "waves":
        value = _first_number(marine_vars.get("wave_height_m"))
        if value is not None:
            return f"Tomorrow's forecast wave height near {state.get('location_name') or 'the requested location'} is about {value:.1f} m. The current safety assessment is {recommendation}."

    if focus == "sst":
        value = _first_number(marine_vars.get("sst_c"))
        if value is not None:
            return f"Tomorrow's forecast sea-surface temperature near {state.get('location_name') or 'the requested location'} is about {value:.1f} °C. The fishing-yield assessment is {state.get('yield_score') if state.get('yield_score') is not None else 'unavailable'}."

    if focus == "rain":
        value = _first_number(weather_vars.get("rain_mm"))
        if value is None:
            value = _first_number(weather_vars.get("precipitation_mm"))
        if value is not None:
            return f"Tomorrow's forecast rainfall near {state.get('location_name') or 'the requested location'} is about {value:.1f} mm. The current safety assessment is {recommendation}."

    if focus == "pressure":
        value = _first_number(weather_vars.get("pressure_msl_hpa"))
        if value is not None:
            return f"Tomorrow's forecast mean sea-level pressure near {state.get('location_name') or 'the requested location'} is about {value:.1f} hPa. The current safety assessment is {recommendation}."

    if focus == "cloud":
        value = _first_number(weather_vars.get("cloud_cover_pct"))
        if value is not None:
            return f"Tomorrow's forecast cloud cover near {state.get('location_name') or 'the requested location'} is about {value:.0f}%. The current safety assessment is {recommendation}."

    # General fishing-safety question: retain the deterministic decision text,
    # but add the live factors so different questions are not all identical.
    parts: list[str] = []
    if recommendation:
        parts.append(f"ORCA's deterministic safety rules currently classify the supplied conditions as {recommendation}.")

    wind = _first_number(weather_vars.get("wind_speed_ms"))
    gust = _first_number(weather_vars.get("wind_gusts_ms"))
    wave = _first_number(marine_vars.get("wave_height_m"))
    distance = _first_number((state.get("geospatial_result") or {}).get("distance_km"))

    factors: list[str] = []
    if wind is not None:
        factors.append(f"wind {wind:.1f} m/s")
    if gust is not None:
        factors.append(f"gusts {gust:.1f} m/s")
    if wave is not None:
        factors.append(f"waves {wave:.1f} m")
    if distance is not None:
        factors.append(f"EEZ boundary distance {distance:.2f} km")

    if factors:
        parts.append("Live factors: " + ", ".join(factors) + ".")

    return " ".join(parts) if parts else "ORCA could not produce a reliable answer from the available evidence."


# ============================================================================
# WORKFLOW ENTRYPOINT
# ============================================================================


async def run_workflow(
    state: ORCAState,
) -> ORCAState:
    """
    Run the ORCA execution flow.
    """

    state["timestamp_utc"] = _iso_utc()

    state = await classify_node(state)
    state = await execute_tools_node(state)
    state = await fuse_node(state)
    state = await decide_node(state)

    return state


# ============================================================================
# API RESPONSE BUILDER
# ============================================================================


def build_response(
    state: ORCAState,
) -> dict[str, Any]:
    geo = (
        state.get("geospatial_result")
        or state.get(
            "tool_results",
            {},
        ).get("geospatial")
        or {}
    )

    timestamp = (
        geo.get("timestamp")
        or state.get("timestamp_utc")
    )

    tool_results = state.get("tool_results", {})
    available_confidences = [
        float(result.get("confidence"))
        for result in tool_results.values()
        if isinstance(result, dict)
        and result.get("status") == "available"
        and isinstance(result.get("confidence"), (int, float))
    ]
    overall_confidence = (
        sum(available_confidences) / len(available_confidences)
        if available_confidences
        else None
    )

    available_qualities = [
        result.get("quality")
        for result in tool_results.values()
        if isinstance(result, dict)
        and result.get("status") == "available"
        and result.get("quality")
    ]

    return {
        "query_type": state.get("query_type"),
        "selected_tools": state.get(
            "selected_tools",
            [],
        ),
        "execution_status": state.get(
            "execution_status"
        ),
        "execution_errors": state.get(
            "execution_errors",
            [],
        ),
        "location": {
            "name": state.get("location_name"),
            "latitude": state.get("latitude"),
            "longitude": state.get("longitude"),
        },
        "geospatial": geo,
        "geospatial_operation": geo.get("operation"),
        "question": state.get("text", ""),
        "weather": state.get(
            "weather_result"
        ),
        "marine": state.get(
            "marine_result"
        ),
        "recommendation": state.get(
            "recommendation"
        ),
        "answer": state.get(
            "recommendation_text"
        ),
        "safety_score": state.get(
            "safety_score"
        ),
        "yield_score": state.get(
            "yield_score"
        ),
        "safety_score_reasoning": state.get(
            "safety_score_reasoning"
        ),
        "yield_reasoning": state.get(
            "yield_reasoning"
        ),
        "decision_engine": state.get(
            "decision_engine"
        ),
        "sources": state.get(
            "sources",
            [],
        ),
        "timestamp_utc": timestamp,
        "confidence": overall_confidence,
        "quality": (
            "GOOD"
            if available_qualities and all(q == "GOOD" for q in available_qualities)
            else (available_qualities[0] if available_qualities else None)
        ),
    }


__all__ = [
    "classify_node",
    "execute_tools_node",
    "fuse_node",
    "decide_node",
    "run_workflow",
    "build_response",
]
