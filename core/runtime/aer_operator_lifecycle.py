from __future__ import annotations

from typing import Any, Dict, Tuple

AER_OPERATOR_LIFECYCLE_CONTRACT = "aer.operator_lifecycle.v2"

OPERATOR_PHASES: Tuple[str, ...] = (
    "initialized",
    "admitted",
    "running",
    "checkpointed",
    "waiting_approval",
    "resumed",
    "completed",
    "failed",
    "blocked",
)

OPERATOR_TERMINAL_PHASES: Tuple[str, ...] = (
    "completed",
    "failed",
    "blocked",
)

OPERATOR_ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "initialized": ("admitted", "blocked", "failed"),
    "admitted": ("running", "blocked", "failed"),
    "running": (
        "checkpointed",
        "waiting_approval",
        "completed",
        "blocked",
        "failed",
    ),
    "checkpointed": ("running", "resumed", "completed", "blocked", "failed"),
    "waiting_approval": ("running", "blocked", "failed"),
    "resumed": ("running", "checkpointed", "completed", "blocked", "failed"),
    "completed": (),
    "failed": (),
    "blocked": (),
}


def normalize_operator_phase(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in OPERATOR_PHASES:
        return text
    return "initialized"


def is_operator_terminal_phase(value: Any) -> bool:
    return normalize_operator_phase(value) in OPERATOR_TERMINAL_PHASES


def can_transition_operator_phase(from_phase: Any, to_phase: Any) -> bool:
    source = normalize_operator_phase(from_phase)
    target = normalize_operator_phase(to_phase)
    return target in OPERATOR_ALLOWED_TRANSITIONS.get(source, ())


def build_operator_lifecycle_record(
    *,
    operator_session_id: str,
    package_id: str,
    phase: str = "initialized",
    previous_phase: str = "",
    transition_reason: str = "",
) -> Dict[str, Any]:
    return {
        "contract": AER_OPERATOR_LIFECYCLE_CONTRACT,
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "phase": normalize_operator_phase(phase),
        "previous_phase": str(previous_phase or ""),
        "transition_reason": str(transition_reason or ""),
    }


def validate_operator_lifecycle_record(payload: Any) -> Dict[str, Any]:
    errors = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "contract": AER_OPERATOR_LIFECYCLE_CONTRACT,
            "errors": ["payload must be a dict"],
        }

    required_fields = (
        "contract",
        "operator_session_id",
        "package_id",
        "phase",
        "previous_phase",
        "transition_reason",
    )

    for field in required_fields:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("contract") != AER_OPERATOR_LIFECYCLE_CONTRACT:
        errors.append("invalid contract")

    if not str(payload.get("operator_session_id") or "").strip():
        errors.append("operator_session_id is required")

    if not str(payload.get("package_id") or "").strip():
        errors.append("package_id is required")

    phase = payload.get("phase")
    if phase not in OPERATOR_PHASES:
        errors.append(f"invalid phase: {phase}")

    previous_phase = str(payload.get("previous_phase") or "").strip()
    if previous_phase:
        if previous_phase not in OPERATOR_PHASES:
            errors.append(f"invalid previous_phase: {previous_phase}")
        elif phase in OPERATOR_PHASES and not can_transition_operator_phase(previous_phase, phase):
            errors.append(f"invalid transition: {previous_phase} -> {phase}")

    return {
        "ok": not errors,
        "contract": AER_OPERATOR_LIFECYCLE_CONTRACT,
        "errors": errors,
    }