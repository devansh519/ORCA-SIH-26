from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DecisionLevel = Literal[
    "GO",
    "CAUTION",
    "AVOID",
    "INSUFFICIENT_DATA",
]

DecisionStatus = Literal[
    "available",
    "insufficient_data",
]


class SafetyDecision(BaseModel):
    """Deterministic safety decision derived only from supplied evidence."""

    score: float | None = Field(default=None, ge=0, le=100)
    level: DecisionLevel
    reasoning: list[str] = Field(default_factory=list)
    factors: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0, le=1)
    status: DecisionStatus


class YieldDecision(BaseModel):
    """Fishing-yield assessment.

    The MVP only produces a numeric yield score when the marine provider
    supplies recognized, live marine variables. It never invents a score.
    """

    score: float | None = Field(default=None, ge=0, le=100)
    level: DecisionLevel
    reasoning: list[str] = Field(default_factory=list)
    factors: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0, le=1)
    status: DecisionStatus


class DecisionResult(BaseModel):
    """Combined decision output.

    Safety and yield are intentionally independent. There is no blended
    overall score.
    """

    safety: SafetyDecision
    yield_assessment: YieldDecision
    recommendation: DecisionLevel
    recommendation_text: str
    status: DecisionStatus
    evidence_used: list[str] = Field(default_factory=list)

    def to_state_fields(self) -> dict[str, Any]:
        """Return fields compatible with ORCAState/workflow responses."""

        return {
            "safety_score": self.safety.score,
            "safety_score_reasoning": " ".join(self.safety.reasoning)
            if self.safety.reasoning
            else None,
            "yield_score": self.yield_assessment.score,
            "yield_reasoning": " ".join(self.yield_assessment.reasoning)
            if self.yield_assessment.reasoning
            else None,
            "recommendation": self.recommendation,
            "recommendation_text": self.recommendation_text,
        }
