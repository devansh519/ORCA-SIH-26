from __future__ import annotations

"""
ORCA Experience API

Fresh replacement for backend/app/main.py.

Preserves the existing Experience API contract and adds:
    - proactive geofence alert API
    - background geofence poller
    - immediate poll on application startup
    - poller status endpoint for demo/testing
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from app.api.alerts import router as alerts_router
from app.graph.state import initial_state
from app.graph.workflow import build_response, run_workflow
from app.services.alert_poller import GeofenceAlertPoller


# ============================================================================
# REQUEST MODELS
# ============================================================================


class LocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    latitude: float
    longitude: float


class ExperienceQueryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    language: str = "ta"
    voice_input: bool = False
    location: LocationInput
    question: str


# ============================================================================
# RESPONSE MODEL
# ============================================================================


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
    version="0.3.1-demo",
    lifespan=lifespan,
)

# ============================================================================
# CORS
# ============================================================================
# Demo frontend runs separately on localhost:5500.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
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
    """
    Demo/diagnostic endpoint.

    Confirms that the background proactive poller is alive and shows the
    result of its most recent automatic check.
    """
    return geofence_poller.status()


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
        latitude=payload.location.latitude,
        longitude=payload.location.longitude,
        route=[],
    )

    state["location_name"] = payload.location.name

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
    sources = workflow_response.get("sources", [])

    return ExperienceResponse(
        status="completed",
        scenario="geospatial_boundary_demo",
        location={
            "name": payload.location.name,
            "latitude": payload.location.latitude,
            "longitude": payload.location.longitude,
        },
        request={
            "user_id": payload.user_id,
            "language": payload.language,
            "voice_input": payload.voice_input,
            "question": payload.question,
        },
        orchestration={
            "entrypoint": "experience_api",
            "orchestrator": "orca_orchestrator",
            "query_type": workflow_response.get("query_type"),
            "selected_tools": workflow_response.get(
                "selected_tools",
                [],
            ),
            "execution_status": workflow_response.get(
                "execution_status"
            ),
        },
        golden_schema={
            "source": geospatial.get("source") or "experience_api",
            "location": {
                "name": payload.location.name,
                "lat": payload.location.latitude,
                "lon": payload.location.longitude,
            },
            "variables": {
                "question": payload.question,
                "query_type": workflow_response.get("query_type"),
                "geospatial": geospatial,
            },
            "units": {
                "lat": "degrees",
                "lon": "degrees",
                "distance": "km",
            },
            "quality": geospatial.get("quality", "GOOD"),
            "confidence": geospatial.get("confidence", 0.0),
            "timestamp": workflow_response.get("timestamp_utc"),
        },
        context=None,
        sources=sources,
        answer=workflow_response.get("answer"),
        recommendation=workflow_response.get("recommendation"),
        geospatial=geospatial,
        safety_score=workflow_response.get("safety_score"),
        yield_score=workflow_response.get("yield_score"),
        selected_tools=workflow_response.get("selected_tools", []),
        execution_status=workflow_response.get("execution_status"),
        execution_errors=workflow_response.get("execution_errors", []),
        timestamp_utc=workflow_response.get("timestamp_utc"),
        confidence=workflow_response.get("confidence"),
        quality=workflow_response.get("quality"),
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
