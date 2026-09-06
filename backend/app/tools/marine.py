from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from app.tools.base import BaseTool, ToolResult


class MarineProvider(Protocol):
    """Provider interface for marine observations/forecasts."""

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
    """Explicit fallback when no live marine provider is configured.

    This provider never invents SST, chlorophyll, PFZ, wave, or other marine
    values. It returns a structured unavailable result instead.
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
            "source": "INCOIS/Copernicus",
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
            "reason": "no_live_marine_source_configured",
            "freshness": "UNKNOWN",
        }


class HttpMarineProvider:
    """Generic HTTP marine provider adapter.

    This adapter is intentionally provider-neutral. Configure a real upstream
    endpoint with MARINE_API_URL. The upstream response must be a JSON object
    containing marine variables.

    Optional:
        MARINE_API_URL
        MARINE_API_KEY

    The provider does not claim to be INCOIS or Copernicus; the configured
    endpoint is the actual source returned in the result.
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
                raise ValueError("marine_provider_response_must_be_object")

            variables = payload.get("variables", payload)

            if not isinstance(variables, dict):
                raise ValueError("marine_variables_must_be_object")

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
                "confidence": float(payload.get("confidence", 0.8)),
                "reason": payload.get("reason"),
                "freshness": payload.get("freshness", "UNKNOWN"),
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
                "reason": "marine_provider_request_failed",
                "detail": str(exc),
                "freshness": "UNKNOWN",
            }


class MarineDataTool(BaseTool):
    """ORCA marine-data tool with an explicit live-provider boundary.

    Provider selection:
        MARINE_PROVIDER=unavailable
            Safe default. No fabricated marine values.

        MARINE_PROVIDER=http
            Uses MARINE_API_URL through HttpMarineProvider.

    For the Tier-1 demo, this tool can therefore participate in orchestration
    without falsely claiming that INCOIS/Copernicus data is live.
    """

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

        if provider_name == "http":
            url = os.getenv("MARINE_API_URL")
            if not url:
                return UnavailableMarineProvider()

            return HttpMarineProvider(
                url=url,
                api_key=os.getenv("MARINE_API_KEY"),
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
        """Fetch marine data through the configured provider."""
        started = self.now_utc()

        if not self._validate_coordinates(latitude, longitude):
            result = ToolResult(
                source="marine",
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
            )

            return result.to_dict()

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

            return result_data

        except Exception as exc:
            result = ToolResult(
                source="marine",
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
                reason="marine_tool_execution_failed",
                freshness="UNKNOWN",
            ).to_dict()

            result["detail"] = str(exc)
            return result

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
                    if "result_data" in locals()
                    and isinstance(result_data, dict)
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
        """Convenience method used by agents/workflow nodes."""
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
        """Standard ORCA tool execution entry point."""
        return await self.get_conditions(
            latitude=latitude,
            longitude=longitude,
            target_time=target_time,
            request_id=request_id,
        )
