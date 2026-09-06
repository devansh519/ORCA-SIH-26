from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import asyncpg

from app.schemas.alerts import AlertSeverity
from app.tools.geospatial import GeospatialTool


class GeofenceAlertService:
    """Checks persistent frequent zones against the live PostGIS EEZ geofence."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        self.geospatial = GeospatialTool()

    async def _connect(self) -> asyncpg.Connection:
        return await asyncpg.connect(self.database_url)

    async def list_zones(self, user_id: str | None = None) -> list[dict[str, Any]]:
        conn = await self._connect()
        try:
            if user_id:
                rows = await conn.fetch(
                    """
                    SELECT id::text, user_id, name, latitude, longitude,
                           alert_radius_km, language, active
                    FROM public.frequent_zones
                    WHERE active = TRUE AND user_id = $1
                    ORDER BY created_at
                    """,
                    user_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id::text, user_id, name, latitude, longitude,
                           alert_radius_km, language, active
                    FROM public.frequent_zones
                    WHERE active = TRUE
                    ORDER BY created_at
                    """
                )
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    @staticmethod
    def _severity(
        distance_km: float | None,
        inside: bool | None,
    ) -> AlertSeverity | None:
        if inside is True:
            return AlertSeverity.RED
        if distance_km is None:
            return None
        if distance_km <= 0.5:
            return AlertSeverity.RED
        if distance_km <= 1.0:
            return AlertSeverity.AMBER
        return None

    @staticmethod
    def _messages(
        language: str,
        severity: AlertSeverity,
        distance_km: float | None,
        inside: bool | None,
    ) -> tuple[str, str]:
        distance = (
            f"{distance_km:.2f} km"
            if distance_km is not None
            else "the boundary"
        )

        if language.lower().startswith("ta"):
            if inside:
                return (
                    "கடல் எல்லை எச்சரிக்கை",
                    "எச்சரிக்கை: நீங்கள் EEZ எல்லைக்குள் உள்ளீர்கள். கடல் எல்லை தொடர்பான விதிமுறைகளை சரிபார்க்கவும்.",
                )
            if severity == AlertSeverity.RED:
                return (
                    "கடல் எல்லைக்கு மிக அருகில்",
                    f"சிவப்பு எச்சரிக்கை: நீங்கள் EEZ எல்லையிலிருந்து சுமார் {distance} தொலைவில் உள்ளீர்கள்.",
                )
            return (
                "கடல் எல்லை அருகாமை எச்சரிக்கை",
                f"ஆம்பர் எச்சரிக்கை: நீங்கள் EEZ எல்லையிலிருந்து சுமார் {distance} தொலைவில் உள்ளீர்கள்.",
            )

        if inside:
            return (
                "EEZ Boundary Alert",
                "RED ALERT: The monitored zone is inside the EEZ boundary. Check applicable maritime rules before proceeding.",
            )
        if severity == AlertSeverity.RED:
            return (
                "Very Close to EEZ Boundary",
                f"RED ALERT: The monitored zone is approximately {distance} from the EEZ boundary.",
            )
        return (
            "Near EEZ Boundary",
            f"AMBER ALERT: The monitored zone is approximately {distance} from the EEZ boundary.",
        )

    @staticmethod
    def _to_datetime(value: Any) -> datetime | None:
        """
        Convert the geospatial tool's ISO timestamp into a real datetime.

        asyncpg cannot bind an ISO string to a PostgreSQL timestamptz parameter;
        it requires datetime/date objects.
        """
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed

        raise TypeError(
            f"Unsupported timestamp type: {type(value).__name__}"
        )

    async def check_zone(
        self,
        zone: dict[str, Any],
        force: bool = False,
    ) -> dict[str, Any]:
        result = await self.geospatial.is_inside_eez(
            latitude=float(zone["latitude"]),
            longitude=float(zone["longitude"]),
        )

        if result.get("status") != "available":
            return {
                "status": "error",
                "zone_id": str(zone["id"]),
                "error": result.get(
                    "error",
                    "Geospatial data unavailable",
                ),
                "geospatial": result,
            }

        distance_km = result.get("distance_km")
        inside = result.get("inside")
        severity = self._severity(distance_km, inside)

        # Respect the zone's configured proximity radius.
        if (
            severity is not None
            and not inside
            and distance_km is not None
            and float(distance_km) > float(zone["alert_radius_km"])
        ):
            severity = None

        if severity is None:
            return {
                "status": "no_alert",
                "zone_id": str(zone["id"]),
                "geospatial": result,
            }

        conn = await self._connect()
        try:
            if not force:
                recent = await conn.fetchval(
                    """
                    SELECT id::text
                    FROM public.proactive_alerts
                    WHERE zone_id = $1::uuid
                      AND alert_type = 'EEZ_GEOFENCE'
                      AND created_at >= NOW() - INTERVAL '6 hours'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    str(zone["id"]),
                )

                if recent:
                    return {
                        "status": "deduplicated",
                        "zone_id": str(zone["id"]),
                        "existing_alert_id": recent,
                        "geospatial": result,
                    }

            title, message = self._messages(
                zone.get("language", "ta"),
                severity,
                distance_km,
                inside,
            )

            source_timestamp = self._to_datetime(
                result.get("timestamp")
            )

            alert_id = await conn.fetchval(
                """
                INSERT INTO public.proactive_alerts (
                    zone_id,
                    user_id,
                    alert_type,
                    severity,
                    title,
                    message,
                    boundary_distance_km,
                    inside_eez,
                    source,
                    source_timestamp,
                    delivery_status
                )
                VALUES (
                    $1::uuid,
                    $2,
                    'EEZ_GEOFENCE',
                    $3,
                    $4,
                    $5,
                    $6,
                    $7,
                    $8,
                    $9,
                    'created'
                )
                RETURNING id::text
                """,
                str(zone["id"]),
                zone["user_id"],
                severity.value,
                title,
                message,
                distance_km,
                inside,
                result.get(
                    "source",
                    "Marine Regions World EEZ v12",
                ),
                source_timestamp,
            )

            return {
                "status": "alert_created",
                "alert_id": alert_id,
                "zone_id": str(zone["id"]),
                "severity": severity.value,
                "title": title,
                "message": message,
                "delivery_status": "created",
                "geospatial": result,
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }
        finally:
            await conn.close()

    async def check_all(
        self,
        user_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        zones = await self.list_zones(user_id)
        results = []

        for zone in zones:
            results.append(
                await self.check_zone(
                    zone,
                    force=force,
                )
            )

        return {
            "status": "completed",
            "checked_zones": len(zones),
            "alerts_created": sum(
                result["status"] == "alert_created"
                for result in results
            ),
            "results": results,
            "checked_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    async def active_alerts(
        self,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = await self._connect()
        try:
            if user_id:
                rows = await conn.fetch(
                    """
                    SELECT id::text,
                           zone_id::text,
                           user_id,
                           alert_type,
                           severity,
                           title,
                           message,
                           boundary_distance_km,
                           inside_eez,
                           source,
                           source_timestamp,
                           created_at,
                           delivery_status
                    FROM public.proactive_alerts
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT 50
                    """,
                    user_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id::text,
                           zone_id::text,
                           user_id,
                           alert_type,
                           severity,
                           title,
                           message,
                           boundary_distance_km,
                           inside_eez,
                           source,
                           source_timestamp,
                           created_at,
                           delivery_status
                    FROM public.proactive_alerts
                    ORDER BY created_at DESC
                    LIMIT 50
                    """
                )

            return [dict(row) for row in rows]
        finally:
            await conn.close()
