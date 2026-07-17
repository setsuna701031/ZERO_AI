from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint, time_text


CONTRACT = "zero.agent.mission_reflection.v1"
OUTCOMES = {"completed", "blocked", "failed", "cancelled", "denied", "partial"}
_SECRET = re.compile(r"(?i)(password|token|api[_-]?key|authorization|bearer|secret)\s*[:=]\s*([^\s,;]+)")
_PRIVATE_KEY = re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.I | re.S)


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def redact_sensitive(value: Any) -> tuple[Any, bool]:
    redacted = False
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if re.search(r"(?i)password|token|api[_-]?key|authorization|cookie|secret|private[_-]?key|credential", str(key)):
                result[str(key)] = "[REDACTED]"; redacted = True
            else:
                result[str(key)], changed = redact_sensitive(item); redacted = redacted or changed
        return result, redacted
    if isinstance(value, list):
        result = []
        for item in value:
            clean, changed = redact_sensitive(item); result.append(clean); redacted = redacted or changed
        return result, redacted
    if isinstance(value, str):
        clean, count = _PRIVATE_KEY.subn("[REDACTED]", value)
        clean, count2 = _SECRET.subn(lambda match: f"{match.group(1)}=[REDACTED]", clean)
        return clean[:2000], bool(count or count2)
    return deepcopy(value), False


def _walk(value: Any):
    if isinstance(value, Mapping):
        yield value
        for item in value.values(): yield from _walk(item)
    elif isinstance(value, list):
        for item in value: yield from _walk(item)


def _strings(value: Any, *keys: str) -> list[str]:
    found = []
    for item in _walk(value):
        for key in keys:
            current = item.get(key)
            values = current if isinstance(current, list) else [current]
            for candidate in values:
                text = str(candidate or "").strip()
                if text and text not in found: found.append(text)
    return found


def _artifact_reference(path: Any) -> dict[str, Any] | None:
    if not path: return None
    candidate = Path(path).resolve(strict=False)
    if not candidate.is_file(): return {"path": str(candidate), "available": False}
    data = candidate.read_bytes()
    return {"path": str(candidate), "available": True, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _unsigned(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(value); result.pop("reflection_fingerprint", None); return result


def seal_reflection(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _unsigned(value); result["reflection_fingerprint"] = fingerprint(result); return result


def validate_reflection(value: Mapping[str, Any]) -> list[str]:
    item = _mapping(value); reasons = []
    if item.get("contract") != CONTRACT: reasons.append("invalid_reflection_contract")
    if item.get("reflection_fingerprint") != fingerprint(_unsigned(item)): reasons.append("reflection_fingerprint_mismatch")
    for field in ("reflection_id", "agent_id", "entry_id", "outcome", "original_input", "normalized_input", "summary", "created_at", "idempotency_key"):
        if not str(item.get(field) or "").strip(): reasons.append(f"{field}_required")
    if item.get("outcome") not in OUTCOMES: reasons.append("invalid_reflection_outcome")
    for field in ("what_was_attempted", "what_succeeded", "what_failed", "what_was_blocked", "key_evidence", "committed_paths", "lessons", "future_recommendations", "reusable_patterns", "avoid_patterns", "risk_notes", "source_artifact_references"):
        if not isinstance(item.get(field), list): reasons.append(f"{field}_required")
    return sorted(set(reasons))


def build_mission_reflection(entry: Mapping[str, Any], *, agent_id: str, mission: Any = None,
                             session: Any = None, artifact: Any = None, now: Any = None) -> dict[str, Any]:
    item = _mapping(entry); mission_data = _mapping(mission); session_data = _mapping(session); artifact_data = _mapping(artifact)
    evidence = {"entry": item, "mission": mission_data, "session": session_data, "artifact": artifact_data, "result": item.get("last_result")}
    clean, secret_redacted = redact_sensitive(evidence)
    status = str(item.get("status") or "failed").casefold(); approval = str(item.get("approval_status") or "").casefold()
    outcome = "denied" if approval == "denied" else status if status in OUTCOMES else "partial"
    operations = _strings(clean, "operation", "natural_operation")
    targets = _strings(clean, "target_paths", "committed_paths")
    for intent in artifact_data.get("structured_intents") or _mapping(item.get("last_result")).get("structured_intents") or []:
        path = str(_mapping(intent).get("path") or "").strip()
        if path and path not in targets: targets.append(path)
    committed = _strings(clean, "committed_paths")
    failures = _strings(clean, "reason", "reasons")
    failures = [reason for reason in failures if reason.casefold() not in {"none", "null"}]
    blocked = failures if outcome in {"blocked", "denied"} else []
    failed = failures if outcome == "failed" else []
    reusable = []
    if outcome == "completed" and "create_file" in operations and "check_exists" in operations: reusable.append("create_then_verify")
    if outcome == "completed" and approval == "approved": reusable.append("approval_before_mutation")
    if outcome == "completed" and any(op in operations for op in ("create_file", "create_directory")): reusable.append("workspace_contained_write")
    if outcome == "completed" and any(op in operations for op in ("read_file", "check_exists")): reusable.append("controlled_read_only")
    avoid = []
    joined = " ".join(failures).casefold()
    if "unsafe" in joined or "outside" in joined or "traversal" in joined: avoid.append("path_traversal")
    if "validation" in joined: avoid.append("commit_without_validation")
    if approval == "denied": avoid.append("proceed_without_operator_approval")
    recommendations = []
    if any(op in operations for op in ("create_file", "create_directory")): recommendations.append("verify_target_exists")
    if "create_file" in operations: recommendations.append("verify_content_hash")
    if "path_traversal" in avoid: recommendations.append("use_workspace_relative_paths")
    if outcome == "failed": recommendations.append("inspect_failure_evidence_before_retry")
    refs = []
    for path in (item.get("bootstrap_artifact_path"), item.get("execution_plan_path"), mission_data.get("mission_path"), session_data.get("session_state_path")):
        ref = _artifact_reference(path)
        if ref and ref not in refs: refs.append(ref)
    evidence_present = bool(mission_data or session_data or artifact_data or item.get("last_result") or item.get("failure"))
    quality = "sufficient" if evidence_present else "insufficient"
    identity = {"agent_id": agent_id, "entry_id": item.get("entry_id"), "mission_id": item.get("mission_id"), "session_id": item.get("mission_session_id"), "outcome": outcome}
    reflection_id = f"mission-reflection-{fingerprint(identity)[:20]}"
    risk_notes = ["secret_redacted"] if secret_redacted else []
    validation = _strings(clean, "validation_status")
    rollback = _strings(clean, "rollback_status")
    planning_applied = deepcopy(artifact_data.get("applied_recommendations") or item.get("memory_recommendations_applied") or [])
    planning_ignored = deepcopy(artifact_data.get("ignored_recommendations") or item.get("memory_recommendations_ignored") or [])
    effective = []
    if outcome == "completed":
        completed_operations = set(operations)
        for recommendation in planning_applied:
            name = str(_mapping(recommendation).get("recommendation") or recommendation)
            if name == "create_then_verify" and {"create_file", "check_exists"}.issubset(completed_operations): effective.append(name)
            elif name.startswith("verify_") and validation and not any("fail" in state.casefold() for state in validation): effective.append(name)
    planning_failed = [] if outcome == "completed" else [str(_mapping(candidate).get("recommendation") or candidate) for candidate in planning_applied]
    value = {"contract": CONTRACT, "reflection_id": reflection_id, "agent_id": str(agent_id), "entry_id": item.get("entry_id"), "mission_id": item.get("mission_id"), "session_id": item.get("mission_session_id"), "mission_fingerprint": mission_data.get("mission_fingerprint") or artifact_data.get("mission_fingerprint"), "goal_graph_fingerprint": _mapping(mission_data.get("goal_graph")).get("graph_fingerprint") or _mapping(artifact_data.get("graph_reference")).get("graph_fingerprint"), "outcome": outcome, "original_input": clean["entry"].get("original_input"), "normalized_input": clean["entry"].get("normalized_input"), "summary": f"Mission {outcome}: {clean['entry'].get('normalized_input')}", "what_was_attempted": operations or [clean["entry"].get("normalized_input")], "what_succeeded": (["mission_completed"] + committed) if outcome == "completed" else [], "what_failed": failed, "what_was_blocked": blocked, "key_evidence": [ref["sha256"] for ref in refs if ref.get("sha256")], "committed_paths": committed, "validation_summary": validation[0] if validation else "not_recorded", "rollback_summary": rollback[0] if rollback else "not_required", "approval_summary": approval or ("pending" if item.get("approval_required") else "not_required"), "lessons": sorted(set(reusable + avoid)), "future_recommendations": sorted(set(recommendations)), "reusable_patterns": sorted(set(reusable)), "avoid_patterns": sorted(set(avoid)), "risk_notes": risk_notes, "memory_context_used": bool(artifact_data.get("memory_context")), "planning_recommendations_applied": planning_applied, "planning_recommendations_effective": sorted(set(effective)), "planning_recommendations_failed": sorted(set(planning_failed)), "planning_recommendations_ignored": planning_ignored, "evidence_quality": quality, "reflection_confidence": "high" if quality == "sufficient" else "low", "created_at": time_text(now), "source_artifact_references": refs, "idempotency_key": fingerprint(identity)}
    clean_value, changed = redact_sensitive(value)
    if changed and "secret_redacted" not in clean_value["risk_notes"]: clean_value["risk_notes"].append("secret_redacted")
    return seal_reflection(clean_value)


def save_reflection(value: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path).resolve(strict=False); destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and (destination.is_symlink() or getattr(destination.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)): raise ValueError("unsafe_reflection_path")
    sealed = seal_reflection(value); reasons = validate_reflection(sealed)
    if reasons: raise ValueError(";".join(reasons))
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle: handle.write(json.dumps(sealed, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination); return sealed


def load_reflection(path: Any) -> dict[str, Any]:
    try: value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_reflection_json") from exc
    reasons = validate_reflection(value)
    if reasons: raise ValueError(";".join(reasons))
    return value


__all__ = ["CONTRACT", "OUTCOMES", "build_mission_reflection", "load_reflection", "redact_sensitive", "save_reflection", "seal_reflection", "validate_reflection"]
