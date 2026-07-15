from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.runtime.runtime_natural_language_mission_bootstrap import normalize_natural_language_mission
from core.runtime.runtime_operator_session import fingerprint, parse_time, time_text


CONTRACT = "zero.agent.mission_inbox.v1"
ENTRY_CONTRACT = "zero.agent.mission_inbox_entry.v1"
PRIORITIES = {"high": 100, "normal": 0, "low": -100}
STATUSES = {"pending", "selected", "preparing", "waiting_for_approval", "running", "paused", "completed", "blocked", "failed", "cancelled"}
RUNNABLE = {"pending"}
TERMINAL = {"completed", "blocked", "failed", "cancelled"}


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _unsafe(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False


def _canonical_root(value: Any, *, create: bool = False) -> str:
    raw = Path(value).expanduser()
    if not raw.is_absolute() and ".." in raw.parts:
        raise ValueError("unsafe_agent_root_traversal")
    path = raw.resolve(strict=False)
    if create and not path.exists():
        parent = path.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        if not parent.exists() or _unsafe(parent):
            raise ValueError("unsafe_agent_root_parent")
        path.mkdir(parents=True, exist_ok=True)
    path = path.resolve(strict=True)
    if _unsafe(path):
        raise ValueError("unsafe_agent_root")
    return str(path)


def _unsigned_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(entry); value.pop("entry_fingerprint", None); return value


def seal_mission_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    value = _unsigned_entry(entry); value["entry_fingerprint"] = fingerprint(value); return value


def _unsigned_inbox(inbox: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(inbox); value.pop("inbox_fingerprint", None); return value


def seal_mission_inbox(inbox: Mapping[str, Any]) -> dict[str, Any]:
    value = _unsigned_inbox(inbox); value["inbox_fingerprint"] = fingerprint(value); return value


def validate_mission_entry(entry: Mapping[str, Any]) -> list[str]:
    value = _mapping(entry); reasons = []
    if value.get("contract") != ENTRY_CONTRACT: reasons.append("invalid_mission_entry_contract")
    if value.get("entry_fingerprint") != fingerprint(_unsigned_entry(value)): reasons.append("mission_entry_fingerprint_mismatch")
    for field in ("entry_id", "original_input", "normalized_input", "workspace_root", "target_root", "source"):
        if not str(value.get(field) or "").strip(): reasons.append(f"{field}_required")
    if value.get("priority") not in PRIORITIES: reasons.append("invalid_mission_priority")
    if value.get("status") not in STATUSES: reasons.append("invalid_mission_entry_status")
    if isinstance(value.get("attempt_count"), bool) or not isinstance(value.get("attempt_count"), int) or value.get("attempt_count", -1) < 0: reasons.append("invalid_attempt_count")
    if isinstance(value.get("max_attempts"), bool) or not isinstance(value.get("max_attempts"), int) or value.get("max_attempts", 0) < 1: reasons.append("invalid_max_attempts")
    return reasons


def validate_mission_inbox(inbox: Mapping[str, Any]) -> list[str]:
    value = _mapping(inbox); reasons = []
    if value.get("contract") != CONTRACT: reasons.append("invalid_mission_inbox_contract")
    if value.get("inbox_fingerprint") != fingerprint(_unsigned_inbox(value)): reasons.append("mission_inbox_fingerprint_mismatch")
    for field in ("inbox_id", "workspace_root", "state_root"):
        if not str(value.get(field) or "").strip(): reasons.append(f"{field}_required")
    entries = value.get("mission_entries"); order = value.get("entry_order")
    if not isinstance(entries, Mapping): reasons.append("mission_entries_required"); entries = {}
    if not isinstance(order, list): reasons.append("entry_order_required"); order = []
    if len(entries) != len(order) or set(entries) != set(order): reasons.append("mission_entry_order_mismatch")
    if not isinstance(value.get("processed_input_ids"), list): reasons.append("processed_input_ids_required")
    for entry_id in order:
        entry = _mapping(entries.get(entry_id))
        if entry.get("entry_id") != entry_id: reasons.append("mission_entry_identity_mismatch")
        reasons.extend(validate_mission_entry(entry))
    return sorted(set(reasons))


def create_mission_inbox(*, workspace_root: Any, state_root: Any, now: Any = None) -> dict[str, Any]:
    workspace = _canonical_root(workspace_root, create=True); state = str(Path(state_root).resolve(strict=False)); at = time_text(now)
    identity = {"workspace_root": workspace.replace("\\", "/").casefold(), "state_root": state.replace("\\", "/").casefold()}
    return seal_mission_inbox({"contract": CONTRACT, "inbox_id": f"mission-inbox-{fingerprint(identity)[:20]}", "created_at": at, "updated_at": at, "workspace_root": workspace, "state_root": state, "mission_entries": {}, "entry_order": [], "processed_input_ids": [], "audit_record": {"event_type": "agent_mission_inbox_created", "created_at": at}})


def save_mission_inbox(inbox: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path).resolve(strict=False)
    if destination.exists() and _unsafe(destination): raise ValueError("unsafe_mission_inbox_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(destination.parent): raise ValueError("unsafe_mission_inbox_directory")
    value = seal_mission_inbox(inbox); reasons = validate_mission_inbox(value)
    if reasons: raise ValueError(";".join(reasons))
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination); return value


def load_mission_inbox(path: Any) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source): raise ValueError("unsafe_mission_inbox_path")
    try: value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_mission_inbox_json") from exc
    reasons = validate_mission_inbox(value)
    if reasons: raise ValueError(";".join(reasons))
    return value


def normalize_priority(priority: Any) -> str:
    value = "normal" if priority is None else str(priority).strip().casefold()
    if value not in PRIORITIES: raise ValueError("invalid_mission_priority")
    return value


def add_mission_entry(inbox: Mapping[str, Any], natural_language: str, *, workspace_root: Any = None, target_root: Any = None, priority: Any = "normal", constraints: list[str] | None = None, tags: list[str] | None = None, source: str = "zero_agent", max_attempts: int = 3, not_before: Any = None, input_id: str | None = None, now: Any = None) -> tuple[dict[str, Any], dict[str, Any], bool]:
    value = _mapping(inbox); reasons = validate_mission_inbox(value)
    if reasons: raise ValueError(";".join(reasons))
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1: raise ValueError("invalid_max_attempts")
    normalized = normalize_natural_language_mission(natural_language); level = normalize_priority(priority)
    workspace = _canonical_root(workspace_root or value["workspace_root"]); target = _canonical_root(target_root or workspace)
    operation_id = str(input_id or fingerprint({"input": normalized, "workspace": workspace.replace("\\", "/").casefold(), "target": target.replace("\\", "/").casefold(), "source": source})).strip()
    if operation_id in value.get("processed_input_ids", []):
        existing = next(item for item in value["mission_entries"].values() if item.get("input_id") == operation_id)
        return seal_mission_inbox(value), _mapping(existing), False
    seed = {"inbox_id": value["inbox_id"], "input_id": operation_id}; entry_id = f"mission-entry-{fingerprint(seed)[:20]}"; at = time_text(now)
    entry = seal_mission_entry({"contract": ENTRY_CONTRACT, "entry_id": entry_id, "input_id": operation_id, "original_input": str(natural_language), "normalized_input": normalized, "priority": level, "priority_value": PRIORITIES[level], "status": "pending", "created_at": at, "updated_at": at, "completed_at": None, "workspace_root": workspace, "target_root": target, "constraints": list(constraints or ["controlled_execution", "path_containment", "operator_approval"]), "mission_id": None, "mission_session_id": None, "bootstrap_artifact_path": None, "execution_plan_path": None, "approval_required": None, "approval_status": None, "last_result": None, "failure": None, "reflection_id": None, "reflection_path": None, "experience_id": None, "memory_recorded_at": None, "memory_context_used": None, "reflection_status": "not_required", "reflection_error": None, "attempt_count": 0, "max_attempts": max_attempts, "not_before": time_text(not_before) if not_before is not None else None, "tags": sorted(set(str(tag).strip() for tag in tags or [] if str(tag).strip())), "source": str(source or "zero_agent"), "claimed_by": None, "claim_token": None, "claimed_at": None})
    entries = _mapping(value["mission_entries"]); entries[entry_id] = entry; value["mission_entries"] = entries; value["entry_order"] = list(value["entry_order"]) + [entry_id]; value["processed_input_ids"] = list(value["processed_input_ids"]) + [operation_id]; value["updated_at"] = at
    return seal_mission_inbox(value), entry, True


def list_mission_entries(inbox: Mapping[str, Any], *, status: str | None = None) -> list[dict[str, Any]]:
    value = _mapping(inbox); reasons = validate_mission_inbox(value)
    if reasons: raise ValueError(";".join(reasons))
    if status is not None and status not in STATUSES: raise ValueError("invalid_mission_entry_status")
    return [_mapping(value["mission_entries"][entry_id]) for entry_id in value["entry_order"] if status is None or value["mission_entries"][entry_id]["status"] == status]


def get_mission_entry(inbox: Mapping[str, Any], entry_id: str) -> dict[str, Any]:
    entry = _mapping(_mapping(inbox.get("mission_entries")).get(str(entry_id)))
    if not entry: raise ValueError("mission_entry_not_found")
    return entry


def update_mission_entry(inbox: Mapping[str, Any], entry_id: str, *, status: str | None = None, updates: Mapping[str, Any] | None = None, now: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    value = _mapping(inbox); entry = get_mission_entry(value, entry_id); old = entry["status"]
    if status is not None:
        if status not in STATUSES: raise ValueError("invalid_mission_entry_status")
        if old in TERMINAL and status != old: raise ValueError("terminal_mission_entry_immutable")
        entry["status"] = status
    for key, item in _mapping(updates).items():
        if key not in {"entry_id", "entry_fingerprint", "contract", "created_at", "input_id"}: entry[key] = deepcopy(item)
    entry["updated_at"] = time_text(now)
    if entry["status"] in TERMINAL: entry["completed_at"] = entry.get("completed_at") or time_text(now); entry["claimed_by"] = None; entry["claim_token"] = None
    entries = _mapping(value["mission_entries"]); entries[entry_id] = seal_mission_entry(entry); value["mission_entries"] = entries; value["updated_at"] = time_text(now)
    return seal_mission_inbox(value), entries[entry_id]


def reprioritize_mission_entry(inbox: Mapping[str, Any], entry_id: str, priority: Any, *, now: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = get_mission_entry(inbox, entry_id)
    if entry["status"] not in {"pending", "waiting_for_approval", "paused"}: raise ValueError("mission_entry_not_reprioritizable")
    level = normalize_priority(priority)
    return update_mission_entry(inbox, entry_id, updates={"priority": level, "priority_value": PRIORITIES[level]}, now=now)


def cancel_mission_entry(inbox: Mapping[str, Any], entry_id: str, *, now: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    entry = get_mission_entry(inbox, entry_id)
    if entry["status"] not in {"pending", "selected", "preparing", "waiting_for_approval", "paused"}: raise ValueError("mission_entry_not_cancellable")
    return update_mission_entry(inbox, entry_id, status="cancelled", updates={"failure": {"reasons": ["operator_cancelled"]}}, now=now)


def runnable_mission_entries(inbox: Mapping[str, Any], *, now: Any = None) -> list[dict[str, Any]]:
    current = parse_time(time_text(now)); entries = []
    for item in list_mission_entries(inbox):
        if item["status"] not in RUNNABLE or item["attempt_count"] >= item["max_attempts"]: continue
        if item.get("not_before") and parse_time(item["not_before"]) > current: continue
        entries.append(item)
    entries.sort(key=lambda item: (-int(item.get("priority_value", 0)), str(item.get("created_at")), str(item.get("entry_id"))))
    return entries


def claim_next_mission_entry(inbox: Mapping[str, Any], *, agent_id: str, now: Any = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    identity = str(agent_id or "").strip()
    if not identity: raise ValueError("agent_id_required")
    candidates = runnable_mission_entries(inbox, now=now)
    if not candidates: return seal_mission_inbox(inbox), None
    selected = candidates[0]; token = fingerprint({"agent_id": identity, "entry_id": selected["entry_id"], "attempt": selected["attempt_count"] + 1})
    return update_mission_entry(inbox, selected["entry_id"], status="selected", updates={"claimed_by": identity, "claim_token": token, "claimed_at": time_text(now), "attempt_count": selected["attempt_count"] + 1}, now=now)


__all__ = ["CONTRACT", "ENTRY_CONTRACT", "PRIORITIES", "RUNNABLE", "STATUSES", "TERMINAL", "add_mission_entry", "cancel_mission_entry", "claim_next_mission_entry", "create_mission_inbox", "get_mission_entry", "list_mission_entries", "load_mission_inbox", "normalize_priority", "reprioritize_mission_entry", "runnable_mission_entries", "save_mission_inbox", "seal_mission_entry", "seal_mission_inbox", "update_mission_entry", "validate_mission_entry", "validate_mission_inbox"]
