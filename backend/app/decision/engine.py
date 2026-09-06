from __future__ import annotations

from typing import Any

from .rules import score_safety_from_weather, score_yield_from_marine
from .schemas import DecisionResult, SafetyDecision, YieldDecision


class DecisionEngine:
    """ORCA deterministic decision engine.

    Responsibilities:
      1. Consume already-fetched evidence.
      2. Keep safety and fishing-yield decisions separate.
      3. Apply transparent deterministic rules.
      4. Refuse to invent scores when evidence is unavailable.
      5. Produce a recommendation only when safety evidence is sufficient.

    The engine does not call external APIs. Tool calls remain the
    orchestrator's responsibility.
    """

    def evaluate(
        self,
        *,
        weather: dict[str, Any] | None = None,
        marine: dict[str, Any] | None = None,
        geospatial: dict[str, Any] | None = None,
    ) -> DecisionResult:
        weather = weather or {}
        marine = marine or {}
        geospatial = geospatial or {}

        safety_raw = score_safety_from_weather(
            weather,
            geospatial=geospatial,
        )
        yield_raw = score_yield_from_marine(marine)

        safety = SafetyDecision(**safety_raw)
        yield_assessment = YieldDecision(**yield_raw)

        evidence_used: list[str] = []

        if safety.score is not None:
            evidence_used.append("weather")
        if yield_assessment.score is not None:
            evidence_used.append("marine")
        if geospatial.get("status") == "available":
            evidence_used.append("geospatial")

        # Recommendation is intentionally safety-led. Yield never makes an
        # unsafe trip "safe", and yield is never blended into safety.
        if safety.score is None:
            recommendation = "INSUFFICIENT_DATA"
            recommendation_text = (
                "ORCA cannot make a fishing safety recommendation until "
                "live weather/hazard evidence is available."
            )
            status = "insufficient_data"
        else:
            recommendation = safety.level
            if safety.level == "GO":
                recommendation_text = (
                    "ORCA's deterministic safety rules currently classify "
                    "the supplied conditions as GO."
                )
            elif safety.level == "CAUTION":
                recommendation_text = (
                    "ORCA's deterministic safety rules currently classify "
                    "the supplied conditions as CAUTION."
                )
            else:
                recommendation_text = (
                    "ORCA's deterministic safety rules currently classify "
                    "the supplied conditions as AVOID."
                )
            status = "available"

        return DecisionResult(
            safety=safety,
            yield_assessment=yield_assessment,
            recommendation=recommendation,
            recommendation_text=recommendation_text,
            status=status,
            evidence_used=evidence_used,
        )


__all__ = ["DecisionEngine"]
