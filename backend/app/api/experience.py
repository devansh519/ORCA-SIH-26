from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter

from app.main import ExperienceQueryInput
from app.services.live_context import LiveContextService

router = APIRouter(prefix="/api/v1", tags=["experience"])


@router.post("/experience/query")
async def submit_experience_query(payload: ExperienceQueryInput) -> dict[str, Any]:
    target_time = datetime.now(timezone.utc) + timedelta(days=1)
    service = LiveContextService()
    context = await service.fetch_context(
        latitude=payload.location.latitude,
        longitude=payload.location.longitude,
        target_time=target_time,
        request_id=payload.user_id,
    )

    return {
        "status": "completed",
        "scenario": "rameswaram_fishing_safety",
        "location": {
            "name": payload.location.name,
            "latitude": payload.location.latitude,
            "longitude": payload.location.longitude,
        },
        "request": {
            "user_id": payload.user_id,
            "language": payload.language,
            "voice_input": payload.voice_input,
            "question": payload.question,
        },
        "context": context,
        "sources": context["sources"],
        "orchestration": {
            "entrypoint": "experience_api",
            "next_stage": "context_and_intent",
        },
    }
