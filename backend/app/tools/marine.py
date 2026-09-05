from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.tools.base import BaseTool, ToolResult


class MarineDataTool(BaseTool):
    """Determistic marine data interface for the demo. Live upstreams are optional and intentionally guarded."""

    def __init__(self) -> None:
        super().__init__("marine")

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
                "source": "marine",
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
            source="marine",
            status="unavailable",
            timestamp=target_time,
            fetch_timestamp=self.now_utc(),
            location={"lat": latitude, "lon": longitude},
            variables={},
            units={},
            quality={"level": "UNAVAILABLE"},
            confidence=0.0,
            reason="no_live_marine_source_configured",
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
