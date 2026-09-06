import asyncio
from datetime import datetime, timedelta, timezone

from app.decision.engine import DecisionEngine
from app.tools.geospatial import GeospatialTool
from app.tools.marine import MarineDataTool
from app.tools.weather import WeatherTool


LATITUDE = 9.2876
LONGITUDE = 79.3129


async def run():
    target_time = datetime.now(timezone.utc) + timedelta(hours=1)

    weather = await WeatherTool().get_conditions(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        target_time=target_time,
    )

    marine = await MarineDataTool().get_conditions(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        target_time=target_time,
    )

    geospatial = await GeospatialTool().is_inside_eez(
        latitude=LATITUDE,
        longitude=LONGITUDE,
    )

    result = DecisionEngine().evaluate(
        weather=weather,
        marine=marine,
        geospatial=geospatial,
    )

    print("\n=== WEATHER ===")
    print(weather)

    print("\n=== MARINE ===")
    print(marine)

    print("\n=== GEOSPATIAL ===")
    print(geospatial)

    print("\n=== DECISION ENGINE ===")
    print(result)


if __name__ == "__main__":
    asyncio.run(run())