from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.tools.geospatial import GeospatialTool
from app.tools.marine import MarineDataTool
from app.tools.weather import WeatherTool


class LiveContextService:
    """Temporary integration layer for fetching live tool context for the demo scenario."""

    def __init__(self) -> None:
        self.marine_tool = MarineDataTool()
        self.weather_tool = WeatherTool()
        self.geospatial_tool = GeospatialTool()

    async def fetch_context(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        marine_task = asyncio.to_thread(
            self.marine_tool.fetch,
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            request_id=request_id,
        )
        weather_task = asyncio.to_thread(
            self.weather_tool.fetch,
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            request_id=request_id,
        )
        geospatial_task = asyncio.to_thread(
            self.geospatial_tool.analyze,
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            request_id=request_id,
        )

        marine, weather, geospatial = await asyncio.gather(marine_task, weather_task, geospatial_task)

        return {
            "marine": marine,
            "weather": weather,
            "geospatial": geospatial,
            "sources": [
                marine.get("source"),
                weather.get("source"),
                geospatial.get("source"),
            ],
        }
