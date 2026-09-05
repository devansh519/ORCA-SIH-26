#!/usr/bin/env python3
"""Validate the PostGIS geospatial backend before importing EEZ / MPA / IMBL datasets."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPOSITORY_ROOT / ".env")


def main() -> int:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Geospatial import not configured: DATABASE_URL is missing.")
        return 1

    print("DATABASE_URL is set.")

    try:
        import psycopg2
    except ModuleNotFoundError:
        print("psycopg2 is not installed in this environment; install it before import.")
        return 1

    try:
        conn = psycopg2.connect(db_url)
    except Exception as exc:  # pragma: no cover - diagnostics only
        print(f"Database connection failed: {type(exc).__name__}: {exc}")
        return 1

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis')")
            has_postgis = cur.fetchone()[0]

        if not has_postgis:
            print("PostGIS is not enabled on the connected database. Enable the PostGIS extension in Supabase or use a PostGIS-enabled database before importing EEZ datasets.")
            return 1

        print("PostGIS is available on the connected database.")
    finally:
        conn.close()

    missing = [
        name
        for name in (
            "POSTGIS_EEZ_DATASET_PATH",
            "POSTGIS_MPA_DATASET_PATH",
            "POSTGIS_IMBL_DATASET_PATH",
        )
        if not os.getenv(name)
    ]
    if missing:
        print("The following dataset paths are not configured: " + ", ".join(missing))
        return 1

    print("All required geospatial dataset paths are configured. Import can proceed once the DB is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
