from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    RED = "RED"
    AMBER = "AMBER"


class FrequentZoneCreate(BaseModel):
    user_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    alert_radius_km: float = Field(default=1.0, gt=0)
    language: str = Field(default="ta", min_length=2, max_length=10)
    active: bool = True


class FrequentZone(BaseModel):
    id: str
    user_id: str
    name: str
    latitude: float
    longitude: float
    alert_radius_km: float
    language: str
    active: bool


class AlertCheckRequest(BaseModel):
    user_id: str | None = None
    force: bool = False


class ProactiveAlert(BaseModel):
    id: str
    zone_id: str
    user_id: str
    alert_type: str
    severity: AlertSeverity
    title: str
    message: str
    boundary_distance_km: float | None
    inside_eez: bool | None
    source: str
    source_timestamp: datetime | None
    created_at: datetime
    delivery_status: str
