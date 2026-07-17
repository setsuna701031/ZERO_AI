from __future__ import annotations

import copy
from typing import Any

from core.runtime.runtime_recovery_plan import stable_recovery_fingerprint, utc_timestamp


def reconstruct_runtime_incident(
    *,
    recovery_id: str,
    source_failure: dict[str, Any],
    recovery_plan: dict[str, Any],
    replay_reference: dict[str, Any] | None = None,
    rollback_reference: dict[str, Any] | None = None,
    verification_result: dict[str, Any] | None = None,
    audit_events: list[dict[str, Any]] | None = None,
    journal_reconstruction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failure = copy.deepcopy(source_failure if isinstance(source_failure, dict) else {})
    plan = copy.deepcopy(recovery_plan if isinstance(recovery_plan, dict) else {})
    replay = copy.deepcopy(replay_reference or {})
    rollback = copy.deepcopy(rollback_reference or {})
    verification = copy.deepcopy(verification_result or {})
    events = [copy.deepcopy(item) for item in (audit_events or []) if isinstance(item, dict)]
    journal = copy.deepcopy(journal_reconstruction or {})

    task_id = str(failure.get("task_id") or plan.get("task_id") or "").strip()
    source_session_id = str(
        failure.get("source_session_id")
        or plan.get("source_session_id")
        or replay.get("source_session_id")
        or ""
    ).strip()
    failure_type = str(failure.get("failure_type") or "runtime_failure").strip()
    message = str(failure.get("message") or failure.get("failure_message") or failure_type).strip()
    status = str(verification.get("status") or plan.get("status") or "planned").strip()

    timeline = []
    if failure:
        timeline.append(
            {
                "phase": "failure_detected",
                "summary": message,
                "timestamp": failure.get("observed_at") or utc_timestamp(),
            }
        )
    if plan:
        timeline.append(
            {
                "phase": "recovery_planned",
                "summary": f"plan={plan.get('plan_id', '')} status={plan.get('status', '')}",
                "timestamp": plan.get("created_at") or utc_timestamp(),
            }
        )
    if replay:
        timeline.append(
            {
                "phase": "replay_attached",
                "summary": f"replay={replay.get('replay_id', replay.get('status', 'attached'))}",
                "timestamp": replay.get("created_at") or utc_timestamp(),
            }
        )
    if rollback:
        timeline.append(
            {
                "phase": "rollback_represented",
                "summary": f"rollback={rollback.get('mode', rollback.get('status', 'represented'))}",
                "timestamp": rollback.get("created_at") or utc_timestamp(),
            }
        )
    if verification:
        timeline.append(
            {
                "phase": "verification",
                "summary": str(verification.get("reason") or verification.get("status") or "verified"),
                "timestamp": verification.get("verified_at") or utc_timestamp(),
            }
        )

    summary_text = (
        f"Runtime recovery {recovery_id} handled {failure_type}: {message}. "
        f"Plan status={plan.get('status', '')}; verification status={status}."
    )

    incident_seed = {
        "recovery_id": recovery_id,
        "source_session_id": source_session_id,
        "failure_type": failure_type,
        "message": message,
    }
    return {
        "incident_id": "runtime-incident-" + stable_recovery_fingerprint(incident_seed)[:16],
        "recovery_id": str(recovery_id or ""),
        "runtime_phase": "runtime_incident_reconstruction",
        "task_id": task_id,
        "source_session_id": source_session_id,
        "failure_type": failure_type,
        "message": message,
        "status": status,
        "summary": summary_text,
        "timeline": timeline,
        "audit_event_count": len(events),
        "journal_record_count": int(journal.get("record_count") or 0) if isinstance(journal, dict) else 0,
        "has_replay": bool(replay),
        "rollback_required": bool(plan.get("rollback_required") or rollback),
        "verified": bool(verification.get("verified", False)),
        "source_failure": failure,
        "recovery_plan": plan,
        "replay_reference": replay,
        "rollback_reference": rollback,
        "verification_result": verification,
        "audit_events": events,
        "journal_reconstruction": journal,
        "reconstructed_at": utc_timestamp(),
    }


__all__ = ["reconstruct_runtime_incident"]
