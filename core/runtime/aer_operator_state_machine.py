from __future__ import annotations

from typing import Any, Dict, List

from core.runtime.aer_operator_lifecycle import (
    AER_OPERATOR_LIFECYCLE_CONTRACT,
    OPERATOR_ALLOWED_TRANSITIONS,
    OPERATOR_PHASES,
    is_operator_terminal_phase,
    normalize_operator_phase,
    validate_operator_lifecycle_record,
)

AER_OPERATOR_STATE_MACHINE_CONTRACT = "aer.operator_state_machine.v2"
AER_OPERATOR_TRANSITION_CONTRACT = "aer.operator_transition.v2"


def can_transition(from_phase: Any, to_phase: Any) -> bool:
    source = normalize_operator_phase(from_phase)
    target = normalize_operator_phase(to_phase)
    return target in OPERATOR_ALLOWED_TRANSITIONS.get(source, ())


def build_transition_record(
    *,
    operator_session_id: str,
    package_id: str,
    from_phase: str,
    to_phase: str,
    reason: str = "",
    sequence: int = 0,
) -> Dict[str, Any]:
    return {
        "contract": AER_OPERATOR_TRANSITION_CONTRACT,
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "from_phase": normalize_operator_phase(from_phase),
        "to_phase": normalize_operator_phase(to_phase),
        "reason": str(reason or ""),
        "sequence": int(sequence or 0),
        "allowed": can_transition(from_phase, to_phase),
    }


def validate_transition_record(payload: Any) -> Dict[str, Any]:
    errors = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "contract": AER_OPERATOR_TRANSITION_CONTRACT,
            "errors": ["payload must be a dict"],
        }

    required_fields = (
        "contract",
        "operator_session_id",
        "package_id",
        "from_phase",
        "to_phase",
        "reason",
        "sequence",
        "allowed",
    )

    for field in required_fields:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("contract") != AER_OPERATOR_TRANSITION_CONTRACT:
        errors.append("invalid contract")

    if not str(payload.get("operator_session_id") or "").strip():
        errors.append("operator_session_id is required")

    if not str(payload.get("package_id") or "").strip():
        errors.append("package_id is required")

    from_phase = payload.get("from_phase")
    to_phase = payload.get("to_phase")

    if from_phase not in OPERATOR_PHASES:
        errors.append(f"invalid from_phase: {from_phase}")

    if to_phase not in OPERATOR_PHASES:
        errors.append(f"invalid to_phase: {to_phase}")

    try:
        sequence = int(payload.get("sequence"))
        if sequence < 0:
            errors.append("sequence must be >= 0")
    except Exception:
        errors.append("sequence must be an int")

    expected_allowed = (
        can_transition(from_phase, to_phase)
        if from_phase in OPERATOR_PHASES and to_phase in OPERATOR_PHASES
        else False
    )

    if payload.get("allowed") is not expected_allowed:
        errors.append("allowed flag mismatch")

    if expected_allowed is False:
        errors.append(f"transition not allowed: {from_phase} -> {to_phase}")

    return {
        "ok": not errors,
        "contract": AER_OPERATOR_TRANSITION_CONTRACT,
        "errors": errors,
    }


def append_transition_history(
    record: Dict[str, Any],
    transition: Dict[str, Any],
) -> Dict[str, Any]:
    next_record = dict(record)
    history = list(next_record.get("transition_history") or [])
    history.append(dict(transition))
    next_record["transition_history"] = history
    return next_record


def advance_operator_lifecycle(
    record: Dict[str, Any],
    next_phase: str,
    *,
    reason: str = "",
) -> Dict[str, Any]:
    validation = validate_operator_lifecycle_record(record)
    if validation["ok"] is not True:
        return {
            "ok": False,
            "contract": AER_OPERATOR_STATE_MACHINE_CONTRACT,
            "record": dict(record),
            "transition": {},
            "errors": list(validation["errors"]),
        }

    current_phase = normalize_operator_phase(record.get("phase"))
    target_phase = normalize_operator_phase(next_phase)

    sequence = len(record.get("transition_history") or [])
    transition = build_transition_record(
        operator_session_id=str(record.get("operator_session_id") or ""),
        package_id=str(record.get("package_id") or ""),
        from_phase=current_phase,
        to_phase=target_phase,
        reason=reason,
        sequence=sequence,
    )

    transition_validation = validate_transition_record(transition)
    if transition_validation["ok"] is not True:
        return {
            "ok": False,
            "contract": AER_OPERATOR_STATE_MACHINE_CONTRACT,
            "record": dict(record),
            "transition": transition,
            "errors": list(transition_validation["errors"]),
        }

    next_record = dict(record)
    next_record["previous_phase"] = current_phase
    next_record["phase"] = target_phase
    next_record["transition_reason"] = str(reason or "")
    next_record = append_transition_history(next_record, transition)

    return {
        "ok": True,
        "contract": AER_OPERATOR_STATE_MACHINE_CONTRACT,
        "record": next_record,
        "transition": transition,
        "errors": [],
    }


def transition_history(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [dict(item) for item in list(record.get("transition_history") or [])]


def terminal_reason(record: Dict[str, Any]) -> str:
    phase = normalize_operator_phase(record.get("phase"))
    if not is_operator_terminal_phase(phase):
        return ""
    return str(record.get("transition_reason") or phase)