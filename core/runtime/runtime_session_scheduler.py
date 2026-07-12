from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_end_to_end_orchestrator import cancel_runtime_session, resume_runtime_session
from core.runtime.runtime_operator_session import load_runtime_session, save_runtime_session, time_text
from core.runtime.runtime_session_queue import (TERMINAL, WAITING, enqueue_session, ordered_entries,
    rebuild_waiting_projection, seal_scheduler_state, update_entry_from_session, validate_scheduler_state)

LEASE_SECONDS = 30
MAX_LEASE_SECONDS = 60
SAFE_DISPATCH_STATUSES = {"created", "running"}

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _now(value: Any = None) -> datetime:
    text = time_text(value if value is not None else datetime.now(timezone.utc)); return datetime.fromisoformat(text)
def _entry(state: Mapping[str, Any], session_id: str) -> dict[str, Any]:
    found = next((item for item in state.get("entries", []) if item.get("session_id") == session_id), None)
    if found is None: raise ValueError("scheduled_session_not_found")
    return found

def recover_scheduler_state(state: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state); reasons = validate_scheduler_state(value)
    if reasons: raise ValueError(";".join(reasons))
    current = _now(now)
    for entry in value["entries"]:
        if entry.get("lease_status") == "active" and entry.get("lease_expires_at"):
            if current >= _now(entry["lease_expires_at"]):
                entry.update(lease_status="expired", lease_id="", lease_owner="", lease_acquired_at=None, lease_expires_at=None)
                entry["blocked_reasons"] = []
        path = Path(str(entry.get("session_path") or ""))
        if not path.exists(): entry["blocked_reasons"] = ["missing_session_path"]; entry["session_status"] = "blocked"; continue
        try: session = load_runtime_session(path, now=now)
        except ValueError as exc: entry["blocked_reasons"] = [str(exc)]; entry["session_status"] = "blocked"; continue
        refreshed = update_entry_from_session(entry, session, now=now); entry.clear(); entry.update(refreshed)
        if session.get("session_status") == "transaction_running" and not session.get("artifacts", {}).get("transaction_result"):
            entry["blocked_reasons"] = ["transaction_running_recovery_requires_evidence"]; entry["session_status"] = "blocked"
    return rebuild_waiting_projection(value, now=now)

def lease_next_session(state: Mapping[str, Any], *, owner: str, now: Any = None, lifetime_seconds: int = LEASE_SECONDS) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not str(owner).strip(): raise ValueError("lease_owner_required")
    if isinstance(lifetime_seconds, bool) or not 1 <= int(lifetime_seconds) <= MAX_LEASE_SECONDS: raise ValueError("invalid_lease_lifetime")
    value = recover_scheduler_state(state, now=now); current = _now(now)
    candidate = next((item for item in ordered_entries(value, include_terminal=False)
        if item.get("session_status") in SAFE_DISPATCH_STATUSES and item.get("lease_status") != "active"
        and _now(item.get("available_at")) <= current), None)
    if candidate is None: return value, None
    live = _entry(value, candidate["session_id"]); attempt = int(live.get("attempt_count", 0)) + 1
    seed = {"scheduler_id": value["scheduler_id"], "entry": live["queue_entry_id"], "owner": owner, "attempt": attempt, "acquired_at": time_text(now)}
    from core.runtime.runtime_operator_session import fingerprint
    lease = {"lease_id": f"session-lease-{fingerprint(seed)[:20]}", "session_id": live["session_id"],
        "queue_entry_id": live["queue_entry_id"], "lease_owner": owner, "acquired_at": time_text(now),
        "expires_at": time_text(current + timedelta(seconds=int(lifetime_seconds))), "lease_status": "active",
        "attempt_number": attempt, "scheduler_id": value["scheduler_id"], "mutation_authority": False}
    live.update(lease_status="active", lease_id=lease["lease_id"], lease_owner=owner, lease_acquired_at=lease["acquired_at"],
        lease_expires_at=lease["expires_at"], attempt_count=attempt); value["leases"].append(lease); value["scheduler_status"] = "running"
    return seal_scheduler_state(value), deepcopy(lease)

def release_session_lease(state: Mapping[str, Any], *, lease_id: str, owner: str, session_id: str, now: Any = None) -> dict[str, Any]:
    value = _mapping(state); entry = _entry(value, session_id)
    if entry.get("lease_status") != "active" or entry.get("lease_id") != lease_id: raise ValueError("invalid_lease_id")
    if entry.get("lease_owner") != owner: raise ValueError("lease_owner_mismatch")
    lease = next((item for item in value.get("leases", []) if item.get("lease_id") == lease_id), None)
    if not lease or lease.get("scheduler_id") != value.get("scheduler_id"): raise ValueError("lease_scheduler_mismatch")
    entry.update(lease_status="released", lease_id="", lease_owner="", lease_acquired_at=None, lease_expires_at=None)
    lease["lease_status"] = "released"; lease["released_at"] = time_text(now)
    value["scheduler_status"] = "idle"; return rebuild_waiting_projection(value, now=now)

def _terminal_lists(state: dict[str, Any], entry: Mapping[str, Any]) -> None:
    session_id, status = entry.get("session_id"), entry.get("session_status")
    target = "completed_sessions" if status == "completed" else "cancelled_sessions" if status == "cancelled" else "failed_sessions"
    if status in TERMINAL and session_id not in state[target]: state[target].append(session_id)

def dispatch_session(state: Mapping[str, Any], *, owner: str, target_root: Any, workspace_root: Any,
                     now: Any = None, lease_id: str | None = None, dispatch_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    value = _mapping(state)
    if dispatch_id and dispatch_id in value.get("processed_dispatch_ids", []): return value, {"duplicate": True, "dispatch_id": dispatch_id}
    lease = None
    if lease_id:
        lease = next((item for item in value.get("leases", []) if item.get("lease_id") == lease_id and item.get("lease_status") == "active"), None)
        if not lease or lease.get("lease_owner") != owner: raise ValueError("invalid_dispatch_lease")
    else: value, lease = lease_next_session(value, owner=owner, now=now)
    if lease is None: return value, {"dispatched": False, "reason": "no_dispatchable_session"}
    entry = _entry(value, lease["session_id"]); session = load_runtime_session(entry["session_path"], target_root=target_root, workspace_root=workspace_root, now=now)
    if session.get("session_status") in WAITING: raise ValueError("operator_input_required")
    try: result = resume_runtime_session(session, operator_input=None, target_root=target_root, workspace_root=workspace_root, now=now)
    except ValueError as exc:
        entry["blocked_reasons"] = [str(exc)]; result = session
    result = save_runtime_session(result, entry["session_path"]); refreshed = update_entry_from_session(entry, result, now=now); entry.clear(); entry.update(refreshed)
    identifier = dispatch_id or f"dispatch:{lease['lease_id']}"; entry["last_dispatch_id"] = identifier
    entry["last_result"] = {"session_status": result.get("session_status"), "current_phase": result.get("current_phase")}
    value.setdefault("processed_dispatch_ids", []).append(identifier); _terminal_lists(value, entry)
    value = release_session_lease(value, lease_id=lease["lease_id"], owner=owner, session_id=lease["session_id"], now=now)
    return value, {"dispatched": True, "dispatch_id": identifier, "session_id": lease["session_id"], "session_status": result.get("session_status")}

def submit_operator_input(state: Mapping[str, Any], operator_input: Mapping[str, Any], *, target_root: Any,
                          workspace_root: Any, now: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    value = recover_scheduler_state(state, now=now); envelope = _mapping(operator_input); entry = _entry(value, str(envelope.get("session_id") or ""))
    if entry.get("lease_status") == "active": raise ValueError("session_actively_leased")
    session = load_runtime_session(entry["session_path"], target_root=target_root, workspace_root=workspace_root, now=now)
    result = resume_runtime_session(session, operator_input=envelope, target_root=target_root, workspace_root=workspace_root, now=now)
    result = save_runtime_session(result, entry["session_path"]); refreshed = update_entry_from_session(entry, result, now=now); entry.clear(); entry.update(refreshed)
    _terminal_lists(value, entry); return rebuild_waiting_projection(value, now=now), result

def resume_ready_sessions(state: Mapping[str, Any], *, owner: str, max_sessions: int, target_root: Any,
                          workspace_root: Any, now: Any = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if isinstance(max_sessions, bool) or not 1 <= int(max_sessions) <= 100: raise ValueError("invalid_max_sessions")
    value = recover_scheduler_state(state, now=now); results = []
    for index in range(int(max_sessions)):
        value, result = dispatch_session(value, owner=owner, target_root=target_root, workspace_root=workspace_root, now=now, dispatch_id=f"resume-ready:{time_text(now)}:{index}")
        if not result.get("dispatched"): break
        results.append(result)
    return value, results

def cancel_scheduled_session(state: Mapping[str, Any], session_id: str, *, operator_id: str, now: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    value = recover_scheduler_state(state, now=now); entry = _entry(value, session_id)
    if entry.get("lease_status") == "active": raise ValueError("session_actively_leased")
    session = load_runtime_session(entry["session_path"]); result = cancel_runtime_session(session, operator_id=operator_id, now=now)
    result = save_runtime_session(result, entry["session_path"]); refreshed = update_entry_from_session(entry, result, now=now); entry.clear(); entry.update(refreshed)
    _terminal_lists(value, entry); return rebuild_waiting_projection(value, now=now), result

def compute_scheduler_stats(state: Mapping[str, Any]) -> dict[str, int]:
    entries = list(state.get("entries", [])); statuses = [item.get("session_status") for item in entries]
    actions = [item.get("required_action") for item in entries if item.get("session_status") in WAITING]
    tx_statuses = [(item.get("last_result") or {}).get("transaction_status") for item in entries]
    return {"total_sessions": len(entries), "queued": sum(s not in TERMINAL and s not in WAITING for s in statuses),
        "leased": sum(item.get("lease_status") == "active" for item in entries), "running": statuses.count("running"),
        "waiting_operator": sum(s in WAITING for s in statuses), "waiting_approval": actions.count("operator_approval"),
        "waiting_plan_review": actions.count("execution_plan_review"), "waiting_controlled_request": actions.count("controlled_execution_request"),
        "waiting_active_authorization": actions.count("active_execution_authorization"), "waiting_candidate_bundle": actions.count("candidate_bundle"),
        "waiting_transaction_invocation": actions.count("transactional_invocation"), "completed": statuses.count("completed"),
        "committed": tx_statuses.count("committed"), "rolled_back": tx_statuses.count("rolled_back"), "blocked": statuses.count("blocked"),
        "failed": statuses.count("failed"), "critical_failure": sum(s == "failed" and "critical" in str(item.get("blocked_reasons")) for s, item in zip(statuses, entries)),
        "expired": statuses.count("expired"), "cancelled": statuses.count("cancelled")}

__all__ = ["LEASE_SECONDS", "MAX_LEASE_SECONDS", "SAFE_DISPATCH_STATUSES", "cancel_scheduled_session", "compute_scheduler_stats", "dispatch_session", "enqueue_session", "lease_next_session", "recover_scheduler_state", "release_session_lease", "resume_ready_sessions", "submit_operator_input"]
