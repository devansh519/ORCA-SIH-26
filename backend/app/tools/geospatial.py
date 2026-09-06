from __future__ import annotations

"""ORCA geospatial tool with repository-root .env loading and Supabase PostGIS support."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

# Always resolve the repository root from this file, rather than relying on cwd.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPOSITORY_ROOT / ".env"
load_dotenv(ENV_FILE, override=True)
load_dotenv(override=True)


class GeospatialTool:
    source_name = "Marine Regions World EEZ v12"

    @staticmethod
    def validate_coordinates(latitude: float, longitude: float) -> bool:
        try:
            return -90.0 <= float(latitude) <= 90.0 and -180.0 <= float(longitude) <= 180.0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def calculate_freshness(age_seconds: float) -> str:
        if age_seconds <= 300:
            return "FRESH"
        if age_seconds <= 900:
            return "STALE"
        return "EXPIRED"

    def _database_url(self) -> str | None:
        # Reload the repository-root .env at call time as a final guard against
        # the tool being imported from a process with an empty/stale variable.
        load_dotenv(ENV_FILE, override=False)
        value = os.getenv("DATABASE_URL")
        return value.strip() if value else None

    def _table(self) -> str:
        return os.getenv("POSTGIS_EEZ_TABLE", "gis.eez_boundaries")

    def _geom_column(self) -> str:
        return os.getenv("POSTGIS_EEZ_GEOM_COLUMN", "geom")

    @staticmethod
    def _safe_identifier(value: str) -> str:
        parts = value.split(".")
        if not parts or any(not p or not p.replace("_", "").isalnum() for p in parts):
            raise ValueError(f"Unsafe SQL identifier: {value}")
        return ".".join(parts)

    async def _connect(self):
        url = self._database_url()
        if not url:
            raise RuntimeError("database_url_missing")
        return await asyncpg.connect(url)

    async def readiness_status(self) -> dict[str, Any]:
        if not self._database_url():
            return {"status": "unavailable", "reason": "database_url_missing"}
        conn = None
        try:
            conn = await self._connect()
            await conn.fetchval("SELECT gis.postgis_version()")
            table = self._safe_identifier(self._table())
            geom = self._safe_identifier(self._geom_column())
            exists = await conn.fetchval("SELECT to_regclass($1)", table)
            if exists is None:
                return {"status": "unavailable", "reason": "eez_table_missing", "table": table}
            await conn.fetchval(f"SELECT {geom} FROM {table} LIMIT 1")
            return {"status": "available", "table": table, "geometry_column": geom}
        except Exception as exc:
            return {"status": "unavailable", "reason": "geospatial_query_failed", "detail": str(exc)}
        finally:
            if conn is not None:
                await conn.close()

    async def is_inside_eez(self, *, latitude: float, longitude: float) -> dict[str, Any]:
        if not self.validate_coordinates(latitude, longitude):
            return {"status": "unavailable", "source": self.source_name, "reason": "invalid_coordinates", "inside": None, "distance_km": None, "confidence": 0.0, "quality": "UNAVAILABLE"}
        conn = None
        try:
            conn = await self._connect()
            table = self._safe_identifier(self._table())
            geom = self._safe_identifier(self._geom_column())
            row = await conn.fetchrow(
                f"""
                SELECT
                    gis.ST_Covers({geom}, gis.ST_SetSRID(gis.ST_MakePoint($1, $2), 4326)) AS inside,
                    gis.ST_Distance(
                        {geom}::gis.geography,
                        gis.ST_SetSRID(gis.ST_MakePoint($1, $2), 4326)::gis.geography
                    ) / 1000.0 AS distance_km
                FROM {table}
                ORDER BY gis.ST_Distance(
                    {geom}::gis.geography,
                    gis.ST_SetSRID(gis.ST_MakePoint($1, $2), 4326)::gis.geography
                )
                LIMIT 1
                """, longitude, latitude
            )
            return {
                "status": "available",
                "source": self.source_name,
                "inside": bool(row["inside"]),
                "distance_km": float(row["distance_km"]) if row["distance_km"] is not None else None,
                "confidence": 1.0,
                "quality": "GOOD",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"status": "unavailable", "source": self.source_name, "reason": "geospatial_query_failed", "detail": str(exc), "inside": None, "distance_km": None, "confidence": 0.0, "quality": "UNAVAILABLE"}
        finally:
            if conn is not None:
                await conn.close()

    async def check_route(self, route: list[tuple[float, float]] | list[list[float]]) -> dict[str, Any]:
        """Check whether a route intersects the configured EEZ polygons.

        Route coordinates are supplied as (latitude, longitude) pairs.
        The calculation is performed by PostGIS against the real EEZ table.
        """
        if not route or len(route) < 2:
            return {
                "status": "unavailable",
                "source": self.source_name,
                "reason": "route_requires_at_least_two_points",
                "intersects_eez": None,
                "distance_km": None,
                "confidence": 0.0,
                "quality": "UNAVAILABLE",
            }

        points: list[tuple[float, float]] = []
        for point in route:
            if len(point) != 2:
                return {
                    "status": "unavailable",
                    "source": self.source_name,
                    "reason": "invalid_route_point",
                    "intersects_eez": None,
                    "distance_km": None,
                    "confidence": 0.0,
                    "quality": "UNAVAILABLE",
                }
            latitude, longitude = float(point[0]), float(point[1])
            if not self.validate_coordinates(latitude, longitude):
                return {
                    "status": "unavailable",
                    "source": self.source_name,
                    "reason": "invalid_route_coordinates",
                    "intersects_eez": None,
                    "distance_km": None,
                    "confidence": 0.0,
                    "quality": "UNAVAILABLE",
                }
            points.append((latitude, longitude))

        # Build WKT from validated numeric coordinates. WKT uses longitude latitude.
        wkt = "LINESTRING(" + ", ".join(
            f"{longitude:.12f} {latitude:.12f}" for latitude, longitude in points
        ) + ")"

        conn = None
        try:
            conn = await self._connect()
            table = self._safe_identifier(self._table())
            geom = self._safe_identifier(self._geom_column())
            row = await conn.fetchrow(
                f"""
                SELECT
                    EXISTS (
                        SELECT 1
                        FROM {table}
                        WHERE gis.ST_Intersects(
                            {geom},
                            gis.ST_GeomFromText($1, 4326)
                        )
                    ) AS intersects_eez,
                    MIN(
                        gis.ST_Distance(
                            {geom}::gis.geography,
                            gis.ST_GeomFromText($1, 4326)::gis.geography
                        )
                    ) / 1000.0 AS distance_km
                FROM {table}
                """,
                wkt,
            )
            return {
                "status": "available",
                "source": self.source_name,
                "intersects_eez": bool(row["intersects_eez"]),
                "distance_km": float(row["distance_km"]) if row["distance_km"] is not None else None,
                "route_points": len(points),
                "confidence": 1.0,
                "quality": "GOOD",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "source": self.source_name,
                "reason": "geospatial_route_query_failed",
                "detail": str(exc),
                "intersects_eez": None,
                "distance_km": None,
                "route_points": len(points),
                "confidence": 0.0,
                "quality": "UNAVAILABLE",
            }
        finally:
            if conn is not None:
                await conn.close()

    async def analyze(self, *, latitude: float, longitude: float, **_: Any) -> dict[str, Any]:
        eez = await self.is_inside_eez(latitude=latitude, longitude=longitude)
        return {"status": eez["status"], "coordinate_valid": self.validate_coordinates(latitude, longitude), "eez": eez, "mpa": {"status": "unavailable", "reason": "mpa_dataset_not_configured"}, "imbl": {"status": "unavailable", "reason": "imbl_dataset_not_configured"}}

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        return await self.analyze(**kwargs)
