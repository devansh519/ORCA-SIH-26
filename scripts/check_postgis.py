from pathlib import Path
import asyncio
import os

import asyncpg
from dotenv import load_dotenv


async def main():
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("DATABASE_URL: MISSING")
        return

    print("DATABASE_URL: SET")

    conn = await asyncpg.connect(database_url)

    try:
        print("DATABASE: CONNECTED")

        # Check whether PostGIS extension is installed.
        extension = await conn.fetchrow(
            """
            SELECT extname, extversion
            FROM pg_extension
            WHERE extname = 'postgis'
            """
        )

        if extension:
            print(
                f"POSTGIS EXTENSION: INSTALLED "
                f"(version {extension['extversion']})"
            )
        else:
            print("POSTGIS EXTENSION: NOT INSTALLED")

        # Locate PostGIS functions instead of assuming their schema.
        functions = await conn.fetch(
            """
            SELECT
                n.nspname AS schema_name,
                p.proname AS function_name
            FROM pg_proc p
            JOIN pg_namespace n
                ON n.oid = p.pronamespace
            WHERE p.proname IN (
                'postgis_version',
                'st_covers',
                'st_intersects',
                'st_distance',
                'st_makepoint',
                'st_setsrid'
            )
            ORDER BY n.nspname, p.proname
            """
        )

        print("\nPOSTGIS FUNCTIONS:")

        if functions:
            for row in functions:
                print(
                    f"  {row['schema_name']}."
                    f"{row['function_name']}"
                )
        else:
            print("  NONE FOUND")

        # List application tables.
        tables = await conn.fetch(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN (
                'pg_catalog',
                'information_schema'
            )
            ORDER BY table_schema, table_name
            """
        )

        print("\nUSER TABLES:")

        if tables:
            for row in tables:
                print(
                    f"  {row['table_schema']}."
                    f"{row['table_name']}"
                )
        else:
            print("  NONE FOUND")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())