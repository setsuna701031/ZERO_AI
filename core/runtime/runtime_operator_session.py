from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

CONTRACT = "zero.runtime.operator_session.v1"
INPUT_CONTRACT = "zero.runtime.operator_session_input.v1"

TRANSITIONS = {
    "created": {"running", "cancelled"},
    "running": {"waiting_for_operator_approval", "waiting_for_plan_review", "waiting_for_active_authorization", "waiting_for_candidate_bundle", "waiting_for_transaction_invocation", "transaction_running", "blocked", "failed", "expired", "cancelled"},
    "waiting_for_operator_approval": {"running", "blocked", "expired", "cancelled"},
    "waiting_for_plan_review": {"running", "blocked", "expired", "cancelled"},
    "waiting_for_active_authorization": {"running", "blocked", "expired", "cancelled"},
    "waiting_for_candidate_bundle": {"running", "blocked", "expired", "cancelled"},
    "waiting_for_transaction_invocation": {"transaction_running", "blocked", "expired", "cancelled"},
    "transaction_running": {"completed", "blocked", "failed"},
    "completed": set(), "blocked": set(), "failed": set(), "expired": set(), "cancelled": set(),
}

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

def fingerprint(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()

def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime): result = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"): text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None: result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)

def time_text(value: Any = None) -> str:
    return parse_time(value if value is not None else datetime.now(timezone.utc)).replace(microsecond=0).isoformat()

def root_identity(value: Any) -> str:
    return str(Path(value).resolve(strict=True)).replace("\\", "/").casefold()

def _unsigned(session: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(session)); value.pop("session_fingerprint", None); return value

def seal_session(session: Mapping[str, Any]) -> dict[str, Any]:
    value = _unsigned(session); value["session_fingerprint"] = fingerprint(value); return value

def validate_session(session: Mapping[str, Any], *, target_root: Any = None,
                     workspace_root: Any = None, now: Any = None) -> list[str]:
    value = deepcopy(dict(session)) if isinstance(session, Mapping) else {}
    reasons: list[str] = []
    if value.get("contract") != CONTRACT: reasons.append("invalid_session_contract")
    if value.get("session_status") not in TRANSITIONS: reasons.append("invalid_session_status")
    if value.get("session_fingerprint") != fingerprint(_unsigned(value)): reasons.append("session_fingerprint_mismatch")
    for name, artifact in dict(value.get("artifacts") or {}).items():
        expected = dict(value.get("artifact_fingerprints") or {}).get(name)
        if artifact is not None and expected != fingerprint(artifact): reasons.append(f"artifact_fingerprint_mismatch:{name}")
    try:
        if target_root is not None and root_identity(target_root) != value.get("target_root_identity"): reasons.append("target_root_mismatch")
        if workspace_root is not None and root_identity(workspace_root) != value.get("workspace_root_identity"): reasons.append("workspace_root_mismatch")
    except (OSError, RuntimeError, ValueError, TypeError): reasons.append("invalid_root")
    try:
        if value.get("expires_at") and parse_time(now or datetime.now(timezone.utc)) >= parse_time(value["expires_at"]): reasons.append("session_expired")
    except (TypeError, ValueError): reasons.append("invalid_session_expiration")
    return reasons

def transition(session: Mapping[str, Any], status: str, *, phase: str | None = None,
               now: Any = None) -> dict[str, Any]:
    value = deepcopy(dict(session)); current = value.get("session_status")
    if status not in TRANSITIONS.get(current, set()): raise ValueError(f"invalid_transition:{current}:{status}")
    value["session_status"] = status
    if phase is not None: value["current_phase"] = phase
    value["updated_at"] = time_text(now)
    value.setdefault("phase_history", []).append({"from": current, "to": status, "phase": value.get("current_phase"), "at": value["updated_at"]})
    return seal_session(value)

def set_artifact(session: Mapping[str, Any], name: str, artifact: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(session)); item = deepcopy(dict(artifact))
    value["artifacts"][name] = item; value["artifact_fingerprints"][name] = fingerprint(item)
    return seal_session(value)

def add_checkpoint(session: Mapping[str, Any], phase: str, *, inputs: list[str] | None = None,
                   outputs: list[str] | None = None, required_next_action: str = "none",
                   operator_id: str = "", reasons: list[str] | None = None, now: Any = None) -> dict[str, Any]:
    value = deepcopy(dict(session)); at = time_text(now)
    seed = {"session_id": value.get("session_id"), "phase": phase, "inputs": inputs or [], "outputs": outputs or [], "at": at}
    value.setdefault("checkpoints", []).append({"checkpoint_id": f"checkpoint-{fingerprint(seed)[:16]}", "phase": phase, "status": "completed", "started_at": at, "completed_at": at, "input_fingerprints": inputs or [], "output_fingerprints": outputs or [], "required_next_action": required_next_action, "operator_id": operator_id, "reasons": reasons or [], "audit_reference": f"audit:{len(value.get('checkpoints', []))}"})
    return seal_session(value)

def _unsafe_path(path: Path) -> bool:
    try: return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError: return False

def save_runtime_session(session: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path)
    if destination.exists() and _unsafe_path(destination): raise ValueError("unsafe_session_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe_path(destination.parent): raise ValueError("unsafe_session_directory")
    value = seal_session(session); temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination)
    return value

def load_runtime_session(path: Any, **validation: Any) -> dict[str, Any]:
    source = Path(path)
    if _unsafe_path(source): raise ValueError("unsafe_session_path")
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_session_json") from exc
    reasons = validate_session(value, **validation)
    if reasons: raise ValueError(";".join(reasons))
    return value

__all__ = ["CONTRACT", "INPUT_CONTRACT", "TRANSITIONS", "add_checkpoint", "canonical_json", "fingerprint", "load_runtime_session", "parse_time", "root_identity", "save_runtime_session", "seal_session", "set_artifact", "time_text", "transition", "validate_session"]
