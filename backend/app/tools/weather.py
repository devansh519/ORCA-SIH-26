from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from app.tools.base import BaseTool, ToolResult


OPEN_METEO_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherProvider(Protocol):
    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        ...


class UnavailableWeatherProvider:
    """Safe fallback when no live weather source is configured."""

    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "source": "Open-Meteo",
            "status": "unavailable",
            "timestamp": target_time.isoformat(),
            "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {"lat": latitude, "lon": longitude},
            "variables": {},
            "units": {},
            "quality": {"level": "UNAVAILABLE"},
            "confidence": 0.0,
            "reason": "no_live_weather_source_configured",
            "freshness": "UNKNOWN",
            "alerts": [],
        }


class OpenMeteoWeatherProvider:
    """Open-Meteo forecast adapter.

    Open-Meteo's public forecast API does not require an API key for the
    standard non-commercial endpoint. It returns JSON weather forecasts.
    """

    def __init__(
        self,
        *,
        url: str = OPEN_METEO_WEATHER_URL,
        timeout: float = 15.0,
    ) -> None:
        self.url = url
        self.timeout = timeout

    @staticmethod
    def _nearest_index(times: list[str], target_time: datetime) -> int:
        if not times:
            raise ValueError("open_meteo_weather_no_times")

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
                    "temperature_2m",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "wind_gusts_10m",
                    "precipitation",
                    "rain",
                    "weather_code",
                    "cloud_cover",
                    "pressure_msl",
                ]
            ),
            "forecast_days": 3,
            "timezone": "UTC",
            "wind_speed_unit": "ms",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.url, params=params)
                response.raise_for_status()
                payload = response.json()

            hourly = payload.get("hourly")
            if not isinstance(hourly, dict):
                raise ValueError("open_meteo_weather_hourly_missing")

            times = hourly.get("time")
            if not isinstance(times, list):
                raise ValueError("open_meteo_weather_times_missing")

            index = self._nearest_index(times, target_time)
            selected_time = str(times[index])

            variables = {
                "temperature_c": self._value(
                    hourly.get("temperature_2m", []), index
                ),
                "wind_speed_ms": self._value(
                    hourly.get("wind_speed_10m", []), index
                ),
                "wind_direction_deg": self._value(
                    hourly.get("wind_direction_10m", []), index
                ),
                "wind_gusts_ms": self._value(
                    hourly.get("wind_gusts_10m", []), index
                ),
                "precipitation_mm": self._value(
                    hourly.get("precipitation", []), index
                ),
                "rain_mm": self._value(hourly.get("rain", []), index),
                "weather_code": self._value(
                    hourly.get("weather_code", []), index
                ),
                "cloud_cover_pct": self._value(
                    hourly.get("cloud_cover", []), index
                ),
                "pressure_msl_hpa": self._value(
                    hourly.get("pressure_msl", []), index
                ),
            }

            variables = {
                key: value
                for key, value in variables.items()
                if value is not None
            }

            return {
                "source": "Open-Meteo Weather API",
                "status": "available",
                "timestamp": selected_time,
                "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
                "location": {"lat": latitude, "lon": longitude},
                "variables": variables,
                "units": {
                    "temperature_c": "°C",
                    "wind_speed_ms": "m/s",
                    "wind_direction_deg": "°",
                    "wind_gusts_ms": "m/s",
                    "precipitation_mm": "mm",
                    "rain_mm": "mm",
                    "weather_code": "WMO code",
                    "cloud_cover_pct": "%",
                    "pressure_msl_hpa": "hPa",
                },
                "quality": {"level": "GOOD"},
                "confidence": 0.85,
                "reason": "open_meteo_forecast",
                "freshness": "FORECAST",
                "alerts": [],
            }

        except Exception as exc:
            return {
                "source": "Open-Meteo Weather API",
                "status": "unavailable",
                "timestamp": target_time.isoformat(),
                "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
                "location": {"lat": latitude, "lon": longitude},
                "variables": {},
                "units": {},
                "quality": {"level": "UNAVAILABLE"},
                "confidence": 0.0,
                "reason": "weather_provider_request_failed",
                "detail": str(exc),
                "freshness": "UNKNOWN",
                "alerts": [],
            }


class WeatherTool(BaseTool):
    """ORCA weather tool with Open-Meteo as the Tier-1 live provider."""

    def __init__(
        self,
        provider: WeatherProvider | None = None,
    ) -> None:
        super().__init__("weather")
        self.provider = provider or self._build_provider()

    @staticmethod
    def _build_provider() -> WeatherProvider:
        provider_name = os.getenv(
            "WEATHER_PROVIDER",
            "unavailable",
        ).strip().lower()

        if provider_name == "open_meteo":
            return OpenMeteoWeatherProvider(
                url=os.getenv(
                    "OPEN_METEO_WEATHER_URL",
                    OPEN_METEO_WEATHER_URL,
                )
            )

        return UnavailableWeatherProvider()

    @staticmethod
    def validate_coordinates(
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

        if not self.validate_coordinates(latitude, longitude):
            return ToolResult(
                source="weather",
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
                raise ValueError("weather_provider_result_must_be_object")

            result_data.setdefault("source", "weather")
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
            result_data.setdefault("alerts", [])

            if not isinstance(result_data["alerts"], list):
                raise ValueError("weather_alerts_must_be_list")

            return result_data

        except Exception as exc:
            result_data = ToolResult(
                source="weather",
                status="unavailable",
                timestamp=target_time,
                fetch_timestamp=self.now_utc(),
                location={"lat": latitude, "lon": longitude},
                variables={},
                units={},
                quality={"level": "UNAVAILABLE"},
                confidence=0.0,
                reason="weather_tool_execution_failed",
                freshness="UNKNOWN",
            ).to_dict()
            result_data["alerts"] = []
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
        target_time = target_time or datetime.now(timezone.utc)
        return await self.fetch(
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            request_id=request_id,
        )

    async def get_alerts(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        result = await self.get_conditions(
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            request_id=request_id,
        )
        return {
            "status": result.get("status", "unavailable"),
            "source": result.get("source", "weather"),
            "timestamp": result.get("timestamp"),
            "location": result.get("location"),
            "alerts": result.get("alerts", []),
            "confidence": result.get("confidence", 0.0),
            "quality": result.get("quality", {}),
            "reason": result.get("reason"),
        }

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
