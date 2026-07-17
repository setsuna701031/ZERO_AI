from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from core.tasks.planner_gateway_runtime import run_scheduler_planner_gateway


def _contract_payload_to_external_plan(payload: Any, user_input: str) -> Optional[Dict[str, Any]]:
    """Convert a valid planner contract payload into legacy external-plan shape.

    Phase10-G-9 keeps the scheduler compatibility boundary intact:
    gateway/contract output gets first chance only when it can be represented
    as the existing external planner shape. Otherwise the raw legacy planner
    result is returned unchanged.
    """
    if not isinstance(payload, dict):
        return None

    if payload.get("is_valid") is False:
        return None

    action = str(payload.get("action") or "").strip().lower()
    if action in {"", "noop", "repair", "rollback"}:
        return None

    target_path = payload.get("target_path")
    target_path_text = str(target_path or "").strip()
    content_text = str(payload.get("content") or "")
    command_text = str(payload.get("command") or "").strip()
    goal_text = str(payload.get("goal") or user_input or "").strip()
    reason_text = str(payload.get("reason") or "").strip()

    step: Dict[str, Any]
    intent = action

    if action == "read_file":
        if not target_path_text:
            return None
        step = {
            "type": "read_file",
            "path": target_path_text,
            "target_path": target_path_text,
        }
    elif action == "write_file":
        if not target_path_text:
            return None
        step = {
            "type": "write_file",
            "path": target_path_text,
            "target_path": target_path_text,
            "content": content_text,
        }
    elif action == "append_file":
        if not target_path_text:
            return None
        step = {
            "type": "append_file",
            "path": target_path_text,
            "target_path": target_path_text,
            "content": content_text,
        }
    elif action == "verify_file":
        if not target_path_text:
            return None
        step = {
            "type": "verify",
            "path": target_path_text,
            "target_path": target_path_text,
        }
        if reason_text:
            step["reason"] = reason_text
    elif action == "run_command":
        if not command_text:
            return None
        step = {
            "type": "command",
            "command": command_text,
        }
    else:
        return None

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    step["planner_contract_action"] = action
    if metadata:
        step["metadata"] = copy.deepcopy(metadata)

    return {
        "planner_mode": "planner_contract_gateway",
        "intent": intent,
        "final_answer": goal_text or f"planned via planner contract: {action}",
        "steps": [step],
        "planner_contract": {
            "contract_version": str(payload.get("contract_version") or ""),
            "action": action,
            "raw_action": str(payload.get("raw_action") or ""),
            "is_valid": bool(payload.get("is_valid", True)),
            "contract_errors": copy.deepcopy(payload.get("contract_errors") or []),
            "contract_warnings": copy.deepcopy(payload.get("contract_warnings") or []),
            "adapter_ok": payload.get("adapter_ok"),
            "runtime_entry_ok": payload.get("runtime_entry_ok"),
            "planner_gateway_ok": payload.get("planner_gateway_ok"),
            "scheduler_planner_gateway_used": payload.get("scheduler_planner_gateway_used"),
            "scheduler_planner_legacy_fallback_used": payload.get(
                "scheduler_planner_legacy_fallback_used"
            ),
        },
    }


def _gateway_first_or_legacy(raw_plan: Any, request: Dict[str, Any], user_input: str) -> Any:
    try:
        gateway_result = run_scheduler_planner_gateway(
            lambda _request, _raw_plan=raw_plan: _raw_plan,
            request,
            legacy_payload=raw_plan if isinstance(raw_plan, dict) else None,
            allow_legacy_fallback=True,
        )
    except Exception:
        return raw_plan

    gateway_plan = _contract_payload_to_external_plan(
        getattr(gateway_result, "payload", None),
        user_input,
    )
    if isinstance(gateway_plan, dict):
        return gateway_plan

    # Compatibility rule: legacy external plans keep their original shape
    # until the downstream scheduler normalizer is fully migrated.
    return raw_plan
