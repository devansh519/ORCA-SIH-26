from __future__ import annotations

from datetime import datetime
from typing import Any

from app.tools.base import BaseTool, ToolResult


class WeatherTool(BaseTool):
    """Weather and alert interface for the demo. No fabricated hazards or forecast values."""

    def __init__(self) -> None:
        super().__init__("weather")

    def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return {
                "source": "weather",
                "status": "unavailable",
                "reason": "invalid_coordinates",
                "timestamp": target_time.isoformat(),
                "fetch_timestamp": self.now_utc().isoformat(),
                "location": {"lat": latitude, "lon": longitude},
                "variables": {},
                "units": {},
                "quality": {"level": "UNAVAILABLE"},
                "confidence": 0.0,
                "freshness": "UNKNOWN",
            }

        result = ToolResult(
            source="weather",
            status="unavailable",
            timestamp=target_time,
            fetch_timestamp=self.now_utc(),
            location={"lat": latitude, "lon": longitude},
            variables={},
            units={},
            quality={"level": "UNAVAILABLE"},
            confidence=0.0,
            reason="no_live_weather_source_configured",
            freshness="UNKNOWN",
        )

        self.log_call(
            request_id=request_id,
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            duration_ms=0,
            status=result.status,
        )

        return result.to_dict()
