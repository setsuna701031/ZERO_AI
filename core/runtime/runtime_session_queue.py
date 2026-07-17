from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint, load_runtime_session, parse_time, time_text

CONTRACT = "zero.runtime.session_scheduler.v1"
QUEUE_VERSION = 1
PRIORITIES = {"low": -10, "normal": 0, "high": 10}
TERMINAL = {"completed", "blocked", "failed", "expired", "cancelled"}
WAITING = {"waiting_for_operator_approval", "waiting_for_plan_review", "waiting_for_active_authorization",
           "waiting_for_candidate_bundle", "waiting_for_transaction_invocation"}

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _unsigned(state: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(state); value.pop("scheduler_fingerprint", None); return value
def seal_scheduler_state(state: Mapping[str, Any]) -> dict[str, Any]:
    value = _unsigned(state)
    for entry in value.get("entries", []):
        item = deepcopy(entry); item.pop("entry_fingerprint", None); entry["entry_fingerprint"] = fingerprint(item)
    value["scheduler_fingerprint"] = fingerprint(value); return value

def normalize_priority(value: Any) -> int:
    if isinstance(value, str) and value in PRIORITIES: return PRIORITIES[value]
    if isinstance(value, bool) or not isinstance(value, int) or not -100 <= value <= 100: raise ValueError("invalid_priority")
    return value

def create_scheduler_state(*, state_path: Any = None, now: Any = None) -> dict[str, Any]:
    at = time_text(now); identity = str(Path(state_path).resolve(strict=False)).replace("\\", "/").casefold() if state_path else "explicit-path-required"
    state = {"contract": CONTRACT, "scheduler_id": f"runtime-scheduler-{fingerprint({'path': identity, 'created_at': at})[:20]}",
        "scheduler_status": "idle", "created_at": at, "updated_at": at, "queue_version": QUEUE_VERSION,
        "entries": [], "leases": [], "completed_sessions": [], "failed_sessions": [], "cancelled_sessions": [],
        "waiting_operator_sessions": [], "stats": {}, "processed_dispatch_ids": [],
        "audit_record": {"event_type": "runtime_session_scheduler_created", "created_at": at}}
    return seal_scheduler_state(state)

def _entry_unsigned(entry: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(entry); value.pop("entry_fingerprint", None); return value

def validate_scheduler_state(state: Mapping[str, Any]) -> list[str]:
    value = _mapping(state); reasons: list[str] = []
    if value.get("contract") != CONTRACT: reasons.append("invalid_scheduler_contract")
    if value.get("queue_version") != QUEUE_VERSION: reasons.append("scheduler_migration_required")
    if value.get("scheduler_fingerprint") != fingerprint(_unsigned(value)): reasons.append("scheduler_fingerprint_mismatch")
    sequences, sessions, active_leases = set(), set(), set()
    for entry in value.get("entries", []):
        if not isinstance(entry, Mapping): reasons.append("invalid_queue_entry"); continue
        if entry.get("entry_fingerprint") != fingerprint(_entry_unsigned(entry)): reasons.append(f"queue_entry_fingerprint_mismatch:{entry.get('session_id')}")
        sequence = entry.get("sequence_number")
        if sequence in sequences: reasons.append("duplicate_sequence_number")
        sequences.add(sequence)
        if entry.get("session_id") in sessions and entry.get("session_status") not in TERMINAL: reasons.append("duplicate_active_session_entry")
        sessions.add(entry.get("session_id"))
        if entry.get("lease_status") == "active":
            if entry.get("session_id") in active_leases: reasons.append("duplicate_active_lease")
            active_leases.add(entry.get("session_id"))
    return reasons

def _projection(session: Mapping[str, Any], session_path: Path, priority: int, sequence: int, now: Any) -> dict[str, Any]:
    at = time_text(now); status = session.get("session_status")
    entry = {"queue_entry_id": f"queue-entry-{fingerprint({'scheduler_session': session.get('session_id'), 'path': str(session_path).casefold()})[:20]}",
        "session_id": session.get("session_id"), "session_path": str(session_path), "session_fingerprint": session.get("session_fingerprint"),
        "session_status": status, "current_phase": session.get("current_phase"), "required_action": session.get("required_action"),
        "required_input_contract": session.get("required_input_contract"), "priority": priority, "sequence_number": sequence,
        "enqueued_at": at, "available_at": at, "expires_at": session.get("expires_at"), "lease_status": "none", "lease_id": "",
        "lease_owner": "", "lease_acquired_at": None, "lease_expires_at": None, "attempt_count": 0, "last_dispatch_id": "",
        "last_result": None, "blocked_reasons": [], "target_root_identity": session.get("target_root_identity"),
        "workspace_root_identity": session.get("workspace_root_identity"), "waiting_since": at if status in WAITING else None,
        "audit_record": {"event_type": "runtime_session_enqueued", "session_id": session.get("session_id"), "at": at}}
    entry["entry_fingerprint"] = fingerprint(entry); return entry

def update_entry_from_session(entry: Mapping[str, Any], session: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    value = _mapping(entry); status = session.get("session_status")
    value.update(session_fingerprint=session.get("session_fingerprint"), session_status=status,
        current_phase=session.get("current_phase"), required_action=session.get("required_action"),
        required_input_contract=session.get("required_input_contract"), expires_at=session.get("expires_at"))
    if status in WAITING and not value.get("waiting_since"): value["waiting_since"] = time_text(now)
    if status not in WAITING: value["waiting_since"] = None
    value["entry_fingerprint"] = fingerprint(_entry_unsigned(value)); return value

def enqueue_session(state: Mapping[str, Any], session_path: Any, *, priority: Any = "normal", now: Any = None,
                    target_root: Any = None, workspace_root: Any = None) -> dict[str, Any]:
    value = _mapping(state); reasons = validate_scheduler_state(value)
    if reasons: raise ValueError(";".join(reasons))
    normalized_priority = normalize_priority(priority)
    path = Path(session_path).resolve(strict=True); session = load_runtime_session(path, target_root=target_root, workspace_root=workspace_root, now=now)
    existing = next((item for item in value["entries"] if item.get("session_id") == session.get("session_id")), None)
    if existing:
        if existing.get("session_fingerprint") == session.get("session_fingerprint"): return value
        raise ValueError("duplicate_active_queue_entry")
    if session.get("session_status") in TERMINAL: raise ValueError("terminal_session_not_enqueueable")
    sequence = max([int(item.get("sequence_number", 0)) for item in value["entries"]] or [0]) + 1
    value["entries"].append(_projection(session, path, normalized_priority, sequence, now)); value["updated_at"] = time_text(now)
    return rebuild_waiting_projection(value, now=now)

def ordered_entries(state: Mapping[str, Any], *, include_terminal: bool = True) -> list[dict[str, Any]]:
    entries = [_mapping(item) for item in state.get("entries", []) if include_terminal or item.get("session_status") not in TERMINAL]
    return sorted(entries, key=lambda item: (-int(item.get("priority", 0)), int(item.get("sequence_number", 0))))

def waiting_projection(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {key: entry.get(key) for key in ("session_id", "session_path", "current_phase", "required_action", "required_input_contract",
        "waiting_since", "expires_at", "priority", "target_root_identity")} | {"operator_id_required": True,
        "summary": f"{entry.get('current_phase')}:{entry.get('required_action')}", "checkpoint_id": None,
        "next_command_hint": "zero-runtime-scheduler submit-input <state> <operator-input>"}

def rebuild_waiting_projection(state: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state); value["waiting_operator_sessions"] = [waiting_projection(item) for item in ordered_entries(value) if item.get("session_status") in WAITING]
    value["updated_at"] = time_text(now); return seal_scheduler_state(value)

def pause_queue(state: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state)
    if validate_scheduler_state(value): raise ValueError("invalid_scheduler_state")
    value["scheduler_status"] = "paused"; value["updated_at"] = time_text(now); return seal_scheduler_state(value)

def resume_queue(state: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state)
    if validate_scheduler_state(value): raise ValueError("invalid_scheduler_state")
    if value.get("scheduler_status") != "paused": raise ValueError("queue_not_paused")
    value["scheduler_status"] = "idle"; value["updated_at"] = time_text(now); return seal_scheduler_state(value)

def _unsafe(path: Path) -> bool:
    try: return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError: return False

def save_scheduler_state(state: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path)
    if destination.exists() and _unsafe(destination): raise ValueError("unsafe_scheduler_state_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(destination.parent): raise ValueError("unsafe_scheduler_state_directory")
    value = seal_scheduler_state(state); temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination); return value

def load_scheduler_state(path: Any) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source): raise ValueError("unsafe_scheduler_state_path")
    try: value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_scheduler_json") from exc
    reasons = validate_scheduler_state(value)
    if reasons: raise ValueError(";".join(reasons))
    return value

__all__ = ["CONTRACT", "PRIORITIES", "QUEUE_VERSION", "TERMINAL", "WAITING", "create_scheduler_state", "enqueue_session", "load_scheduler_state", "normalize_priority", "ordered_entries", "pause_queue", "rebuild_waiting_projection", "resume_queue", "save_scheduler_state", "seal_scheduler_state", "update_entry_from_session", "validate_scheduler_state", "waiting_projection"]
