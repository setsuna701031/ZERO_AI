from __future__ import annotations

import copy
from typing import Any, Dict

from core.persona.display_state_contract import ensure_display_state_contract


def render_cli_view(display_state: Dict[str, Any], *, include_tts: bool = False) -> str:
    safe_display = _validated_copy(display_state)
    lines = [
        "[L5]",
        f"runtime_status: {safe_display.get('runtime_status') or '-'}",
        f"controller_status: {safe_display.get('controller_status') or '-'}",
        f"risk_level: {safe_display.get('risk_level') or '-'}",
        f"confirmation_required: {safe_display.get('confirmation_required')}",
        f"display_state_source: {safe_display.get('display_state_source') or '-'}",
        "",
        "[PERSONA]",
        str(safe_display.get("persona_final_reply") or ""),
    ]

    if include_tts:
        tts_input = extract_tts_input(safe_display)
        lines.extend(
            [
                "",
                "[TTS]",
                f"ready: {tts_input.get('ready')}",
                f"model: {tts_input.get('tts_model') or '-'}",
                f"input_source: {tts_input.get('input_source') or '-'}",
                f"runtime_safe: {tts_input.get('runtime_safe')}",
            ]
        )

    return "\n".join(lines)


def render_json_view(display_state: Dict[str, Any]) -> Dict[str, Any]:
    return _validated_copy(display_state)


def extract_tts_input(display_state: Dict[str, Any]) -> Dict[str, Any]:
    safe_display = _validated_copy(display_state)
    pipeline = safe_display.get("tts_pipeline") if isinstance(safe_display.get("tts_pipeline"), dict) else {}
    return {
        "text": str(safe_display.get("persona_final_reply") or ""),
        "input_source": str(pipeline.get("input_source") or ""),
        "text_normalization": bool(pipeline.get("text_normalization")),
        "voice_style": str(pipeline.get("voice_style") or ""),
        "speaker_profile": str(pipeline.get("speaker_profile") or ""),
        "tts_model": str(pipeline.get("tts_model") or ""),
        "tts_model_path": str(pipeline.get("tts_model_path") or ""),
        "audio_output": str(pipeline.get("audio_output") or ""),
        "runtime_safe": bool(pipeline.get("runtime_safe")),
        "controller_writeback": bool(pipeline.get("controller_writeback")),
        "audit_writeback": bool(pipeline.get("audit_writeback")),
        "ready": bool(pipeline.get("ready")),
    }


def _validated_copy(display_state: Dict[str, Any]) -> Dict[str, Any]:
    copied = copy.deepcopy(display_state) if isinstance(display_state, dict) else {}
    return copy.deepcopy(ensure_display_state_contract(copied))
