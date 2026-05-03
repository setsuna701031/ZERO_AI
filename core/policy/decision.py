from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Dict


POLICY_DECISIONS = {"allow", "deny", "require_confirm", "unknown"}


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    reason: str = ""
    source: str = ""
    hint: Any = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        decision = str(payload.get("decision") or "").strip().lower()
        payload["decision"] = decision if decision in POLICY_DECISIONS else "unknown"
        return payload


def unknown_policy_decision(reason: str = "", source: str = "policy.unknown", hint: Any = None) -> Dict[str, Any]:
    return PolicyDecision(
        decision="unknown",
        reason=str(reason or "no policy decision available"),
        source=str(source or "policy.unknown"),
        hint=copy.deepcopy(hint),
    ).to_dict()


def decision_from_guard_result(
    guard_result: Dict[str, Any],
    *,
    hint: Any = None,
    source: str = "ExecutionGuard.check_step",
) -> Dict[str, Any]:
    if not isinstance(guard_result, dict):
        return unknown_policy_decision(
            reason="guard returned non-dict result",
            source=source,
            hint=hint,
        )

    ok = bool(guard_result.get("ok"))
    if ok:
        reason = str(guard_result.get("guard_mode") or "guard allowed step")
        decision = "allow"
    else:
        reason = str(guard_result.get("error") or "guard denied step")
        decision = "deny"

    return PolicyDecision(
        decision=decision,
        reason=reason,
        source=str(source or "ExecutionGuard.check_step"),
        hint=copy.deepcopy(hint),
    ).to_dict()


def policy_hint_for_step(step: Dict[str, Any]) -> Dict[str, Any]:
    payload = step if isinstance(step, dict) else {}
    step_type = str(payload.get("type") or "unknown").strip().lower() or "unknown"
    raw_path = str(payload.get("path") or payload.get("target_path") or "").strip()
    command = str(payload.get("command") or "").strip()

    side_effect = "none"
    risk = "low"
    if step_type in {"write_file", "ensure_file"}:
        side_effect = "workspace_write"
        risk = "medium"
    elif step_type in {"command", "run_python"}:
        side_effect = "process_execution"
        risk = "high"
    elif step_type in {"read_file", "verify", "verify_file"}:
        side_effect = "read"
        risk = "low"

    return {
        "step_type": step_type,
        "risk": risk,
        "side_effect": side_effect,
        "path": raw_path,
        "has_command": bool(command),
    }
