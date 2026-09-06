from datetime import datetime, timedelta, timezone

import pytest

from app.tools.geospatial import GeospatialTool
from app.tools.marine import MarineDataTool
from app.tools.weather import WeatherTool


@pytest.mark.asyncio
async def test_marine_tool_returns_structured_unavailable_state():
    tool = MarineDataTool()

    result = await tool.fetch(
        latitude=9.2876,
        longitude=79.3129,
        target_time=datetime.now(timezone.utc) + timedelta(days=1),
    )

    assert result["status"] in {"available", "unavailable"}
    assert "source" in result
    assert "variables" in result
    assert "quality" in result
    assert "confidence" in result


@pytest.mark.asyncio
async def test_weather_tool_returns_structured_unavailable_state():
    tool = WeatherTool()

    result = await tool.fetch(
        latitude=9.2876,
        longitude=79.3129,
        target_time=datetime.now(timezone.utc) + timedelta(days=1),
    )

    assert result["status"] in {"available", "unavailable"}
    assert "source" in result
    assert "variables" in result
    assert "quality" in result
    assert "confidence" in result


@pytest.mark.asyncio
async def test_geospatial_tool_validates_coordinates_and_detects_missing_geometry():
    tool = GeospatialTool()

    assert tool.validate_coordinates(9.2876, 79.3129) is True
    assert tool.validate_coordinates(91.0, 79.3129) is False
    assert tool.validate_coordinates(9.2876, 181.0) is False

    analysis = await tool.analyze(
        latitude=9.2876,
        longitude=79.3129,
    )

    assert "status" in analysis
    assert "coordinate_valid" in analysis
    assert "eez" in analysis
    assert "mpa" in analysis
    assert "imbl" in analysis


def test_freshness_decision_uses_thresholds():
    assert GeospatialTool.calculate_freshness(age_seconds=30) == "FRESH"
    assert GeospatialTool.calculate_freshness(age_seconds=900) == "STALE"
    assert GeospatialTool.calculate_freshness(age_seconds=36000) == "EXPIRED"