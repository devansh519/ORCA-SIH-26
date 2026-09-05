from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from app.schemas import GoldenLocation, GoldenSchema
from app.services.live_context import LiveContextService


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


class ExperienceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    scenario: str
    location: dict[str, Any]
    request: dict[str, Any]
    orchestration: dict[str, str]
    golden_schema: dict[str, Any]
    context: dict[str, Any] | None = None
    sources: list[str] | None = None


app = FastAPI(title="ORCA API", version="0.1.0")


@app.get("/api/v1/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/experience/query", response_model=ExperienceResponse)
async def submit_experience_query(payload: ExperienceQueryInput) -> ExperienceResponse:
    golden_schema = GoldenSchema(
        source="experience_api",
        location=GoldenLocation(
            name=payload.location.name,
            lat=payload.location.latitude,
            lon=payload.location.longitude,
        ),
        variables={
            "fishing_question": payload.question,
            "scenario": "rameswaram_fishing_safety",
        },
        units={
            "lat": "degrees",
            "lon": "degrees",
        },
        quality={
            "voice_input": payload.voice_input,
            "language": payload.language,
        },
        confidence=0.9,
    )

    target_time = datetime.now(timezone.utc) + timedelta(days=1)
    context_service = LiveContextService()
    context = await context_service.fetch_context(
        latitude=payload.location.latitude,
        longitude=payload.location.longitude,
        target_time=target_time,
        request_id=payload.user_id,
    )

    response = ExperienceResponse(
        status="accepted",
        scenario="rameswaram_fishing_safety",
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
            "next_stage": "context_and_intent",
        },
        golden_schema=golden_schema.model_dump(mode="json"),
    )

    response_dict = response.model_dump(mode="json")
    response_dict["context"] = context
    response_dict["sources"] = context["sources"]
    return ExperienceResponse(**response_dict)
