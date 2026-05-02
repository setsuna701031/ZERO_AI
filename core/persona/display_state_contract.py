from __future__ import annotations

from typing import Any, Dict, List, Tuple


DISPLAY_STATE_SCHEMA_VERSION = "l5_persona_display_state.v1"

DISPLAY_STATE_REQUIRED_KEYS: Tuple[str, ...] = (
    "ok",
    "display_state_schema_version",
    "display_state_source",
    "runtime_status",
    "controller_status",
    "risk_level",
    "confirmation_required",
    "status_source",
    "task_goal",
    "tool_calls",
    "result_summary",
    "blocked_reason",
    "trace",
    "execution_log",
    "last_result",
    "timeline",
    "audit_records",
    "persona_status_update",
    "persona_intent_explanation",
    "persona_reasoning_summary",
    "persona_final_reply",
    "presentation_log",
    "tts_pipeline",
    "persona_runtime_contract",
)

TTS_PIPELINE_REQUIRED_KEYS: Tuple[str, ...] = (
    "input_source",
    "text_normalization",
    "voice_style",
    "speaker_profile",
    "tts_model",
    "tts_model_path",
    "audio_output",
    "runtime_safe",
    "controller_writeback",
    "audit_writeback",
    "ready",
)

PRESENTATION_LOG_REQUIRED_KEYS: Tuple[str, ...] = (
    "reply_id",
    "text_hash",
    "voice_id",
    "tts_model",
    "audio_path",
    "created_at",
    "source",
)

PERSONA_RUNTIME_CONTRACT_REQUIRED_KEYS: Tuple[str, ...] = (
    "role",
    "display_state_source",
    "presentation_flow",
    "input_sources",
    "can",
    "cannot",
    "no_reverse_path",
    "forbidden_reverse_paths",
)

DISPLAY_STATE_LIST_KEYS: Tuple[str, ...] = (
    "tool_calls",
    "trace",
    "execution_log",
    "timeline",
    "audit_records",
)

DISPLAY_STATE_DICT_KEYS: Tuple[str, ...] = (
    "last_result",
    "presentation_log",
    "tts_pipeline",
    "persona_runtime_contract",
)


def ensure_display_state_contract(display_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the public L5 Persona display_state contract.

    This is intentionally structural only. It must not interpret results,
    decide tools, infer missing runtime state, or change runtime behavior.
    """
    payload = display_state if isinstance(display_state, dict) else {}
    payload["display_state_schema_version"] = DISPLAY_STATE_SCHEMA_VERSION

    errors: List[str] = []
    errors.extend(_missing_keys(payload, DISPLAY_STATE_REQUIRED_KEYS, prefix="display_state"))

    for key in DISPLAY_STATE_LIST_KEYS:
        if key in payload and not isinstance(payload.get(key), list):
            errors.append(f"display_state.{key} must be list")

    for key in DISPLAY_STATE_DICT_KEYS:
        if key in payload and not isinstance(payload.get(key), dict):
            errors.append(f"display_state.{key} must be dict")

    if "confirmation_required" in payload and not isinstance(payload.get("confirmation_required"), bool):
        errors.append("display_state.confirmation_required must be bool")

    for key in (
        "display_state_schema_version",
        "display_state_source",
        "runtime_status",
        "controller_status",
        "risk_level",
        "status_source",
        "task_goal",
        "result_summary",
        "blocked_reason",
        "persona_status_update",
        "persona_intent_explanation",
        "persona_reasoning_summary",
        "persona_final_reply",
    ):
        if key in payload and not isinstance(payload.get(key), str):
            errors.append(f"display_state.{key} must be str")

    tts_pipeline = payload.get("tts_pipeline") if isinstance(payload.get("tts_pipeline"), dict) else {}
    errors.extend(_missing_keys(tts_pipeline, TTS_PIPELINE_REQUIRED_KEYS, prefix="tts_pipeline"))
    if tts_pipeline.get("input_source") != "persona_final_reply":
        errors.append("tts_pipeline.input_source must be persona_final_reply")
    if tts_pipeline.get("runtime_safe") is not True:
        errors.append("tts_pipeline.runtime_safe must be true")
    if tts_pipeline.get("controller_writeback") is not False:
        errors.append("tts_pipeline.controller_writeback must be false")
    if tts_pipeline.get("audit_writeback") is not False:
        errors.append("tts_pipeline.audit_writeback must be false")

    presentation_log = payload.get("presentation_log") if isinstance(payload.get("presentation_log"), dict) else {}
    errors.extend(_missing_keys(presentation_log, PRESENTATION_LOG_REQUIRED_KEYS, prefix="presentation_log"))

    persona_contract = payload.get("persona_runtime_contract") if isinstance(payload.get("persona_runtime_contract"), dict) else {}
    errors.extend(_missing_keys(persona_contract, PERSONA_RUNTIME_CONTRACT_REQUIRED_KEYS, prefix="persona_runtime_contract"))
    if persona_contract.get("display_state_source") != "runtime_bridge":
        errors.append("persona_runtime_contract.display_state_source must be runtime_bridge")
    if persona_contract.get("no_reverse_path") is not True:
        errors.append("persona_runtime_contract.no_reverse_path must be true")

    if errors:
        raise ValueError("invalid L5 Persona display_state contract: " + "; ".join(errors))

    return payload


def _missing_keys(payload: Dict[str, Any], keys: Tuple[str, ...], *, prefix: str) -> List[str]:
    return [f"{prefix}.{key} missing" for key in keys if key not in payload]
