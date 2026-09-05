from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GoldenLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float
    lon: float
    name: str | None = None


class GoldenSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    location: GoldenLocation
    variables: dict[str, Any] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
