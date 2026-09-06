"""
ORCA workflow execution layer.

Fresh compatibility replacement.

Fixes:
1. Adds explicit boundary/geofence intent detection before the existing
   orchestrator classifier, so:
       "Am I near the international maritime boundary?"
   becomes:
       boundary_geofence_query
2. Uses the ACTUAL existing tool class names:
       MarineDataTool
       WeatherTool
       GeospatialTool
3. Uses the ACTUAL existing GeospatialTool interface:
       is_inside_eez(...)
       check_route(...)
4. Preserves the already-proven Supabase/PostGIS execution path.
5. Preserves the existing ORCA core classifier for all other intents.
6. Never fabricates weather, marine, safety, or yield values.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.orchestrator.core import IncomingRequest, classify_intent
from app.tools.geospatial import GeospatialTool
from app.tools.marine import MarineDataTool
from app.tools.weather import WeatherTool

from .state import ORCAState


# ============================================================================
# CONSTANTS
# ============================================================================

BOUNDARY_QUERY = "boundary_geofence_query"


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

    if _is_boundary_query(text):
        query_type = BOUNDARY_QUERY
    else:
        query_type = classify_intent(
            _incoming_request(state)
        )

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
    Turn the real geospatial result into an operation-specific answer.

    Safety/yield scores remain null because this demo path is geospatial-only.
    """
    state["safety_score"] = None
    state["yield_score"] = None

    geo = state.get("geospatial_result") or {}
    query_type = state.get("query_type")
    operation = geo.get("operation") or _detect_geospatial_operation(
        state.get("text", ""),
        state.get("route") or [],
    )

    if geo.get("status") != "available":
        state["recommendation"] = "DATA_UNAVAILABLE"
        state["recommendation_text"] = (
            geo.get("reason")
            if operation == "unsupported_coastline"
            else "A reliable geospatial result is not available for this request."
        )
        state["execution_status"] = "decided"
        return state

    if operation == "point_distance":
        distance = geo.get("distance_km")
        if distance is None:
            state["recommendation"] = "DISTANCE_UNAVAILABLE"
            state["recommendation_text"] = (
                "The nearest EEZ-boundary distance is unavailable."
            )
        else:
            state["recommendation"] = "EEZ_BOUNDARY_DISTANCE"
            state["recommendation_text"] = (
                f"The supplied location is approximately {float(distance):.2f} km "
                "from the nearest EEZ boundary."
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
            state["recommendation_text"] = "The supplied location is inside an EEZ."
        elif inside is False:
            state["recommendation"] = "OUTSIDE_EEZ"
            state["recommendation_text"] = "The supplied location is outside the EEZ."
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

    state["execution_status"] = "decided"
    return state


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
        "sources": state.get(
            "sources",
            [],
        ),
        "timestamp_utc": timestamp,
        "confidence": geo.get(
            "confidence"
        ),
        "quality": geo.get(
            "quality"
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
