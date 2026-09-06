from __future__ import annotations

"""
ORCA location resolver.

Converts a human place name into coordinates using the public Open-Meteo
Geocoding API. This is deliberately separate from the weather/marine tools:
location resolution is request preprocessing, not a marine evidence source.

No ORCA demo location is hardcoded here.
"""

from datetime import datetime, timezone
from typing import Any

import httpx


OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


class GeocodingError(RuntimeError):
    """Raised when a requested place cannot be resolved reliably."""


class GeocodingTool:
    def __init__(
        self,
        *,
        url: str = OPEN_METEO_GEOCODING_URL,
        timeout: float = 10.0,
    ) -> None:
        self.url = url
        self.timeout = timeout

    async def resolve(self, name: str) -> dict[str, Any]:
        query = (name or "").strip()
        if not query:
            raise GeocodingError("location_name_missing")

        params = {
            "name": query,
            "count": 10,
            "language": "en",
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise GeocodingError(
                f"location_geocoding_request_failed: {exc}"
            ) from exc

        results = payload.get("results") or []
        if not isinstance(results, list) or not results:
            raise GeocodingError(
                f"location_not_found: {query}"
            )

        # Prefer an exact place-name match, then an Indian result.
        normalized = query.casefold()
        exact = [
            item for item in results
            if str(item.get("name", "")).casefold() == normalized
        ]
        indian = [
            item for item in results
            if str(item.get("country_code", "")).upper() == "IN"
        ]

        selected = (exact or indian or results)[0]
        latitude = selected.get("latitude")
        longitude = selected.get("longitude")

        if not isinstance(latitude, (int, float)) or not isinstance(
            longitude, (int, float)
        ):
            raise GeocodingError(
                f"location_coordinates_missing: {query}"
            )

        now = datetime.now(timezone.utc).isoformat()

        return {
            "status": "available",
            "source": "Open-Meteo Geocoding API",
            "timestamp": now,
            "query": query,
            "name": selected.get("name") or query,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "country": selected.get("country"),
            "country_code": selected.get("country_code"),
            "admin1": selected.get("admin1"),
            "admin2": selected.get("admin2"),
            "timezone": selected.get("timezone"),
            "confidence": 0.95 if exact else 0.90,
            "quality": "GOOD",
        }


__all__ = ["GeocodingTool", "GeocodingError"]
