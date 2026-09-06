from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from app.tools.base import BaseTool, ToolResult


OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"


class MarineProvider(Protocol):
    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        ...


class UnavailableMarineProvider:
    """Safe fallback when no live marine provider is configured."""

    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "source": "Open-Meteo Marine API",
            "status": "unavailable",
            "timestamp": target_time.isoformat(),
            "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {"lat": latitude, "lon": longitude},
            "variables": {},
            "units": {},
            "quality": {"level": "UNAVAILABLE"},
            "confidence": 0.0,
            "reason": "no_live_marine_source_configured",
            "freshness": "UNKNOWN",
        }


class OpenMeteoMarineProvider:
    """Open-Meteo Marine API adapter."""

    def __init__(
        self,
        *,
        url: str = OPEN_METEO_MARINE_URL,
        timeout: float = 15.0,
    ) -> None:
        self.url = url
        self.timeout = timeout

    @staticmethod
    def _nearest_index(times: list[str], target_time: datetime) -> int:
        if not times:
            raise ValueError("open_meteo_marine_no_times")

        target = target_time.astimezone(timezone.utc).replace(
            minute=0,
            second=0,
            microsecond=0,
        )

        parsed = [
            datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
            for value in times
        ]

        return min(
            range(len(parsed)),
            key=lambda index: abs((parsed[index] - target).total_seconds()),
        )

    @staticmethod
    def _value(values: list[Any], index: int) -> Any:
        return values[index] if index < len(values) else None

    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(
                [
                    "wave_height",
                    "wave_direction",
                    "wave_period",
                    "wind_wave_height",
                    "wind_wave_direction",
                    "wind_wave_period",
                    "swell_wave_height",
                    "swell_wave_direction",
                    "swell_wave_period",
                    "sea_surface_temperature",
                    "ocean_current_velocity",
                    "ocean_current_direction",
                ]
            ),
            "forecast_days": 3,
            "timezone": "UTC",
            "length_unit": "metric",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.url, params=params)
                response.raise_for_status()
                payload = response.json()

            hourly = payload.get("hourly")
            if not isinstance(hourly, dict):
                raise ValueError("open_meteo_marine_hourly_missing")

            times = hourly.get("time")
            if not isinstance(times, list):
                raise ValueError("open_meteo_marine_times_missing")

            index = self._nearest_index(times, target_time)
            selected_time = str(times[index])

            variables = {
                "wave_height_m": self._value(
                    hourly.get("wave_height", []), index
                ),
                "wave_direction_deg": self._value(
                    hourly.get("wave_direction", []), index
                ),
                "wave_period_s": self._value(
                    hourly.get("wave_period", []), index
                ),
                "wind_wave_height_m": self._value(
                    hourly.get("wind_wave_height", []), index
                ),
                "wind_wave_direction_deg": self._value(
                    hourly.get("wind_wave_direction", []), index
                ),
                "wind_wave_period_s": self._value(
                    hourly.get("wind_wave_period", []), index
                ),
                "swell_wave_height_m": self._value(
                    hourly.get("swell_wave_height", []), index
                ),
                "swell_wave_direction_deg": self._value(
                    hourly.get("swell_wave_direction", []), index
                ),
                "swell_wave_period_s": self._value(
                    hourly.get("swell_wave_period", []), index
                ),
                "sst_c": self._value(
                    hourly.get("sea_surface_temperature", []), index
                ),
                "ocean_current_velocity_kmh": self._value(
                    hourly.get("ocean_current_velocity", []), index
                ),
                "ocean_current_direction_deg": self._value(
                    hourly.get("ocean_current_direction", []), index
                ),
            }

            variables = {
                key: value
                for key, value in variables.items()
                if value is not None
            }

            return {
                "source": "Open-Meteo Marine API",
                "status": "available",
                "timestamp": selected_time,
                "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
                "location": {"lat": latitude, "lon": longitude},
                "variables": variables,
                "units": {
                    "wave_height_m": "m",
                    "wave_direction_deg": "°",
                    "wave_period_s": "s",
                    "wind_wave_height_m": "m",
                    "wind_wave_direction_deg": "°",
                    "wind_wave_period_s": "s",
                    "swell_wave_height_m": "m",
                    "swell_wave_direction_deg": "°",
                    "swell_wave_period_s": "s",
                    "sst_c": "°C",
                    "ocean_current_velocity_kmh": "km/h",
                    "ocean_current_direction_deg": "°",
                },
                "quality": {"level": "GOOD"},
                "confidence": 0.85,
                "reason": "open_meteo_marine_forecast",
                "freshness": "FORECAST",
            }

        except Exception as exc:
            return {
                "source": "Open-Meteo Marine API",
                "status": "unavailable",
                "timestamp": target_time.isoformat(),
                "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
                "location": {"lat": latitude, "lon": longitude},
                "variables": {},
                "units": {},
                "quality": {"level": "UNAVAILABLE"},
                "confidence": 0.0,
                "reason": "marine_provider_request_failed",
                "detail": str(exc),
                "freshness": "UNKNOWN",
            }


class MarineDataTool(BaseTool):
    """ORCA marine-data tool with Open-Meteo as the Tier-1 live provider."""

    def __init__(
        self,
        provider: MarineProvider | None = None,
    ) -> None:
        super().__init__("marine")
        self.provider = provider or self._build_provider()

    @staticmethod
    def _build_provider() -> MarineProvider:
        provider_name = os.getenv(
            "MARINE_PROVIDER",
            "unavailable",
        ).strip().lower()

        if provider_name == "open_meteo":
            return OpenMeteoMarineProvider(
                url=os.getenv(
                    "OPEN_METEO_MARINE_URL",
                    OPEN_METEO_MARINE_URL,
                )
            )

        return UnavailableMarineProvider()

    @staticmethod
    def _validate_coordinates(
        latitude: float,
        longitude: float,
    ) -> bool:
        return (
            isinstance(latitude, (int, float))
            and isinstance(longitude, (int, float))
            and -90.0 <= latitude <= 90.0
            and -180.0 <= longitude <= 180.0
        )

    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        started = self.now_utc()
        result_data: dict[str, Any] | None = None

        if not self._validate_coordinates(latitude, longitude):
            return ToolResult(
                source="marine",
                status="unavailable",
                timestamp=target_time,
                fetch_timestamp=self.now_utc(),
                location={"lat": latitude, "lon": longitude},
                variables={},
                units={},
                quality={"level": "UNAVAILABLE"},
                confidence=0.0,
                reason="invalid_coordinates",
                freshness="UNKNOWN",
            ).to_dict()

        try:
            result_data = await self.provider.fetch(
                latitude=latitude,
                longitude=longitude,
                target_time=target_time,
                request_id=request_id,
            )

            if not isinstance(result_data, dict):
                raise ValueError("marine_provider_result_must_be_object")

            result_data.setdefault("source", "marine")
            result_data.setdefault("status", "unavailable")
            result_data.setdefault("timestamp", target_time.isoformat())
            result_data.setdefault(
                "fetch_timestamp",
                self.now_utc().isoformat(),
            )
            result_data.setdefault(
                "location",
                {"lat": latitude, "lon": longitude},
            )
            result_data.setdefault("variables", {})
            result_data.setdefault("units", {})
            result_data.setdefault("quality", {"level": "UNKNOWN"})
            result_data.setdefault("confidence", 0.0)
            result_data.setdefault("freshness", "UNKNOWN")

            return result_data

        except Exception as exc:
            result_data = ToolResult(
                source="marine",
                status="unavailable",
                timestamp=target_time,
                fetch_timestamp=self.now_utc(),
                location={"lat": latitude, "lon": longitude},
                variables={},
                units={},
                quality={"level": "UNAVAILABLE"},
                confidence=0.0,
                reason="marine_tool_execution_failed",
                freshness="UNKNOWN",
            ).to_dict()
            result_data["detail"] = str(exc)
            return result_data

        finally:
            duration_ms = int(
                (self.now_utc() - started).total_seconds() * 1000
            )
            self.log_call(
                request_id=request_id,
                latitude=latitude,
                longitude=longitude,
                target_time=target_time,
                duration_ms=duration_ms,
                status=(
                    result_data.get("status", "unavailable")
                    if isinstance(result_data, dict)
                    else "unavailable"
                ),
            )

    async def get_conditions(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        target_time = target_time or self.now_utc()
        return await self.fetch(
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            request_id=request_id,
        )

    async def execute(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.get_conditions(
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            request_id=request_id,
        )
