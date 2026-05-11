from __future__ import annotations

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_repair_suggestion import build_runtime_repair_suggestion
from core.tasks.runtime_state_hygiene import freeze_runtime_export


LOW_RISK_ACTIONS = [
    "inspect_runtime_evidence",
    "read_execution_log",
    "read_trace",
    "read_runtime_state",
]

MEDIUM_RISK_ACTIONS = [
    "prepare_repair_plan",
    "prepare_patch_preview",
    "prepare_retry_plan",
]

HIGH_RISK_ACTIONS = [
    "apply_patch",
    "write_file",
    "run_command",
    "rerun_task",
    "enqueue_repair_task",
]


def build_runtime_repair_contract(snapshot_or_suggestion: Any) -> Dict[str, Any]:
    """Build a read-only repair contract from a snapshot or repair suggestion.

    The contract is intentionally deterministic and non-executing. It does not
    schedule tasks, call tools, write files, mutate runtime state, or perform the
    repair. Its job is to define the safety boundary that a later repair bridge
    must obey.
    """
    suggestion = _ensure_suggestion(snapshot_or_suggestion)
    raw_suggestion = freeze_runtime_export(suggestion)

    suggestion_type = _first_nonempty(suggestion.get("suggestion_type"), "unknown")
    severity = _first_nonempty(suggestion.get("severity"), "low").lower()
    task_id = _first_nonempty(suggestion.get("task_id"))
    status = _first_nonempty(suggestion.get("status"), "unknown")
    retry_recommended = bool(suggestion.get("retry_recommended"))
    inspection_targets = _list_of_strings(suggestion.get("recommended_inspection"))

    risk = _classify_repair_risk(
        suggestion_type=suggestion_type,
        severity=severity,
        retry_recommended=retry_recommended,
    )
    scope = _classify_repair_scope(suggestion_type=suggestion_type)
    budget = _build_repair_budget(risk=risk, retry_recommended=retry_recommended)
    allowed_actions = _allowed_actions_for_risk(risk)
    confirmation_required = _confirmation_required(risk=risk, suggestion_type=suggestion_type)

    return {
        "ok": True,
        "contract_type": "runtime_repair_contract_v1",
        "task_id": task_id,
        "status": status,
        "suggestion_type": suggestion_type,
        "suggestion_severity": severity,
        "repair_scope": scope,
        "repair_risk": risk,
        "repair_budget": budget,
        "repair_allowed_actions": allowed_actions,
        "repair_confirmation_required": confirmation_required,
        "repair_retry_policy": _build_retry_policy(
            retry_recommended=retry_recommended,
            risk=risk,
            suggestion_type=suggestion_type,
        ),
        "recommended_inspection": inspection_targets,
        "reason": _first_nonempty(suggestion.get("reason"), suggestion.get("human_summary")),
        "human_summary": _build_human_summary(
            suggestion_type=suggestion_type,
            risk=risk,
            scope=scope,
            confirmation_required=confirmation_required,
            inspection_targets=inspection_targets,
        ),
        "raw_suggestion": raw_suggestion,
    }


def build_runtime_repair_contracts(snapshot_or_suggestion: Any) -> List[Dict[str, Any]]:
    """Return a list wrapper for future multi-contract flows."""
    return [build_runtime_repair_contract(snapshot_or_suggestion)]


def validate_runtime_repair_contract(contract: Any) -> Dict[str, Any]:
    """Validate contract shape without executing anything."""
    if not isinstance(contract, Mapping):
        return {"ok": False, "error": "contract must be a mapping"}

    required = [
        "contract_type",
        "repair_scope",
        "repair_risk",
        "repair_budget",
        "repair_allowed_actions",
        "repair_confirmation_required",
        "repair_retry_policy",
    ]
    missing = [key for key in required if key not in contract]
    if missing:
        return {"ok": False, "error": "missing required contract fields", "missing": missing}

    risk = _first_nonempty(contract.get("repair_risk")).lower()
    if risk not in {"none", "low", "medium", "high"}:
        return {"ok": False, "error": "invalid repair_risk", "repair_risk": risk}

    allowed_actions = contract.get("repair_allowed_actions")
    if not isinstance(allowed_actions, list):
        return {"ok": False, "error": "repair_allowed_actions must be a list"}

    retry_policy = contract.get("repair_retry_policy")
    if not isinstance(retry_policy, Mapping):
        return {"ok": False, "error": "repair_retry_policy must be a mapping"}

    budget = contract.get("repair_budget")
    if not isinstance(budget, Mapping):
        return {"ok": False, "error": "repair_budget must be a mapping"}

    return {"ok": True, "error": ""}


def _ensure_suggestion(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping) and "suggestion_type" in value:
        return dict(value)
    suggestion = build_runtime_repair_suggestion(value)
    if isinstance(suggestion, Mapping):
        return dict(suggestion)
    return {
        "ok": False,
        "suggestion_type": "invalid_suggestion",
        "severity": "low",
        "reason": "runtime repair suggestion builder returned non-mapping",
        "recommended_inspection": [],
        "retry_recommended": False,
        "human_summary": "No valid repair suggestion was produced.",
        "task_id": "",
        "status": "unknown",
    }


def _classify_repair_scope(*, suggestion_type: str) -> str:
    lowered = suggestion_type.lower()
    if lowered in {"no_repair_needed", "observe_running_task", "insufficient_runtime_evidence"}:
        return "observe_only"
    if lowered == "blocked_task":
        return "blocker_resolution"
    if "verification" in lowered or "verify" in lowered:
        return "verification_review"
    if "file_operation" in lowered or "path" in lowered or "file" in lowered:
        return "file_operation_review"
    if "python" in lowered:
        return "code_execution_review"
    if "repair" in lowered:
        return "repair_attempt_review"
    return "runtime_failure_review"


def _classify_repair_risk(*, suggestion_type: str, severity: str, retry_recommended: bool) -> str:
    lowered = suggestion_type.lower()
    if lowered == "no_repair_needed":
        return "none"
    if lowered in {"observe_running_task", "insufficient_runtime_evidence"}:
        return "low"
    if lowered == "blocked_task":
        return "medium"
    if severity == "high":
        return "high"
    if retry_recommended:
        return "medium"
    if severity == "medium":
        return "medium"
    return "low"


def _build_repair_budget(*, risk: str, retry_recommended: bool) -> Dict[str, Any]:
    if risk == "none":
        return {
            "max_repair_tasks": 0,
            "max_write_actions": 0,
            "max_command_actions": 0,
            "max_retry_attempts": 0,
            "requires_manual_review_before_execution": False,
        }
    if risk == "low":
        return {
            "max_repair_tasks": 0,
            "max_write_actions": 0,
            "max_command_actions": 0,
            "max_retry_attempts": 0,
            "requires_manual_review_before_execution": True,
        }
    if risk == "medium":
        return {
            "max_repair_tasks": 1,
            "max_write_actions": 0,
            "max_command_actions": 0,
            "max_retry_attempts": 1 if retry_recommended else 0,
            "requires_manual_review_before_execution": True,
        }
    return {
        "max_repair_tasks": 1,
        "max_write_actions": 0,
        "max_command_actions": 0,
        "max_retry_attempts": 0,
        "requires_manual_review_before_execution": True,
    }


def _allowed_actions_for_risk(risk: str) -> List[str]:
    if risk == "none":
        return ["inspect_runtime_evidence"]
    if risk == "low":
        return list(LOW_RISK_ACTIONS)
    if risk == "medium":
        return list(LOW_RISK_ACTIONS + MEDIUM_RISK_ACTIONS)
    if risk == "high":
        return list(LOW_RISK_ACTIONS + ["prepare_repair_plan", "prepare_patch_preview"])
    return list(LOW_RISK_ACTIONS)


def _confirmation_required(*, risk: str, suggestion_type: str) -> bool:
    if risk in {"medium", "high"}:
        return True
    if suggestion_type.lower() in {"blocked_task", "inspect_repair_attempt"}:
        return True
    return False


def _build_retry_policy(*, retry_recommended: bool, risk: str, suggestion_type: str) -> Dict[str, Any]:
    if risk in {"none", "low", "high"}:
        max_attempts = 0
    else:
        max_attempts = 1 if retry_recommended else 0

    return {
        "retry_recommended": bool(retry_recommended and max_attempts > 0),
        "max_attempts": max_attempts,
        "requires_fresh_snapshot": True,
        "requires_contract_revalidation": True,
        "blocked_for_types": _blocked_retry_types(suggestion_type=suggestion_type, risk=risk),
    }


def _blocked_retry_types(*, suggestion_type: str, risk: str) -> List[str]:
    blocked = []
    lowered = suggestion_type.lower()
    if risk == "high":
        blocked.append("high_risk_failure")
    if lowered in {"blocked_task", "inspect_repair_attempt", "no_repair_needed"}:
        blocked.append(lowered)
    return blocked


def _build_human_summary(
    *,
    suggestion_type: str,
    risk: str,
    scope: str,
    confirmation_required: bool,
    inspection_targets: List[str],
) -> str:
    inspect = ", ".join(inspection_targets) if inspection_targets else "runtime evidence"
    confirmation = "Manual confirmation is required" if confirmation_required else "Manual confirmation is not required for observation"
    return (
        f"Repair contract for {suggestion_type}: scope={scope}, risk={risk}. "
        f"Inspect {inspect}. {confirmation} before any mutating repair action."
    )


def _list_of_strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
