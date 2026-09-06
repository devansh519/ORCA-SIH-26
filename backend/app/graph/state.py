"""ORCA graph execution state.

This module defines the shared state passed between orchestration/execution
nodes. It intentionally contains data only; routing and tool execution live
in workflow.py and the tool layer.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


QueryType = Literal[
    "proactive_alert",
    "authority_district_hazard_dashboard",
    "researcher_trend_analysis",
    "reactive_voice_query",
    "next_day_feedback",
    "unclassified",
]

UserRole = Literal["fisherman", "authority", "researcher"]
TriggerType = Literal[
    "user_query",
    "scheduled_poll",
    "feedback_prompt_response",
]
InputModality = Literal["voice", "text"]


class ORCAState(TypedDict, total=False):
    """Shared state for one ORCA execution.

    The state is deliberately transport-friendly: values are plain Python
    dictionaries/lists/scalars so the workflow can later be exposed through
    FastAPI without coupling the API layer to LangGraph internals.
    """

    # ------------------------------------------------------------------
    # Request / context
    # ------------------------------------------------------------------
    user_id: str
    user_role: UserRole
    trigger_type: TriggerType
    input_modality: InputModality

    text: str
    user_language: str
    latitude: float
    longitude: float

    # Optional target date/time supplied by the request/context layer.
    target_time: str | None

    # Route supplied by a vessel/test scenario.
    route: list[tuple[float, float]]

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------
    query_type: QueryType
    selected_tools: list[str]
    execution_status: str
    execution_errors: list[str]

    # Used by proactive-alert routing.
    hazard_zone_overlap: bool

    # ------------------------------------------------------------------
    # Tool outputs
    # ------------------------------------------------------------------
    tool_results: dict[str, dict[str, Any]]

    weather_result: dict[str, Any] | None
    marine_result: dict[str, Any] | None
    geospatial_result: dict[str, Any] | None

    # ------------------------------------------------------------------
    # Fusion / decision
    # ------------------------------------------------------------------
    fused_data: dict[str, Any]
    safety_score: float | None
    safety_score_reasoning: str | None

    yield_score: float | None
    yield_reasoning: str | None

    recommendation: str | None
    recommendation_text: str | None

    # ------------------------------------------------------------------
    # Golden Schema / synthesis
    # ------------------------------------------------------------------
    golden_schema: dict[str, Any]
    synthesis_text: str | None

    # ------------------------------------------------------------------
    # Response metadata
    # ------------------------------------------------------------------
    sources: list[dict[str, Any]]
    response_id: str | None
    timestamp_ist: str | None
    timestamp_utc: str | None
    confidence_overall: float | None

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------
    feedback_id: str | None
    linked_prior_response_id: str | None
    zone_id: str | None
    structured_feedback: dict[str, Any] | None
    implicit_signal: dict[str, Any] | None
    confidence_adjustment: dict[str, Any] | None


def initial_state(
    *,
    user_id: str,
    user_role: UserRole,
    trigger_type: TriggerType,
    input_modality: InputModality,
    text: str = "",
    user_language: str = "en",
    latitude: float | None = None,
    longitude: float | None = None,
    target_time: str | None = None,
    route: list[tuple[float, float]] | None = None,
    hazard_zone_overlap: bool = False,
) -> ORCAState:
    """Create a clean state for a new ORCA execution."""

    state: ORCAState = {
        "user_id": user_id,
        "user_role": user_role,
        "trigger_type": trigger_type,
        "input_modality": input_modality,
        "text": text,
        "user_language": user_language,
        "target_time": target_time,
        "route": route or [],
        "query_type": "unclassified",
        "selected_tools": [],
        "execution_status": "pending",
        "execution_errors": [],
        "hazard_zone_overlap": hazard_zone_overlap,
        "tool_results": {},
        "weather_result": None,
        "marine_result": None,
        "geospatial_result": None,
        "fused_data": {},
        "safety_score": None,
        "safety_score_reasoning": None,
        "yield_score": None,
        "yield_reasoning": None,
        "recommendation": None,
        "recommendation_text": None,
        "golden_schema": {},
        "synthesis_text": None,
        "sources": [],
        "response_id": None,
        "timestamp_ist": None,
        "timestamp_utc": None,
        "confidence_overall": None,
        "feedback_id": None,
        "linked_prior_response_id": None,
        "zone_id": None,
        "structured_feedback": None,
        "implicit_signal": None,
        "confidence_adjustment": None,
    }

    if latitude is not None:
        state["latitude"] = latitude
    if longitude is not None:
        state["longitude"] = longitude

    return state
