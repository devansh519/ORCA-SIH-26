from __future__ import annotations

"""
ORCA Experience API.

Fresh replacement based directly on the user's current main.py.

Preserves:
    - Experience API endpoint
    - proactive geofence API
    - background geofence poller
    - immediate poll on startup
    - poller status endpoint
    - CORS for the static local dashboard

Adds:
    - dynamic place-name resolution for reactive queries
    - optional coordinates for backwards compatibility
    - correct scenario labels
    - location-resolution evidence in the response
    - complete Golden Schema evidence summary
"""

import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from app.api.alerts import router as alerts_router
from app.graph.state import initial_state
from app.graph.workflow import build_response, run_workflow
from app.services.alert_poller import GeofenceAlertPoller
from app.tools.geocoding import GeocodingError, GeocodingTool


# ============================================================================
# REQUEST MODELS
# ============================================================================


class LocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    latitude: float | None = None
    longitude: float | None = None


class ExperienceQueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    language: str = "ta"
    voice_input: bool = False
    location: LocationInput | None = None
    question: str


# ============================================================================
# RESPONSE MODEL
# ============================================================================


def _quality_as_string(value: Any) -> str | None:
    """Normalize Golden Schema quality from string or nested dict form."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        level = value.get("level")
        if level is not None:
            return str(level)
    return str(value)


class ExperienceResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    scenario: str
    location: dict[str, Any]
    request: dict[str, Any]
    orchestration: dict[str, Any]
    golden_schema: dict[str, Any]
    context: dict[str, Any] | None = None
    sources: list[Any] | None = None

    answer: str | None = None
    recommendation: str | None = None
    geospatial: dict[str, Any] | None = None
    weather: dict[str, Any] | None = None
    marine: dict[str, Any] | None = None
    location_resolution: dict[str, Any] | None = None
    decision_engine: dict[str, Any] | None = None
    safety_score: float | None = None
    yield_score: float | None = None
    selected_tools: list[str] | None = None
    execution_status: str | None = None
    execution_errors: list[str] | None = None
    timestamp_utc: str | None = None
    confidence: float | None = None
    quality: str | None = None


# ============================================================================
# PROACTIVE POLLER
# ============================================================================


geofence_poller = GeofenceAlertPoller(
    interval_seconds=3 * 60 * 60,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await geofence_poller.start()

    try:
        yield
    finally:
        await geofence_poller.stop()


# ============================================================================
# APP
# ============================================================================


app = FastAPI(
    title="ORCA API",
    version="0.4.0-demo",
    lifespan=lifespan,
)


# ============================================================================
# CORS
# ============================================================================


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts_router)


# ============================================================================
# HEALTH
# ============================================================================


@app.get("/api/v1/health")
def healthcheck() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "orca",
    }


# ============================================================================
# POLLER STATUS
# ============================================================================


@app.get("/api/v1/alerts/poller/status")
async def poller_status() -> dict[str, Any]:
    return geofence_poller.status()


# ============================================================================
# LOCATION RESOLUTION
# ============================================================================


def _extract_location_name(question: str) -> str | None:
    """
    Extract a simple place phrase when the caller did not provide location.

    This is a fallback only. The frontend supplies a separate location name,
    which is preferred and avoids depending on natural-language parsing.
    """
    text = " ".join((question or "").strip().split())
    if not text:
        return None

    patterns = (
        r"\bnear\s+([A-Za-z][A-Za-z .'-]{1,80}?)(?:[?.!,]|$)",
        r"\baround\s+([A-Za-z][A-Za-z .'-]{1,80}?)(?:[?.!,]|$)",
        r"\bat\s+([A-Za-z][A-Za-z .'-]{1,80}?)(?:[?.!,]|$)",
        r"\bin\s+([A-Za-z][A-Za-z .'-]{1,80}?)(?:[?.!,]|$)",
    )

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(
                r"\b(tomorrow|today|tonight|this morning|this evening)\b.*$",
                "",
                candidate,
                flags=re.IGNORECASE,
            ).strip(" ,.")
            if candidate:
                return candidate

    return None


async def _resolve_request_location(
    payload: ExperienceQueryInput,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Return (resolved_location, resolution_evidence).

    Explicit coordinates remain accepted for backwards compatibility.
    Otherwise the supplied place name is resolved through Open-Meteo.
    """
    supplied = payload.location
    supplied_name = (supplied.name.strip() if supplied else "")

    if supplied and supplied.latitude is not None and supplied.longitude is not None:
        resolved = {
            "name": supplied_name,
            "latitude": supplied.latitude,
            "longitude": supplied.longitude,
        }
        evidence = {
            "status": "available",
            "source": "request_coordinates",
            "timestamp": None,
            "query": supplied_name,
            "name": supplied_name,
            "latitude": supplied.latitude,
            "longitude": supplied.longitude,
            "confidence": 1.0,
            "quality": "GOOD",
            "method": "explicit_coordinates",
        }
        return resolved, evidence

    location_name = supplied_name or _extract_location_name(payload.question)

    if not location_name:
        raise HTTPException(
            status_code=422,
            detail=(
                "A location name is required. "
                "Example: location.name='Rameswaram' "
                "or ask 'near Rameswaram'."
            ),
        )

    geocoder = GeocodingTool()

    try:
        evidence = await geocoder.resolve(location_name)
    except GeocodingError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    resolved = {
        "name": evidence["name"],
        "latitude": evidence["latitude"],
        "longitude": evidence["longitude"],
    }

    return resolved, evidence


# ============================================================================
# SCENARIO
# ============================================================================


def _scenario_for_query_type(query_type: str | None) -> str:
    return {
        "reactive_voice_query": "fishing_safety",
        "proactive_alert": "proactive_geofence_alert",
        "authority_district_hazard_dashboard": "authority_hazard_dashboard",
        "researcher_trend_analysis": "researcher_marine_analysis",
        "boundary_geofence_query": "geospatial_boundary_demo",
    }.get(query_type or "", "orca_marine_query")


# ============================================================================
# EXPERIENCE QUERY
# ============================================================================


@app.post(
    "/api/v1/experience/query",
    response_model=ExperienceResponse,
)
async def submit_experience_query(
    payload: ExperienceQueryInput,
) -> ExperienceResponse:
    resolved_location, location_resolution = await _resolve_request_location(
        payload
    )

    state = initial_state(
        user_id=payload.user_id,
        user_role="fisherman",
        trigger_type="user_query",
        input_modality=(
            "voice"
            if payload.voice_input
            else "text"
        ),
        text=payload.question,
        user_language=payload.language,
        latitude=resolved_location["latitude"],
        longitude=resolved_location["longitude"],
        route=[],
    )

    state["location_name"] = resolved_location["name"]

    try:
        final_state = await run_workflow(state)
        workflow_response = build_response(final_state)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "ORCA workflow execution failed.",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        ) from exc

    geospatial = workflow_response.get("geospatial") or {}
    weather = workflow_response.get("weather") or {}
    marine = workflow_response.get("marine") or {}
    query_type = workflow_response.get("query_type")
    sources = list(workflow_response.get("sources", []))

    # Location resolution is request preprocessing, but exposing it in the
    # evidence list makes the live data lineage visible in the demo.
    sources.insert(
        0,
        {
            "tool": "geocoding",
            "source": location_resolution.get("source"),
            "timestamp": location_resolution.get("timestamp"),
            "quality": location_resolution.get("quality"),
            "confidence": location_resolution.get("confidence"),
            "status": location_resolution.get("status"),
        },
    )

    golden_variables = {
        "question": payload.question,
        "query_type": query_type,
        "weather": weather,
        "marine": marine,
        "geospatial": geospatial,
    }

    return ExperienceResponse(
        status="completed",
        scenario=_scenario_for_query_type(query_type),
        location=resolved_location,
        request={
            "user_id": payload.user_id,
            "language": payload.language,
            "voice_input": payload.voice_input,
            "question": payload.question,
        },
        orchestration={
            "entrypoint": "experience_api",
            "orchestrator": "orca_orchestrator",
            "query_type": query_type,
            "selected_tools": workflow_response.get(
                "selected_tools",
                [],
            ),
            "execution_status": workflow_response.get(
                "execution_status"
            ),
        },
        golden_schema={
            "source": "ORCA Evidence Fusion",
            "location": {
                "name": resolved_location["name"],
                "lat": resolved_location["latitude"],
                "lon": resolved_location["longitude"],
            },
            "variables": golden_variables,
            "units": {
                "lat": "degrees",
                "lon": "degrees",
                "distance": "km",
                "wind_speed": "m/s",
                "wave_height": "m",
                "temperature": "°C",
            },
            "quality": _quality_as_string(workflow_response.get("quality")),
            "confidence": workflow_response.get("confidence"),
            "timestamp": workflow_response.get("timestamp_utc"),
        },
        context=None,
        sources=sources,
        answer=workflow_response.get("answer"),
        recommendation=workflow_response.get("recommendation"),
        geospatial=geospatial,
        weather=weather,
        marine=marine,
        location_resolution=location_resolution,
        decision_engine=workflow_response.get("decision_engine"),
        safety_score=workflow_response.get("safety_score"),
        yield_score=workflow_response.get("yield_score"),
        selected_tools=workflow_response.get("selected_tools", []),
        execution_status=workflow_response.get("execution_status"),
        execution_errors=workflow_response.get("execution_errors", []),
        timestamp_utc=workflow_response.get("timestamp_utc"),
        confidence=workflow_response.get("confidence"),
        quality=_quality_as_string(workflow_response.get("quality")),
    )


# ============================================================================
# LOCAL ENTRYPOINT
# ============================================================================


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
