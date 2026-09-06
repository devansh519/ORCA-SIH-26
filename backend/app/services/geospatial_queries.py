from __future__ import annotations

"""
ORCA Geospatial Query Service

Supports:
1. Point -> inside/outside an EEZ
2. Point -> distance to nearest EEZ boundary
3. Route -> EEZ intersection
4. Route -> minimum distance to EEZ boundary
5. Natural-language geospatial questions
6. Structured answer with source + timestamp

Uses the real Supabase/PostGIS table:

    gis.eez_boundaries

Important:
- PostGIS functions are explicitly schema-qualified with `gis.`
- Coordinates are passed as double precision
- Geometry is EPSG:4326
- Distance calculations use EPSG:32644
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import asyncpg
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def _load_project_env() -> str | None:
    """
    Find the repository .env regardless of the current working directory.

    Expected layout:

        orca/
        ├── .env
        └── backend/
            └── app/
                └── services/
                    └── geospatial_queries.py
    """
    current = Path(__file__).resolve().parent

    for directory in [current, *current.parents]:
        candidate = directory / ".env"

        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return str(candidate)

    return None


_ENV_PATH = _load_project_env()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GeospatialQueryError(RuntimeError):
    """Raised for invalid input or unavailable geospatial infrastructure."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class GeospatialQueryService:
    """
    Real PostGIS-backed geospatial query service.
    """

    SOURCE = "Marine Regions World EEZ v12"
    TABLE = "gis.eez_boundaries"

    def __init__(self, database_url: str | None = None) -> None:
        if not database_url:
            _load_project_env()

        self.database_url = database_url or os.getenv("DATABASE_URL")

        if not self.database_url:
            raise GeospatialQueryError(
                "DATABASE_URL is not configured."
            )

    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------

    async def _connect(self) -> asyncpg.Connection:
        return await asyncpg.connect(self.database_url)

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    @staticmethod
    def _validate_point(
        point: Sequence[float],
    ) -> tuple[float, float]:
        """
        Validate a point represented as:

            (latitude, longitude)
        """

        if len(point) != 2:
            raise GeospatialQueryError(
                "Point must contain [latitude, longitude]."
            )

        lat = float(point[0])
        lon = float(point[1])

        if not -90.0 <= lat <= 90.0:
            raise GeospatialQueryError(
                f"Invalid latitude: {lat}"
            )

        if not -180.0 <= lon <= 180.0:
            raise GeospatialQueryError(
                f"Invalid longitude: {lon}"
            )

        return lat, lon

    @classmethod
    def _validate_route(
        cls,
        route: Iterable[Sequence[float]],
    ) -> list[tuple[float, float]]:
        points = [
            cls._validate_point(point)
            for point in route
        ]

        if len(points) < 2:
            raise GeospatialQueryError(
                "Route must contain at least 2 points."
            )

        return points

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _linestring_wkt(
        points: Sequence[tuple[float, float]],
    ) -> str:
        """
        PostGIS WKT uses:

            longitude latitude

        while our public API uses:

            latitude longitude
        """

        coords = ", ".join(
            f"{lon} {lat}"
            for lat, lon in points
        )

        return f"LINESTRING({coords})"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _base_response(
        cls,
        *,
        operation: str,
        timestamp: str,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        return {
            "status": "available",
            "operation": operation,
            "source": cls.SOURCE,
            "timestamp": timestamp,
            "confidence": confidence,
            "quality": "GOOD",
        }

    # -----------------------------------------------------------------------
    # Point analysis
    # -----------------------------------------------------------------------

    async def point_analysis(
        self,
        *,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:

        lat, lon = self._validate_point(
            (latitude, longitude)
        )

        timestamp = self._timestamp()

        """
        IMPORTANT:

        All PostGIS functions are explicitly qualified with `gis.` because
        this Supabase project exposes PostGIS functions in the gis schema.

        $1 = longitude
        $2 = latitude
        """

        sql = f"""
        WITH p AS (
            SELECT
                gis.ST_SetSRID(
                    gis.ST_MakePoint(
                        $1::double precision,
                        $2::double precision
                    ),
                    4326
                ) AS geom
        ),

        nearest AS (
            SELECT
                gis.ST_Distance(
                    e.geom::gis.geography,
                    p.geom::gis.geography
                ) / 1000.0 AS distance_km

            FROM {self.TABLE} AS e
            CROSS JOIN p

            ORDER BY
                gis.ST_Distance(
                    e.geom::gis.geography,
                    p.geom::gis.geography
                )

            LIMIT 1
        )

        SELECT

            EXISTS (
                SELECT 1

                FROM {self.TABLE} AS e
                CROSS JOIN p

                WHERE gis.ST_Covers(
                    e.geom,
                    p.geom
                )
            ) AS inside_eez,

            (
                SELECT distance_km
                FROM nearest
            ) AS distance_km;
        """

        conn = await self._connect()

        try:
            row = await conn.fetchrow(
                sql,
                lon,
                lat,
            )
        finally:
            await conn.close()

        if row is None:
            raise GeospatialQueryError(
                "No EEZ geometry is available."
            )

        result = self._base_response(
            operation="point_analysis",
            timestamp=timestamp,
        )

        result.update(
            {
                "location": {
                    "latitude": lat,
                    "longitude": lon,
                },
                "inside_eez": bool(
                    row["inside_eez"]
                ),
                "distance_to_nearest_eez_boundary_km": (
                    float(row["distance_km"])
                    if row["distance_km"] is not None
                    else None
                ),
            }
        )

        return result

    # -----------------------------------------------------------------------
    # Route analysis
    # -----------------------------------------------------------------------

    async def route_analysis(
        self,
        *,
        route: Iterable[Sequence[float]],
    ) -> dict[str, Any]:

        points = self._validate_route(route)

        timestamp = self._timestamp()

        route_wkt = self._linestring_wkt(
            points
        )

        sql = f"""
        WITH r AS (
            SELECT
                gis.ST_GeomFromText(
                    $1,
                    4326
                ) AS geom
        ),

        distances AS (
            SELECT
                MIN(
                    gis.ST_Distance(
                        e.geom::gis.geography,
                        r.geom::gis.geography
                    )
                ) / 1000.0 AS distance_km

            FROM {self.TABLE} AS e
            CROSS JOIN r
        )

        SELECT

            EXISTS (
                SELECT 1

                FROM {self.TABLE} AS e
                CROSS JOIN r

                WHERE gis.ST_Intersects(
                    e.geom,
                    r.geom
                )
            ) AS intersects_eez,

            (
                SELECT distance_km
                FROM distances
            ) AS minimum_distance_km;
        """
        conn = await self._connect()

        try:
            row = await conn.fetchrow(
                sql,
                route_wkt,
            )
        finally:
            await conn.close()

        if row is None:
            raise GeospatialQueryError(
                "No EEZ geometry is available."
            )

        result = self._base_response(
            operation="route_analysis",
            timestamp=timestamp,
        )

        result.update(
            {
                "route_points": len(points),

                "route": [
                    {
                        "latitude": lat,
                        "longitude": lon,
                    }
                    for lat, lon in points
                ],

                "intersects_eez": bool(
                    row["intersects_eez"]
                ),

                "minimum_distance_to_eez_boundary_km": (
                    float(row["minimum_distance_km"])
                    if row["minimum_distance_km"] is not None
                    else None
                ),
            }
        )

        return result

    # -----------------------------------------------------------------------
    # Coordinate extraction
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_points_from_text(
        text: str,
    ) -> list[tuple[float, float]]:
        """
        Accept coordinate pairs such as:

            9.2876, 79.3129

        or:

            (9.2876,79.3129)

        Returns:

            [(latitude, longitude)]
        """

        pattern = re.compile(
            r"(-?\d+(?:\.\d+)?)"
            r"\s*[,/]\s*"
            r"(-?\d+(?:\.\d+)?)"
        )

        matches = pattern.findall(text)

        return [
            (
                float(lat),
                float(lon),
            )
            for lat, lon in matches
        ]

    # -----------------------------------------------------------------------
    # Natural-language answer
    # -----------------------------------------------------------------------

    async def answer_question(
        self,
        *,
        question: str,
        latitude: float | None = None,
        longitude: float | None = None,
        route: Iterable[Sequence[float]] | None = None,
    ) -> dict[str, Any]:

        q = question.strip().lower()

        # ---------------------------------------------------------------
        # Route query
        # ---------------------------------------------------------------

        if route is not None:

            route_result = await self.route_analysis(
                route=route
            )

            return self._format_route_answer(
                question,
                route_result,
            )

        # ---------------------------------------------------------------
        # Point query
        # ---------------------------------------------------------------

        points: list[tuple[float, float]]

        if latitude is not None and longitude is not None:

            points = [
                (
                    float(latitude),
                    float(longitude),
                )
            ]

        else:

            points = self._extract_points_from_text(
                question
            )

        if not points:
            raise GeospatialQueryError(
                "A latitude/longitude or route is required "
                "for a geospatial question."
            )

        latitude, longitude = points[0]

        point_result = await self.point_analysis(
            latitude=latitude,
            longitude=longitude,
        )

        # ---------------------------------------------------------------
        # Distance question
        # ---------------------------------------------------------------

        if any(
            phrase in q
            for phrase in (
                "how far",
                "distance",
                "near the border",
                "near border",
                "close to border",
            )
        ):

            distance = (
                point_result[
                    "distance_to_nearest_eez_boundary_km"
                ]
            )

            if distance is not None:

                answer = (
                    f"You are approximately "
                    f"{distance:.2f} km from the nearest "
                    f"EEZ boundary."
                )

            else:

                answer = (
                    "The distance to the nearest EEZ "
                    "boundary is unavailable."
                )

            operation = "point_distance"

        # ---------------------------------------------------------------
        # Containment question
        # ---------------------------------------------------------------

        elif any(
            phrase in q
            for phrase in (
                "inside",
                "within",
                "in the eez",
                "am i in",
            )
        ):

            inside = point_result[
                "inside_eez"
            ]

            if inside:

                answer = (
                    "Your location is inside an EEZ."
                )

            else:

                answer = (
                    "Your location is outside the EEZ "
                    "polygons in the dataset."
                )

            operation = "point_containment"

        # ---------------------------------------------------------------
        # General point question
        # ---------------------------------------------------------------

        else:

            inside = point_result[
                "inside_eez"
            ]

            distance = point_result[
                "distance_to_nearest_eez_boundary_km"
            ]

            answer = (
                "Your location is "
                + (
                    "inside"
                    if inside
                    else "outside"
                )
                + " an EEZ"
            )

            if distance is not None:

                answer += (
                    f" and approximately "
                    f"{distance:.2f} km from the "
                    f"nearest EEZ boundary."
                )

            else:

                answer += "."

            operation = "point_analysis"

        return {
            "status": "available",
            "operation": operation,
            "question": question,
            "answer": answer,

            "location": point_result[
                "location"
            ],

            "inside_eez": point_result[
                "inside_eez"
            ],

            "distance_to_nearest_eez_boundary_km":
                point_result[
                    "distance_to_nearest_eez_boundary_km"
                ],

            "source": point_result[
                "source"
            ],

            "timestamp": point_result[
                "timestamp"
            ],

            "confidence": point_result[
                "confidence"
            ],

            "quality": point_result[
                "quality"
            ],
        }

    # -----------------------------------------------------------------------
    # Route response
    # -----------------------------------------------------------------------

    @staticmethod
    def _format_route_answer(
        question: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:

        intersects = result[
            "intersects_eez"
        ]

        distance = result[
            "minimum_distance_to_eez_boundary_km"
        ]

        if intersects:

            answer = (
                "The planned route intersects "
                "an EEZ boundary."
            )

        elif distance is not None:

            answer = (
                "The planned route does not intersect "
                "an EEZ boundary; its minimum distance "
                f"is approximately {distance:.2f} km."
            )

        else:

            answer = (
                "The route could not be compared "
                "with the EEZ geometry."
            )

        return {
            "status": result[
                "status"
            ],

            "operation": "route_intersection",

            "question": question,

            "answer": answer,

            "route_points": result[
                "route_points"
            ],

            "intersects_eez": intersects,

            "minimum_distance_to_eez_boundary_km":
                distance,

            "source": result[
                "source"
            ],

            "timestamp": result[
                "timestamp"
            ],

            "confidence": result[
                "confidence"
            ],

            "quality": result[
                "quality"
            ],
        }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

async def demo() -> None:
    """
    Smoke test against the real Supabase/PostGIS database.
    """

    service = GeospatialQueryService()

    # ---------------------------------------------------------------
    # Point test
    # ---------------------------------------------------------------

    point = await service.answer_question(
        question=(
            "How far am I from the international "
            "maritime border?"
        ),
        latitude=9.2876,
        longitude=79.3129,
    )

    print()
    print("========================================")
    print("        ORCA POINT QUERY")
    print("========================================")
    print(point)

    # ---------------------------------------------------------------
    # Route test
    # ---------------------------------------------------------------

    route = await service.answer_question(
        question=(
            "Does my route cross the "
            "maritime boundary?"
        ),
        route=[
            (9.2876, 79.3129),
            (9.29, 79.32),
            (9.30, 79.34),
        ],
    )

    print()
    print("========================================")
    print("        ORCA ROUTE QUERY")
    print("========================================")
    print(route)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    asyncio.run(demo())