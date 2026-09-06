from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from app.tools.base import BaseTool, ToolResult


class WeatherProvider(Protocol):
    """Provider interface for weather observations and alerts."""

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
    """Safe fallback when no live weather source is configured.

    No wind, rainfall, cyclone, lightning, wave, or hazard values are
    fabricated by this provider.
    """

    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "source": "IMD/SACHET",
            "status": "unavailable",
            "timestamp": target_time.isoformat(),
            "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {
                "lat": latitude,
                "lon": longitude,
            },
            "variables": {},
            "units": {},
            "quality": {
                "level": "UNAVAILABLE",
            },
            "confidence": 0.0,
            "reason": "no_live_weather_source_configured",
            "freshness": "UNKNOWN",
            "alerts": [],
        }


class HttpWeatherProvider:
    """Generic HTTP weather-provider adapter.

    Configure a real upstream endpoint with WEATHER_API_URL.

    Optional:
        WEATHER_API_URL
        WEATHER_API_KEY

    The response should be a JSON object. The adapter preserves the upstream
    source, variables, units, quality, confidence, and alerts when supplied.
    """

    def __init__(
        self,
        *,
        url: str,
        api_key: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.timeout = timeout

    async def fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        target_time: datetime,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": target_time.isoformat(),
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.url,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()

            if not isinstance(payload, dict):
                raise ValueError("weather_provider_response_must_be_object")

            variables = payload.get("variables", payload)

            if not isinstance(variables, dict):
                raise ValueError("weather_variables_must_be_object")

            alerts = payload.get("alerts", [])
            if not isinstance(alerts, list):
                raise ValueError("weather_alerts_must_be_list")

            return {
                "source": payload.get("source", self.url),
                "status": "available",
                "timestamp": payload.get(
                    "timestamp",
                    target_time.isoformat(),
                ),
                "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
                "location": payload.get(
                    "location",
                    {
                        "lat": latitude,
                        "lon": longitude,
                    },
                ),
                "variables": variables,
                "units": payload.get("units", {}),
                "quality": payload.get(
                    "quality",
                    {
                        "level": "UPSTREAM",
                    },
                ),
                "confidence": float(
                    payload.get("confidence", 0.8)
                ),
                "reason": payload.get("reason"),
                "freshness": payload.get("freshness", "UNKNOWN"),
                "alerts": alerts,
            }

        except Exception as exc:
            return {
                "source": self.url,
                "status": "unavailable",
                "timestamp": target_time.isoformat(),
                "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
                "location": {
                    "lat": latitude,
                    "lon": longitude,
                },
                "variables": {},
                "units": {},
                "quality": {
                    "level": "UNAVAILABLE",
                },
                "confidence": 0.0,
                "reason": "weather_provider_request_failed",
                "detail": str(exc),
                "freshness": "UNKNOWN",
                "alerts": [],
            }


class WeatherTool(BaseTool):
    """ORCA weather and hazard-data tool.

    Provider selection:

        WEATHER_PROVIDER=unavailable
            Safe default. No fabricated weather/hazard values.

        WEATHER_PROVIDER=http
            Uses WEATHER_API_URL through HttpWeatherProvider.

    This keeps the tool ready for a real IMD/SACHET integration without
    falsely claiming that an arbitrary endpoint is an official IMD source.
    """

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

        if provider_name == "http":
            url = os.getenv("WEATHER_API_URL")

            if not url:
                return UnavailableWeatherProvider()

            return HttpWeatherProvider(
                url=url,
                api_key=os.getenv("WEATHER_API_KEY"),
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
        """Fetch weather/hazard information through the configured provider."""
        started = self.now_utc()
        result_data: dict[str, Any] | None = None

        if not self.validate_coordinates(latitude, longitude):
            result = ToolResult(
                source="weather",
                status="unavailable",
                timestamp=target_time,
                fetch_timestamp=self.now_utc(),
                location={
                    "lat": latitude,
                    "lon": longitude,
                },
                variables={},
                units={},
                quality={
                    "level": "UNAVAILABLE",
                },
                confidence=0.0,
                reason="invalid_coordinates",
                freshness="UNKNOWN",
            ).to_dict()

            result["alerts"] = []
            return result

        try:
            result_data = await self.provider.fetch(
                latitude=latitude,
                longitude=longitude,
                target_time=target_time,
                request_id=request_id,
            )

            if not isinstance(result_data, dict):
                raise ValueError(
                    "weather_provider_result_must_be_object"
                )

            result_data.setdefault("source", "weather")
            result_data.setdefault("status", "unavailable")
            result_data.setdefault(
                "timestamp",
                target_time.isoformat(),
            )
            result_data.setdefault(
                "fetch_timestamp",
                self.now_utc().isoformat(),
            )
            result_data.setdefault(
                "location",
                {
                    "lat": latitude,
                    "lon": longitude,
                },
            )
            result_data.setdefault("variables", {})
            result_data.setdefault("units", {})
            result_data.setdefault(
                "quality",
                {
                    "level": "UNKNOWN",
                },
            )
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
                location={
                    "lat": latitude,
                    "lon": longitude,
                },
                variables={},
                units={},
                quality={
                    "level": "UNAVAILABLE",
                },
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
        """Convenience method for agents and graph nodes."""
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
        """Return the weather result with its structured alert list."""
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
        """Standard ORCA tool execution entry point."""
        return await self.get_conditions(
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            request_id=request_id,
        )
