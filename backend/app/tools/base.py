from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("orca.tools")


@dataclass
class ToolResult:
    source: str
    status: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fetch_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    location: dict[str, Any] | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str | None = None
    freshness: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
            "fetch_timestamp": self.fetch_timestamp.isoformat(),
            "location": self.location,
            "variables": self.variables,
            "units": self.units,
            "quality": self.quality,
            "confidence": self.confidence,
            "reason": self.reason,
            "freshness": self.freshness,
        }


class BaseTool:
    """Common tool interface for ORCA deterministic integrations."""

    def __init__(self, source_name: str, *, default_timeout: float = 10.0) -> None:
        self.source_name = source_name
        self.default_timeout = default_timeout

    @staticmethod
    def calculate_freshness(age_seconds: int | float) -> str:
        if age_seconds < 900:
            return "FRESH"
        if age_seconds < 36000:
            return "STALE"
        return "EXPIRED"

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)

    def log_call(
        self,
        *,
        request_id: str | None,
        latitude: float,
        longitude: float,
        target_time: datetime,
        duration_ms: int,
        status: str,
    ) -> None:
        logger.info(
            "tool_call",
            extra={
                "request_id": request_id,
                "tool": self.source_name,
                "latitude": latitude,
                "longitude": longitude,
                "target_time": target_time.isoformat(),
                "duration_ms": duration_ms,
                "status": status,
            },
        )

    def _timed_call(self, func, *args, **kwargs):
        started = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            duration_ms = int((time.perf_counter() - started) * 1000)
            return result, duration_ms
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            raise
