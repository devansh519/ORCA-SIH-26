from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from app.tools.base import BaseTool


class GeospatialTool(BaseTool):
    """Geospatial analysis interface for coordinate and boundary checks. Requires PostGIS configuration in later deployment."""

    def __init__(self) -> None:
        super().__init__("geospatial")

    @staticmethod
    def readiness_status() -> dict[str, Any]:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return {
                "status": "unavailable",
                "reason": "database_url_missing",
                "database_url_configured": False,
            }
        return {
            "status": "unavailable",
            "reason": "postgis_extension_missing",
            "database_url_configured": True,
        }

    @staticmethod
    def validate_coordinates(latitude: float, longitude: float) -> bool:
        return -90 <= latitude <= 90 and -180 <= longitude <= 180

    @staticmethod
    def calculate_freshness(age_seconds: int | float) -> str:
        if age_seconds < 900:
            return "FRESH"
        if age_seconds < 36000:
            return "STALE"
        return "EXPIRED"

    @staticmethod
    def distance_km(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
        if not GeospatialTool.validate_coordinates(latitude_a, longitude_a) or not GeospatialTool.validate_coordinates(latitude_b, longitude_b):
            raise ValueError("invalid coordinates")
        return 0.0

    def is_inside_eez(self, *, latitude: float, longitude: float) -> dict[str, Any]:
        readiness = self.readiness_status()
        return {
            "status": "unavailable",
            "source": "eez",
            "reason": readiness["reason"],
            "inside": None,
            "confidence": 0.0,
            "quality": "UNAVAILABLE",
            "database_url_configured": readiness["database_url_configured"],
        }

    def is_inside_mpa(self, *, latitude: float, longitude: float) -> dict[str, Any]:
        readiness = self.readiness_status()
        return {
            "status": "unavailable",
            "source": "mpa",
            "reason": readiness["reason"],
            "inside": None,
            "confidence": 0.0,
            "quality": "UNAVAILABLE",
            "database_url_configured": readiness["database_url_configured"],
        }

    def check_imbl_proximity(self, *, latitude: float, longitude: float) -> dict[str, Any]:
        readiness = self.readiness_status()
        return {
            "status": "unavailable",
            "source": "imbl",
            "reason": readiness["reason"],
            "distance_km": None,
            "confidence": 0.0,
            "quality": "UNAVAILABLE",
            "database_url_configured": readiness["database_url_configured"],
        }

    def analyze(
        self,
        *,
        latitude: float,
        longitude: float,
        request_id: str | None = None,
        target_time: datetime | None = None,
    ) -> dict[str, Any]:
        coordinate_valid = self.validate_coordinates(latitude, longitude)
        eez_status = self.is_inside_eez(latitude=latitude, longitude=longitude)
        mpa_status = self.is_inside_mpa(latitude=latitude, longitude=longitude)
        imbl_status = self.check_imbl_proximity(latitude=latitude, longitude=longitude)

        return {
            "status": "available" if coordinate_valid else "unavailable",
            "coordinate_valid": coordinate_valid,
            "latitude": latitude,
            "longitude": longitude,
            "eez": eez_status,
            "mpa": mpa_status,
            "imbl": imbl_status,
            "source": "geospatial",
            "quality": "HIGH" if coordinate_valid else "UNAVAILABLE",
            "confidence": 0.8 if coordinate_valid else 0.0,
            "target_time": target_time.isoformat() if target_time else None,
        }
