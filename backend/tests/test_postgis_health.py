from __future__ import annotations

import asyncio
import os

import asyncpg
from dotenv import load_dotenv


LATITUDE = 9.2876
LONGITUDE = 79.3129


async def main() -> None:
    load_dotenv("../.env")

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise SystemExit("DATABASE_URL is missing.")

    print("=== POSTGIS HEALTH ===")

    conn = await asyncpg.connect(
        database_url,
        timeout=10,
        command_timeout=8,
    )

    try:
        print("DB connection: OK")

        # ---------------------------------------------------------
        # 1. PostGIS extension
        # ---------------------------------------------------------
        extension = await conn.fetchrow(
            """
            SELECT
                extname,
                extversion,
                extnamespace::regnamespace AS schema_name
            FROM pg_extension
            WHERE extname = 'postgis';
            """
        )

        print(
            "PostGIS extension:",
            dict(extension) if extension else None,
        )

        # ---------------------------------------------------------
        # 2. EEZ table
        # ---------------------------------------------------------
        table_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'gis'
                  AND table_name = 'eez_boundaries'
            );
            """
        )

        print("EEZ table exists:", table_exists)

        if not table_exists:
            return

        # ---------------------------------------------------------
        # 3. Row count
        # ---------------------------------------------------------
        row_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM gis.eez_boundaries;
            """
        )

        print("EEZ row count:", row_count)

        # ---------------------------------------------------------
        # 4. Inspect geometry column WITHOUT PostGIS functions
        # ---------------------------------------------------------
        column_info = await conn.fetchrow(
            """
            SELECT
                column_name,
                udt_schema,
                udt_name
            FROM information_schema.columns
            WHERE table_schema = 'gis'
              AND table_name = 'eez_boundaries'
              AND column_name = 'geom';
            """
        )

        print(
            "Geometry column:",
            dict(column_info) if column_info else None,
        )

        # ---------------------------------------------------------
        # 5. Check PostGIS function location
        # ---------------------------------------------------------
        functions = await conn.fetch(
            """
            SELECT
                n.nspname AS schema_name,
                p.proname AS function_name
            FROM pg_proc p
            JOIN pg_namespace n
              ON n.oid = p.pronamespace
            WHERE p.proname IN (
                'st_intersects',
                'st_setsrid',
                'st_makepoint'
            )
            ORDER BY
                p.proname,
                n.nspname;
            """
        )

        print("PostGIS functions:")

        for row in functions:
            print(
                f"  - {row['schema_name']}.{row['function_name']}"
            )

        # ---------------------------------------------------------
        # 6. REAL Rameswaram point test
        # ---------------------------------------------------------
        print("Running Rameswaram intersection test...")

        point_test = await conn.fetchrow(
            """
            SELECT COUNT(*) AS intersecting_rows
            FROM gis.eez_boundaries
            WHERE gis.ST_Intersects(
                geom,
                gis.ST_SetSRID(
                    gis.ST_MakePoint($1, $2),
                    4326
                )
            );
            """,
            LONGITUDE,
            LATITUDE,
        )

        print(
            "Rameswaram intersection:",
            dict(point_test),
        )

        # ---------------------------------------------------------
        # 7. Check indexes
        # ---------------------------------------------------------
        print("Checking indexes...")

        indexes = await conn.fetch(
            """
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'gis'
              AND tablename = 'eez_boundaries'
            ORDER BY indexname;
            """
        )

        if indexes:
            for row in indexes:
                print(
                    f"  - {row['indexname']}: "
                    f"{row['indexdef']}"
                )
        else:
            print("  No indexes found.")

        print("=== POSTGIS HEALTH COMPLETE ===")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())