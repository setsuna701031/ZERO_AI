from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_state_hygiene import freeze_runtime_export


DEFAULT_READ_ONLY_ACTIONS = [
    "inspect_runtime_state",
    "inspect_execution_log",
    "inspect_trace",
]

SAFE_REPAIR_ACTIONS = [
    "inspect_runtime_state",
    "inspect_execution_log",
    "inspect_trace",
    "inspect_result",
    "propose_repair_plan",
]

CODE_REPAIR_ACTIONS = [
    "inspect_runtime_state",
    "inspect_execution_log",
    "inspect_trace",
    "inspect_result",
    "propose_repair_plan",
    "prepare_code_repair",
]

BLOCKED_MUTATING_ACTIONS = [
    "execute_repair",
    "apply_patch",
    "write_file",
    "delete_file",
    "run_shell_command",
    "schedule_task",
    "modify_scheduler",
    "modify_planner",
]

PROTECTED_SCOPES = {
    "core",
    "scheduler",
    "planner",
    "system",
    "unknown",
}


def build_runtime_repair_envelope(
    suggestion: Any,
    contract: Any = None,
) -> Dict[str, Any]:
    """Build a read-only repair planning envelope from suggestion + contract.

    This layer is intentionally deterministic and side-effect free. It does not
    create tasks, call tools, write files, invoke LLMs, or mutate the supplied
    suggestion/contract. The envelope is a governance boundary for later
    planner-bridge work.
    """
    safe_suggestion = suggestion if isinstance(suggestion, Mapping) else {}
    safe_contract = contract if isinstance(contract, Mapping) else {}

    suggestion_type = _first_nonempty(safe_suggestion.get("suggestion_type"), "unknown_suggestion")
    severity = _first_nonempty(safe_suggestion.get("severity"), "low").lower()
    task_id = _first_nonempty(safe_suggestion.get("task_id"))
    status = _first_nonempty(safe_suggestion.get("status"), "unknown")
    reason = _first_nonempty(safe_suggestion.get("reason"), safe_contract.get("reason"), "runtime repair envelope generated")

    contract_scope = _first_nonempty(
        safe_contract.get("repair_scope"),
        safe_contract.get("scope"),
        safe_contract.get("target_scope"),
        "unknown",
    )
    contract_risk = _first_nonempty(
        safe_contract.get("repair_risk"),
        safe_contract.get("risk"),
        safe_contract.get("risk_level"),
        "",
    ).lower()

    repair_scope = _resolve_repair_scope(suggestion_type, contract_scope)
    repair_risk = _resolve_repair_risk(
        suggestion_type=suggestion_type,
        severity=severity,
        contract_risk=contract_risk,
        repair_scope=repair_scope,
    )
    repair_mode = _resolve_repair_mode(
        suggestion_type=suggestion_type,
        repair_risk=repair_risk,
        repair_scope=repair_scope,
    )
    retry_recommended = bool(safe_suggestion.get("retry_recommended", False))
    max_retry = _resolve_max_retry(
        retry_recommended=retry_recommended,
        repair_risk=repair_risk,
        contract=safe_contract,
    )
    requires_confirmation = _requires_confirmation(
        repair_mode=repair_mode,
        repair_risk=repair_risk,
        contract=safe_contract,
    )

    allowed_actions = _merge_allowed_actions(
        suggestion_type=suggestion_type,
        repair_mode=repair_mode,
        contract=safe_contract,
    )
    blocked_actions = _merge_blocked_actions(
        repair_risk=repair_risk,
        repair_scope=repair_scope,
        contract=safe_contract,
    )
    inspection_targets = _string_list(
        safe_suggestion.get("recommended_inspection"),
        fallback=["runtime_state.json", "trace.json"],
    )

    return {
        "ok": True,
        "task_id": task_id,
        "status": status,
        "repair_mode": repair_mode,
        "repair_scope": repair_scope,
        "repair_risk": repair_risk,
        "requires_confirmation": requires_confirmation,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "max_retry": max_retry,
        "retry_recommended": retry_recommended,
        "inspection_targets": inspection_targets,
        "suggestion_type": suggestion_type,
        "severity": severity,
        "reason": reason,
        "human_summary": _build_human_summary(
            suggestion_type=suggestion_type,
            repair_mode=repair_mode,
            repair_risk=repair_risk,
            repair_scope=repair_scope,
            requires_confirmation=requires_confirmation,
            max_retry=max_retry,
        ),
        "raw_suggestion": freeze_runtime_export(suggestion),
        "raw_contract": freeze_runtime_export(contract),
    }


def build_runtime_repair_envelopes(
    suggestions: Any,
    contract: Any = None,
) -> List[Dict[str, Any]]:
    """Build envelopes for a single suggestion or a list of suggestions."""
    if isinstance(suggestions, list):
        return [build_runtime_repair_envelope(item, contract=contract) for item in suggestions]
    return [build_runtime_repair_envelope(suggestions, contract=contract)]


def _resolve_repair_scope(suggestion_type: str, contract_scope: str) -> str:
    scope = _safe_lower(contract_scope)
    if scope and scope != "unknown":
        return scope

    lowered = _safe_lower(suggestion_type)
    if "python" in lowered or "code" in lowered:
        return "code"
    if "file" in lowered or "path" in lowered or "write" in lowered:
        return "file_operation"
    if "verify" in lowered or "verification" in lowered:
        return "verification"
    if "blocked" in lowered:
        return "blocker"
    if "no_repair" in lowered or "observe" in lowered:
        return "read_only"
    return "unknown"


def _resolve_repair_risk(
    *,
    suggestion_type: str,
    severity: str,
    contract_risk: str,
    repair_scope: str,
) -> str:
    risk = _safe_lower(contract_risk)
    if risk in {"low", "medium", "high", "critical"}:
        return risk

    lowered = _safe_lower(suggestion_type)
    if "no_repair" in lowered or "observe" in lowered:
        return "low"
    if repair_scope in PROTECTED_SCOPES:
        return "high"
    if severity in {"high", "critical"}:
        return "high"
    if severity == "medium":
        return "medium"
    return "low"


def _resolve_repair_mode(*, suggestion_type: str, repair_risk: str, repair_scope: str) -> str:
    lowered = _safe_lower(suggestion_type)
    if "no_repair" in lowered:
        return "no_repair"
    if "observe" in lowered:
        return "observe_only"
    if repair_risk in {"high", "critical"} or repair_scope in PROTECTED_SCOPES:
        return "manual_review"
    return "guided_repair_plan"


def _resolve_max_retry(*, retry_recommended: bool, repair_risk: str, contract: Mapping[str, Any]) -> int:
    raw = _first_nonempty(
        contract.get("max_retry"),
        contract.get("max_retries"),
        contract.get("repair_budget"),
        "",
    )
    try:
        value = int(raw)
        return max(0, min(value, 3))
    except Exception:
        pass

    if not retry_recommended:
        return 0
    if repair_risk in {"high", "critical"}:
        return 0
    if repair_risk == "medium":
        return 1
    return 2


def _requires_confirmation(*, repair_mode: str, repair_risk: str, contract: Mapping[str, Any]) -> bool:
    raw = contract.get("requires_confirmation")
    if isinstance(raw, bool):
        return raw
    raw = contract.get("repair_confirmation_required")
    if isinstance(raw, bool):
        return raw

    if repair_mode in {"manual_review", "guided_repair_plan"}:
        return True
    if repair_risk in {"medium", "high", "critical"}:
        return True
    return False


def _merge_allowed_actions(*, suggestion_type: str, repair_mode: str, contract: Mapping[str, Any]) -> List[str]:
    contract_actions = _string_list(contract.get("allowed_actions"), fallback=[])
    if contract_actions:
        return _unique(contract_actions)

    if repair_mode in {"no_repair", "observe_only"}:
        return list(DEFAULT_READ_ONLY_ACTIONS)

    lowered = _safe_lower(suggestion_type)
    if "python" in lowered or "code" in lowered:
        return list(CODE_REPAIR_ACTIONS)
    return list(SAFE_REPAIR_ACTIONS)


def _merge_blocked_actions(*, repair_risk: str, repair_scope: str, contract: Mapping[str, Any]) -> List[str]:
    blocked = list(BLOCKED_MUTATING_ACTIONS)
    blocked.extend(_string_list(contract.get("blocked_actions"), fallback=[]))

    if repair_risk in {"high", "critical"} or repair_scope in PROTECTED_SCOPES:
        blocked.extend(["auto_retry", "auto_repair", "auto_apply_patch"])
    else:
        blocked.extend(["auto_apply_patch", "auto_repair_without_confirmation"])

    return _unique(blocked)


def _build_human_summary(
    *,
    suggestion_type: str,
    repair_mode: str,
    repair_risk: str,
    repair_scope: str,
    requires_confirmation: bool,
    max_retry: int,
) -> str:
    confirmation = "requires confirmation" if requires_confirmation else "does not require confirmation"
    return (
        f"Repair envelope for {suggestion_type}: mode={repair_mode}, "
        f"scope={repair_scope}, risk={repair_risk}, max_retry={max_retry}, {confirmation}."
    )


def _string_list(value: Any, *, fallback: Optional[List[str]] = None) -> List[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item or "").strip()]
        return _unique(items)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return list(fallback or [])


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _safe_lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
