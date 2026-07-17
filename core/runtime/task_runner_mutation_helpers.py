from __future__ import annotations

import copy
from typing import Any, Callable, Dict


RuntimeStepTarget = Callable[[Any], str]


def build_repair_replay_validation(
    *,
    step: Any,
    step_result: Dict[str, Any],
    mutation_result: Dict[str, Any],
    step_index: int,
    current_tick: int,
    trace_tick: int,
    runtime_step_target: RuntimeStepTarget,
) -> Dict[str, Any]:
    mutation_status = ""
    verification_ok = None
    replay_verified = None
    mutation_id = ""

    if isinstance(mutation_result, dict):
        mutation_id = str(mutation_result.get("mutation_id") or "")
        mutation_status = str(mutation_result.get("status") or "").strip()
        verification = mutation_result.get("verification")
        if isinstance(verification, dict):
            verification_ok = bool(verification.get("ok"))
            replay_verified = bool(verification.get("replay_verified"))

    step_ok = bool(step_result.get("ok")) if isinstance(step_result, dict) else False
    reproducible = bool(step_ok and mutation_status == "verified" and verification_ok and replay_verified)

    if mutation_status == "rolled_back":
        replay_status = "rolled_back_not_reproducible"
    elif reproducible:
        replay_status = "replay_verified"
    elif mutation_status == "verified" and verification_ok and replay_verified is False:
        replay_status = "verification_ok_replay_failed"
    elif mutation_status == "verified" and verification_ok is False:
        replay_status = "verification_failed"
    elif not step_ok:
        replay_status = "step_failed"
    else:
        replay_status = "unknown"

    return {
        "enabled": True,
        "schema": "zero.repair_replay_validation.v1",
        "mutation_id": mutation_id,
        "step_type": str(step.get("type") or step.get("action") or "").strip().lower() if isinstance(step, dict) else "",
        "target": runtime_step_target(step),
        "step_ok": step_ok,
        "mutation_status": mutation_status,
        "verification_ok": verification_ok,
        "replay_verified": replay_verified,
        "reproducible": reproducible,
        "status": replay_status,
        "step_index": int(step_index),
        "current_tick": current_tick,
        "trace_tick": trace_tick,
    }


def reconcile_mutation_boundary_result(
    *,
    step: Any,
    step_result: Dict[str, Any],
    mutation_result: Dict[str, Any],
    step_index: int,
    current_tick: int,
    trace_tick: int,
) -> Dict[str, Any]:
    normalized = copy.deepcopy(step_result if isinstance(step_result, dict) else {})
    boundary = mutation_result if isinstance(mutation_result, dict) else {}

    if not boundary.get("mutation_recorded"):
        normalized["mutation_reconciliation"] = {
            "enabled": False,
            "status": "not_recorded",
            "reason": str(boundary.get("reason") or boundary.get("error") or "mutation not recorded"),
            "step_index": int(step_index),
            "tick": trace_tick if trace_tick is not None else current_tick,
        }
        return normalized

    mutation_status = str(boundary.get("status") or "").strip().lower()
    step_ok = bool(normalized.get("ok", False))
    verification = boundary.get("verification") if isinstance(boundary.get("verification"), dict) else {}
    rollback = boundary.get("rollback") if isinstance(boundary.get("rollback"), dict) else {}
    rollback_completed = bool(rollback.get("rolled_back") or mutation_status == "rolled_back")
    verified = bool(verification.get("ok") or mutation_status == "verified")

    if verified and step_ok:
        reconciled_status = "verified"
        runtime_status_hint = "finished"
        final_ok = True
        message = "mutation step verified"
    elif rollback_completed:
        reconciled_status = "failed_rolled_back"
        runtime_status_hint = "failed"
        final_ok = False
        message = "mutation step failed; rollback completed"
    elif mutation_status in {"apply_failed", "verification_failed"}:
        reconciled_status = mutation_status
        runtime_status_hint = "failed"
        final_ok = False
        message = "mutation step failed before successful verification"
    elif step_ok and mutation_status:
        reconciled_status = mutation_status
        runtime_status_hint = "running"
        final_ok = step_ok
        message = "mutation boundary recorded"
    else:
        reconciled_status = mutation_status or "unknown"
        runtime_status_hint = "failed" if not step_ok else "running"
        final_ok = step_ok
        message = "mutation boundary recorded with unresolved status"

    reconciliation = {
        "enabled": True,
        "status": reconciled_status,
        "runtime_status_hint": runtime_status_hint,
        "step_ok": step_ok,
        "final_ok": final_ok,
        "mutation_status": mutation_status,
        "verified": verified,
        "rollback_completed": rollback_completed,
        "step_index": int(step_index),
        "tick": trace_tick if trace_tick is not None else current_tick,
        "message": message,
    }
    normalized["mutation_reconciliation"] = reconciliation

    boundary = copy.deepcopy(boundary)
    boundary["runtime_reconciliation"] = copy.deepcopy(reconciliation)
    normalized["mutation_boundary"] = boundary

    if rollback_completed and not step_ok:
        normalized["ok"] = False
        normalized["message"] = message
        normalized["final_answer"] = message
        original_error = normalized.get("error")
        error_payload = {
            "type": "mutation_rolled_back_after_failure",
            "message": message,
            "retryable": False,
            "details": {
                "mutation_boundary_status": mutation_status,
                "mutation_reconciliation_status": reconciled_status,
                "rollback_completed": True,
            },
        }
        if isinstance(original_error, dict):
            error_payload = copy.deepcopy(original_error)
            error_payload["type"] = str(error_payload.get("type") or "mutation_rolled_back_after_failure")
            error_payload["message"] = str(error_payload.get("message") or message)
            error_payload["retryable"] = bool(error_payload.get("retryable", False))
            if not isinstance(error_payload.get("details"), dict):
                error_payload["details"] = {}
            error_payload["details"]["mutation_boundary_status"] = mutation_status
            error_payload["details"]["mutation_reconciliation_status"] = reconciled_status
            error_payload["details"]["rollback_completed"] = True
            normalized["error"] = error_payload
        else:
            raw_error = str(original_error or "").strip()
            if raw_error:
                normalized["error"] = raw_error
                error_payload["details"]["original_error"] = raw_error
            else:
                normalized["error"] = message
        normalized["mutation_rollback_error"] = error_payload

    return normalized


__all__ = [
    "build_repair_replay_validation",
    "reconcile_mutation_boundary_result",
]
