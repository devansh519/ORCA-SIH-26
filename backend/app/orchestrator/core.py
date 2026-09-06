"""
ORCA — Orchestrator Core

Implements:
    1. Deterministic intent classification / routing
    2. Unified Golden Schema validation
    3. Swappable LLM provider adapter
    4. Synthesis explanation
    5. Feedback extraction

Design rules:
    - Routing is 100% deterministic.
    - Schema validation is 100% deterministic.
    - LLMs are used only for synthesis and feedback extraction.
    - LLM failures must never break the demo.
    - No fake marine/weather/geospatial data is created here.
    - Tool execution belongs to the orchestration/execution layer.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# 1. INTENT CLASSIFICATION
# ============================================================================

QueryType = Literal[
    "proactive_alert",
    "authority_district_hazard_dashboard",
    "researcher_trend_analysis",
    "reactive_voice_query",
    "next_day_feedback",
    "unclassified",
]


FISHERMAN_SAFETY_KEYWORDS = [
    "safe",
    "fish",
    "tomorrow",
    "போகலாமா",
    "பாதுகாப்பா",
    "go",
    "danger",
]

AUTHORITY_KEYWORDS = [
    "active hazard",
    "warning",
    "district",
    "dashboard",
]

RESEARCHER_KEYWORDS = [
    "trend",
    "sst",
    "chlorophyll",
    "correlation",
]


@dataclass
class IncomingRequest:
    """
    Input received by the deterministic classifier.

    `text` should already be:
        - typed text for text requests, or
        - STT-transcribed text for voice requests.
    """

    user_role: Literal["fisherman", "authority", "researcher"]
    trigger_type: Literal[
        "user_query",
        "scheduled_poll",
        "feedback_prompt_response",
    ]
    input_modality: Literal["voice", "text"]

    text: str = ""

    # Populated by the scheduled-alert/geospatial execution layer before
    # classification for proactive-alert evaluation.
    hazard_zone_overlap: bool = False


def classify_intent(req: IncomingRequest) -> QueryType:
    """
    Deterministic routing table.

    No LLM is used here.

    Routing precedence:
        1. proactive alert
        2. feedback
        3. authority dashboard
        4. researcher trend
        5. fisherman reactive query
        6. unclassified fallback
    """

    text_lower = req.text.lower()

    # ------------------------------------------------------------------
    # Rule 1 — proactive alert
    # ------------------------------------------------------------------
    if (
        req.trigger_type == "scheduled_poll"
        and req.hazard_zone_overlap
    ):
        return "proactive_alert"

    # ------------------------------------------------------------------
    # Rule 5 — next-day feedback
    # ------------------------------------------------------------------
    if req.trigger_type == "feedback_prompt_response":
        return "next_day_feedback"

    # ------------------------------------------------------------------
    # Rule 2 — authority dashboard
    # ------------------------------------------------------------------
    if (
        req.user_role == "authority"
        and any(keyword in text_lower for keyword in AUTHORITY_KEYWORDS)
    ):
        return "authority_district_hazard_dashboard"

    # ------------------------------------------------------------------
    # Rule 3 — researcher trend analysis
    # ------------------------------------------------------------------
    if (
        req.user_role == "researcher"
        and any(keyword in text_lower for keyword in RESEARCHER_KEYWORDS)
    ):
        return "researcher_trend_analysis"

    # ------------------------------------------------------------------
    # Rule 4 — fisherman reactive query
    #
    # Important:
    # Use text_lower here so English keyword matching is case-insensitive.
    # Tamil matching is unaffected by .lower().
    # ------------------------------------------------------------------
    if (
        req.user_role == "fisherman"
        and req.trigger_type == "user_query"
        and any(keyword.lower() in text_lower for keyword in FISHERMAN_SAFETY_KEYWORDS)
    ):
        return "reactive_voice_query"

    # ------------------------------------------------------------------
    # Rule 6 — safe fallback
    # ------------------------------------------------------------------
    return "unclassified"


UNCLASSIFIED_FALLBACK_TEXT = {
    "ta": (
        "எனக்கு புரியவில்லை. பாதுகாப்பு, காலநிலை அல்லது உங்கள் "
        "மீன்பிடி பகுதி பற்றி கேளுங்கள்."
    ),
    "en": (
        "I couldn't understand that clearly — could you ask about "
        "safety, weather, or your fishing zone?"
    ),
}


# ============================================================================
# 2. GOLDEN SCHEMA VALIDATION
# ============================================================================

REQUIRED_BASE_FIELDS = [
    "query_type",
    "user_id",
    "user_language",
    "timestamp_ist",
    "timestamp_utc",
    "confidence_overall",
    "sources",
]


REQUIRED_EXTENSION_FIELDS: dict[QueryType, list[str]] = {
    "proactive_alert": [
        "alert_id",
        "vessel",
        "frequent_zone",
        "trigger",
        "hazards_detected",
        "safety_score",
        "safety_score_reasoning",
        "yield_score",
        "yield_reasoning",
        "recommendation",
        "recommendation_text",
        "action_taken",
    ],
    "authority_district_hazard_dashboard": [
        "district",
        "hazard_summary",
        "harbours",
    ],
    "researcher_trend_analysis": [
        "region",
        "variables",
        "period",
        "trends",
    ],
    "reactive_voice_query": [
        "query_id",
        "query_transcript",
        "vessel",
        "frequent_zone",
        "forecast_target_date_ist",
        "conditions_forecast",
        "safety_score",
        "yield_score",
        "recommendation",
        "recommendation_text",
    ],
    "next_day_feedback": [
        "feedback_id",
        "linked_prior_response_id",
        "zone_id",
        "structured_feedback",
        "implicit_signal",
        "confidence_adjustment",
    ],
    "unclassified": [],
}


class SchemaValidationError(Exception):
    """
    Raised when a Golden Schema payload is invalid.

    A required field is invalid when it is:
        - missing, or
        - explicitly None.
    """



def validate_response(payload: dict[str, Any]) -> None:
    """
    Validate a response against the unified Golden Schema.

    Raises:
        SchemaValidationError:
            If query_type is unknown or any required field is missing/null.
    """

    if not isinstance(payload, dict):
        raise SchemaValidationError(
            "Response payload must be a dictionary."
        )

    query_type = payload.get("query_type")

    if query_type not in REQUIRED_EXTENSION_FIELDS:
        raise SchemaValidationError(
            f"Unknown query_type: {query_type!r}"
        )

    required_fields = [
        *REQUIRED_BASE_FIELDS,
        *REQUIRED_EXTENSION_FIELDS[query_type],
    ]

    missing_or_null = [
        field
        for field in required_fields
        if field not in payload or payload[field] is None
    ]

    if missing_or_null:
        raise SchemaValidationError(
            f"Response for query_type={query_type!r} is missing or null "
            f"required fields: {missing_or_null}"
        )

    # ---------------------------------------------------------------
    # Special validation for next-day feedback.
    #
    # Prevents the system from implying that one report immediately
    # changes model confidence.
    # ---------------------------------------------------------------
    if query_type == "next_day_feedback":
        adjustment = payload.get("confidence_adjustment")

        if not isinstance(adjustment, dict):
            raise SchemaValidationError(
                "next_day_feedback.confidence_adjustment must be an object."
            )

        adjustment_required = [
            "threshold_reports_required",
            "current_report_count",
        ]

        missing_adjustment = [
            field
            for field in adjustment_required
            if field not in adjustment or adjustment[field] is None
        ]

        if missing_adjustment:
            raise SchemaValidationError(
                "next_day_feedback.confidence_adjustment is missing or "
                f"null fields: {missing_adjustment}"
            )


# ============================================================================
# 3. LLM PROVIDER ADAPTER
# ============================================================================

class LLMProvider:
    """
    Minimal provider interface.

    The rest of ORCA should not depend directly on Groq/Gemini APIs.
    """

    def complete(
        self,
        system_prompt: str,
        user_content: str,
        timeout_s: float = 2.0,
    ) -> str:
        raise NotImplementedError


class GroqProvider(LLMProvider):
    """Groq implementation of the ORCA LLM provider."""

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
    ) -> None:
        self.model = model

        # Lazy import keeps the core module importable when the optional
        # Groq dependency is not installed.
        import groq

        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured."
            )

        self._client = groq.Groq(api_key=api_key)

    def complete(
        self,
        system_prompt: str,
        user_content: str,
        timeout_s: float = 2.0,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            timeout=timeout_s,
        )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "LLM provider returned an empty response."
            )

        return content


class GeminiProvider(LLMProvider):
    """
    Gemini implementation.

    This remains optional and is not the default provider.
    """

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
    ) -> None:
        self.model = model

        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not configured."
            )

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)

    def complete(
        self,
        system_prompt: str,
        user_content: str,
        timeout_s: float = 2.0,
    ) -> str:
        response = self._model.generate_content(
            [system_prompt, user_content],
            request_options={"timeout": timeout_s},
        )

        text = response.text

        if not text:
            raise RuntimeError(
                "LLM provider returned an empty response."
            )

        return text


def get_default_provider() -> LLMProvider:
    """
    Return ORCA's configured default LLM provider.

    Groq is currently the default because the ORCA specification uses
    Groq for synthesis and shares the infrastructure with Whisper STT.
    """

    return GroqProvider(
        model="llama-3.3-70b-versatile"
    )


# ============================================================================
# 4. SYNTHESIS EXPLANATION
# ============================================================================

SYNTHESIS_SYSTEM_PROMPT = """You are ORCA's Synthesis agent. You are given structured marine safety data as JSON. Your ONLY job is to explain it clearly in {user_language}, in at most 6 short sentences, suitable for text-to-speech.

Rules:
- NEVER invent a number not present in the input JSON.
- Always state the recommendation first (GO / NO GO / GO WITH CAUTION).
- Mention safety score and yield score separately — never combine them into one judgment.
- If IMBL/boundary distance is present, always mention it, even if conditions are otherwise safe.
- Keep tone calm, direct, respectful — this is read aloud to a fisherman, not a researcher.
- Do not add caveats beyond what's in the source data.

Output: plain text only, no markdown, ready for TTS."""


def synthesize_explanation(
    golden_schema_json: dict[str, Any],
    user_language: str,
    fallback_script: str,
    provider: Optional[LLMProvider] = None,
) -> str:
    """
    Generate the human-readable ORCA explanation.

    Provider initialization is intentionally inside the try block so
    configuration/import/API failures all reach the fallback.

    The fallback is silent from the perspective of the caller.
    """

    try:
        active_provider = provider or get_default_provider()

        system_prompt = SYNTHESIS_SYSTEM_PROMPT.format(
            user_language=user_language
        )

        return active_provider.complete(
            system_prompt=system_prompt,
            user_content=json.dumps(
                golden_schema_json,
                ensure_ascii=False,
            ),
            timeout_s=2.0,
        )

    except Exception as exc:
        logger.warning(
            "ORCA synthesis LLM failed; using fallback script: %s",
            exc,
        )
        return fallback_script


# ============================================================================
# 5. FEEDBACK EXTRACTION
# ============================================================================

FEEDBACK_SYSTEM_PROMPT = """You are ORCA's feedback-extraction step. You are given a fisherman's free-text or voice-transcribed reply to "was yesterday's prediction accurate?" Extract structured feedback as JSON matching this exact shape:

{
  "safety_forecast_discrepancy": {
    "direction": "actual_stronger_than_predicted | actual_weaker_than_predicted | matched_prediction | not_mentioned",
    "self_reported": true
  },
  "yield_forecast_confirmation": {
    "result": "confirmed_accurate | confirmed_inaccurate | not_mentioned",
    "self_reported": true
  }
}

Only extract what is explicitly stated. Do not infer sentiment beyond the literal content. If a topic isn't mentioned, use "not_mentioned".

Output: JSON only, no explanation."""


VALID_SAFETY_DIRECTIONS = {
    "actual_stronger_than_predicted",
    "actual_weaker_than_predicted",
    "matched_prediction",
    "not_mentioned",
}

VALID_YIELD_RESULTS = {
    "confirmed_accurate",
    "confirmed_inaccurate",
    "not_mentioned",
}


def _validate_feedback_result(
    result: Any,
) -> dict[str, Any]:
    """
    Validate the structure returned by the feedback LLM.

    This is deterministic validation after the LLM call.
    """

    if not isinstance(result, dict):
        raise ValueError(
            "Feedback response must be a JSON object."
        )

    safety = result.get("safety_forecast_discrepancy")
    yield_result = result.get("yield_forecast_confirmation")

    if not isinstance(safety, dict):
        raise ValueError(
            "Missing or invalid safety_forecast_discrepancy."
        )

    if not isinstance(yield_result, dict):
        raise ValueError(
            "Missing or invalid yield_forecast_confirmation."
        )

    safety_direction = safety.get("direction")
    safety_self_reported = safety.get("self_reported")

    if safety_direction not in VALID_SAFETY_DIRECTIONS:
        raise ValueError(
            f"Invalid safety forecast direction: {safety_direction!r}"
        )

    if not isinstance(safety_self_reported, bool):
        raise ValueError(
            "safety_forecast_discrepancy.self_reported must be boolean."
        )

    yield_value = yield_result.get("result")
    yield_self_reported = yield_result.get("self_reported")

    if yield_value not in VALID_YIELD_RESULTS:
        raise ValueError(
            f"Invalid yield forecast result: {yield_value!r}"
        )

    if not isinstance(yield_self_reported, bool):
        raise ValueError(
            "yield_forecast_confirmation.self_reported must be boolean."
        )

    return result


def extract_feedback(
    transcript: str,
    user_language: str,
    provider: Optional[LLMProvider] = None,
) -> dict[str, Any]:
    """
    Extract structured feedback from a fisherman response.

    On any failure:
        - preserve the raw transcript
        - do not fabricate structured feedback
        - return an explicit extraction-failure marker
    """

    try:
        active_provider = provider or get_default_provider()

        raw = active_provider.complete(
            system_prompt=FEEDBACK_SYSTEM_PROMPT,
            user_content=(
                f'User reply ({user_language}): "{transcript}"'
            ),
            timeout_s=2.0,
        )

        parsed = json.loads(raw)

        return _validate_feedback_result(parsed)

    except Exception as exc:
        logger.warning(
            "ORCA feedback extraction failed; raw transcript preserved: %s",
            exc,
        )

        return {
            "structured_feedback": None,
            "note": "extraction_failed_raw_logged",
            "raw_transcript": transcript,
        }


# ============================================================================
# 6. SELF-TEST
# ============================================================================

if __name__ == "__main__":
    test_cases = [
        (
            IncomingRequest(
                "fisherman",
                "scheduled_poll",
                "text",
                hazard_zone_overlap=True,
            ),
            "proactive_alert",
        ),
        (
            IncomingRequest(
                "authority",
                "user_query",
                "text",
                text="show active hazard warnings for my district",
            ),
            "authority_district_hazard_dashboard",
        ),
        (
            IncomingRequest(
                "researcher",
                "user_query",
                "text",
                text="SST and chlorophyll trend last 30 days",
            ),
            "researcher_trend_analysis",
        ),
        (
            IncomingRequest(
                "fisherman",
                "user_query",
                "voice",
                text="நாளைக்கு போகலாமா? பாதுகாப்பா?",
            ),
            "reactive_voice_query",
        ),
        (
            IncomingRequest(
                "fisherman",
                "feedback_prompt_response",
                "voice",
                text="anything",
            ),
            "next_day_feedback",
        ),
        (
            IncomingRequest(
                "fisherman",
                "user_query",
                "voice",
                text="what time is it",
            ),
            "unclassified",
        ),
        (
            IncomingRequest(
                "fisherman",
                "user_query",
                "text",
                text="Is it SAFE to FISH tomorrow?",
            ),
            "reactive_voice_query",
        ),
    ]

    passed = 0

    for request, expected in test_cases:
        actual = classify_intent(request)

        if actual == expected:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"

        print(
            f"[{status}] "
            f"expected={expected!r} "
            f"actual={actual!r}"
        )

    print(f"\n{passed}/{len(test_cases)} routing tests passed.")