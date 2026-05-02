from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.persona.display_state_contract import ensure_display_state_contract
from core.persona.runtime_bridge import get_persona_runtime_bridge
from core.persona.visual_profile import load_default_visual_profile


def get_digital_human_shell_state(display_state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    source = copy.deepcopy(display_state) if isinstance(display_state, dict) else get_persona_runtime_bridge().get_display_state()
    display = ensure_display_state_contract(source)
    visual_profile = load_default_visual_profile()
    runtime_status = str(display.get("runtime_status") or "planning")

    return {
        "ok": True,
        "shell": "digital_human_ui_shell",
        "read_only": True,
        "avatar": {
            "name": "ZERO",
            "visual_id": visual_profile.visual_id,
            "image_url": "/assets/persona/zero_v1/idle_open.png",
            "state": _persona_state(runtime_status),
            "persona_locked": True,
            "persona_note": "single fixed persona shell",
        },
        "status": {
            "runtime_status": runtime_status,
            "controller_status": str(display.get("controller_status") or ""),
            "risk_level": str(display.get("risk_level") or ""),
            "blocked_reason": str(display.get("blocked_reason") or ""),
            "confirmation_required": bool(display.get("confirmation_required")),
        },
        "task": {
            "goal": str(display.get("task_goal") or ""),
            "tool_calls": copy.deepcopy(display.get("tool_calls") if isinstance(display.get("tool_calls"), list) else []),
        },
        "result": {
            "persona_final_reply": str(display.get("persona_final_reply") or ""),
            "result_summary": str(display.get("result_summary") or ""),
            "last_result": copy.deepcopy(display.get("last_result") if isinstance(display.get("last_result"), dict) else {}),
        },
        "trace_summary": _trace_summary(display),
        "tts": {
            "placeholder": True,
            "state": "idle",
            "label": "speaking...",
            "voice_enabled": False,
        },
        "display_state": display,
    }


def run_digital_human_shell_command(command: str) -> Dict[str, Any]:
    text = str(command or "").strip()
    bridge = get_persona_runtime_bridge()
    normalized = text.lower()

    if normalized in {"", "status", "runtime-status"}:
        display = bridge.get_display_state()
    elif normalized in {"runtime-replay", "replay", "replay demo"}:
        display = bridge.replay_last_task()
    else:
        display = bridge.submit_ui_task(text)

    return get_digital_human_shell_state(display)


def _persona_state(runtime_status: str) -> str:
    value = runtime_status.strip().lower()
    if value in {"done"}:
        return "ready"
    if value in {"failed", "blocked"}:
        return "blocked"
    if value in {"executing"}:
        return "running"
    return "idle"


def _trace_summary(display: Dict[str, Any]) -> List[Dict[str, Any]]:
    timeline = display.get("timeline") if isinstance(display.get("timeline"), list) else []
    trace = display.get("trace") if isinstance(display.get("trace"), list) else []
    audit = display.get("audit_records") if isinstance(display.get("audit_records"), list) else []

    rows: List[Dict[str, Any]] = []
    for item in timeline[:8]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "source": "timeline",
                "label": str(item.get("label") or item.get("phase") or ""),
                "status": str(item.get("status") or ""),
                "detail": str(item.get("detail") or ""),
                "summary": _compact_trace_line(item),
            }
        )

    for item in trace[:8]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "source": "trace",
                "label": str(item.get("event_type") or item.get("tool") or item.get("step_type") or ""),
                "status": str(item.get("status") or item.get("ok") or ""),
                "detail": str(item.get("result_summary") or item.get("message") or ""),
                "summary": _compact_trace_line(item),
            }
        )

    if not rows:
        for item in audit[:8]:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "source": "audit",
                    "label": str(item.get("requested_tool") or item.get("final_decision") or ""),
                    "status": str(item.get("result_status") or ""),
                    "detail": str(item.get("reason") or ""),
                    "summary": _compact_trace_line(item),
                }
            )

    return rows[:12]


def _compact_trace_line(item: Dict[str, Any]) -> str:
    tool = str(item.get("tool") or item.get("requested_tool") or item.get("step_type") or "").strip()
    status = str(item.get("status") or item.get("result_status") or item.get("ok") or "").strip()
    summary = str(
        item.get("result_summary")
        or item.get("summary")
        or item.get("message")
        or item.get("detail")
        or item.get("final_decision")
        or ""
    ).strip()
    parts = [part for part in (tool, status, summary) if part]
    text = " / ".join(parts)
    if len(text) <= 120:
        return text
    return text[:117].rstrip() + "..."
