import asyncio

from app.tools.geocoding import GeocodingTool


def test_geocoding_returns_place_coordinates():
    async def run():
        return await GeocodingTool().resolve("Rameswaram")

    result = asyncio.run(run())

    assert result["status"] == "available", result
    assert result["source"] == "Open-Meteo Geocoding API"
    assert result["name"]
    assert isinstance(result["latitude"], float)
    assert isinstance(result["longitude"], float)
    assert result["quality"] == "GOOD"
