from __future__ import annotations

import asyncio
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured")

DEMO_ZONE = {
    "user_id": "demo-fisherman",
    "name": "Rameswaram Demo Zone",
    "latitude": 9.2876,
    "longitude": 79.3129,
    "alert_radius_km": 1.0,
    "language": "ta",
}


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        zone_id = await conn.fetchval(
            """
            INSERT INTO public.frequent_zones (
                user_id, name, latitude, longitude,
                alert_radius_km, language, active
            )
            VALUES ($1, $2, $3, $4, $5, $6, TRUE)
            RETURNING id::text
            """,
            DEMO_ZONE["user_id"],
            DEMO_ZONE["name"],
            DEMO_ZONE["latitude"],
            DEMO_ZONE["longitude"],
            DEMO_ZONE["alert_radius_km"],
            DEMO_ZONE["language"],
        )
        print(f"Created frequent zone: {zone_id}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
