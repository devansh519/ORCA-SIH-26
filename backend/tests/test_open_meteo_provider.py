import asyncio
from datetime import datetime, timedelta, timezone

from app.tools.marine import MarineDataTool
from app.tools.weather import WeatherTool


LATITUDE = 9.2876
LONGITUDE = 79.3129


def test_open_meteo_weather_returns_live_data(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "open_meteo")

    async def run():
        tool = WeatherTool()
        return await tool.get_conditions(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            target_time=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    result = asyncio.run(run())

    assert result["status"] == "available", result
    assert "Open-Meteo" in result["source"]
    assert result["variables"]
    assert "wind_speed_ms" in result["variables"]
    assert result["quality"]["level"] == "GOOD"


def test_open_meteo_marine_returns_live_data(monkeypatch):
    monkeypatch.setenv("MARINE_PROVIDER", "open_meteo")

    async def run():
        tool = MarineDataTool()
        return await tool.get_conditions(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            target_time=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    result = asyncio.run(run())

    assert result["status"] == "available", result
    assert "Open-Meteo" in result["source"]
    assert result["variables"]
    assert "wave_height_m" in result["variables"]
    assert "sst_c" in result["variables"]
    assert result["quality"]["level"] == "GOOD"
