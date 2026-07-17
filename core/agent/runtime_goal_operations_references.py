from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_mission_model import load_mission
from core.runtime.runtime_mission_session import load_mission_session_state
from core.runtime.runtime_operator_session import fingerprint

ACTIVE_ENTRY_STATUSES = {"pending", "selected", "preparing", "waiting_for_approval", "running", "paused"}

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _sealed_json(path: Path, field: str, error: str) -> dict[str, Any]:
    try: value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError(error) from exc
    unsigned = _mapping(value); claimed = unsigned.pop(field, None)
    if claimed != fingerprint(unsigned): raise ValueError(error.replace("json", "fingerprint"))
    return value

def build_reference_chains(goal: Mapping[str, Any], entries: Mapping[str, Any]) -> dict[str, Any]:
    chains = []; issues = []; session_owners: dict[str, list[dict[str, str]]] = {}; mission_owners: dict[str, list[dict[str, str]]] = {}
    for milestone_id in goal.get("milestone_order") or []:
        milestone = _mapping(_mapping(goal.get("milestones")).get(milestone_id))
        for entry_id in milestone.get("mission_entry_ids") or []:
            entry = _mapping(entries.get(entry_id)); chain = {"goal_id": goal.get("goal_id"), "milestone_id": milestone_id, "entry_id": entry_id, "entry_status": entry.get("status"), "mission_id": entry.get("mission_id"), "session_id": entry.get("mission_session_id"), "approval": None, "evidence_references": [], "integrity": True, "issues": []}
            if not entry: chain["issues"].append("missing_entry")
            else:
                if entry.get("goal_id") != goal.get("goal_id"): chain["issues"].append("entry_goal_identity_mismatch")
                if entry.get("milestone_id") != milestone_id: chain["issues"].append("entry_milestone_identity_mismatch")
                artifact_path = Path(str(entry.get("bootstrap_artifact_path") or ""))
                if entry.get("status") not in {"pending", "selected", "preparing"} and not artifact_path.is_file(): chain["issues"].append("missing_bootstrap_artifact")
                if artifact_path.is_file():
                    try:
                        artifact = _sealed_json(artifact_path, "artifact_fingerprint", "invalid_bootstrap_artifact_json"); mission_ref = _mapping(artifact.get("mission_reference")); session_ref = _mapping(artifact.get("session_reference"))
                        plan_ref = _mapping(artifact.get("execution_plan_reference")); public_plan = {key: plan_ref.get(key) for key in ("plan_id", "fingerprint")}
                        if plan_ref.get("path"):
                            try:
                                plan = _sealed_json(Path(str(plan_ref["path"])), "plan_fingerprint", "invalid_execution_plan_json")
                                if plan.get("plan_id") != plan_ref.get("plan_id") or plan.get("plan_fingerprint") != plan_ref.get("fingerprint"): chain["issues"].append("execution_plan_identity_mismatch")
                            except ValueError: chain["issues"].append("missing_or_invalid_execution_plan")
                        elif entry.get("status") == "waiting_for_approval": chain["issues"].append("missing_approval_proposal_reference")
                        chain.update(bootstrap_artifact_path=str(artifact_path), artifact_fingerprint=artifact.get("artifact_fingerprint"), artifact_created_at=artifact.get("created_at"), execution_plan_reference=public_plan, requested_scope=[item.get("path") for item in artifact.get("structured_intents") or [] if item.get("path")])
                        if mission_ref.get("mission_id") != entry.get("mission_id"): chain["issues"].append("entry_mission_identity_mismatch")
                        if session_ref.get("session_id") != entry.get("mission_session_id"): chain["issues"].append("entry_session_identity_mismatch")
                        if mission_ref.get("path"):
                            try:
                                mission = load_mission(mission_ref["path"], check_expiry=False); chain.update(mission_status=mission.get("mission_status"), mission_fingerprint=mission.get("mission_fingerprint"), mission_created_at=mission.get("created_at"), mission_completed_at=mission.get("completed_at"), mission_path=mission_ref.get("path"))
                            except ValueError: chain["issues"].append("missing_or_invalid_mission")
                        if session_ref.get("path"):
                            try:
                                session = load_mission_session_state(session_ref["path"]); chain.update(session_status=session.get("session_status"), session_fingerprint=session.get("session_fingerprint"), session_created_at=session.get("created_at"), session_completed_at=session.get("completed_at"), session_path=session_ref.get("path"), recovery_count=session.get("recovery_count"), last_recovery_at=session.get("last_recovery_at"))
                            except ValueError: chain["issues"].append("missing_or_invalid_session")
                        approval_path = artifact_path.with_name("execution-approval.json")
                        if approval_path.is_file():
                            try:
                                approval = _sealed_json(approval_path, "approval_fingerprint", "invalid_approval_json"); chain["approval"] = {"approval_id": approval.get("approval_id"), "status": approval.get("approval_status"), "requested_scope": deepcopy(approval.get("approved_scope") or approval.get("requested_scope") or []), "created_at": approval.get("created_at"), "expires_at": approval.get("expires_at"), "approval_fingerprint": approval.get("approval_fingerprint")}
                            except ValueError: chain["issues"].append("invalid_approval_reference")
                    except ValueError: chain["issues"].append("invalid_bootstrap_artifact")
                if entry.get("mission_id"): mission_owners.setdefault(str(entry["mission_id"]), []).append({"goal_id": str(goal["goal_id"]), "entry_id": entry_id})
                if entry.get("mission_session_id"): session_owners.setdefault(str(entry["mission_session_id"]), []).append({"goal_id": str(goal["goal_id"]), "entry_id": entry_id})
            if milestone.get("milestone_status") == "completed" and chain.get("entry_status") not in {"completed", None}: chain["issues"].append("completed_milestone_nonterminal_entry")
            chain["integrity"] = not chain["issues"]; issues.extend({"goal_id": goal.get("goal_id"), "milestone_id": milestone_id, "entry_id": entry_id, "reason": reason} for reason in chain["issues"]); chains.append(chain)
    duplicates = []
    for kind, owners in (("mission", mission_owners), ("session", session_owners)):
        for identity, values in owners.items():
            if len({value["entry_id"] for value in values}) > 1: duplicates.append({"type": f"duplicate_{kind}_ownership", "identity": identity, "owners": values})
    return {"chains": chains, "issues": issues, "duplicates": duplicates, "integrity": not issues and not duplicates}

def active_references(chains: list[Mapping[str, Any]]) -> dict[str, Any]:
    active = [chain for chain in chains if chain.get("entry_status") in ACTIVE_ENTRY_STATUSES]
    first = active[0] if active else {}
    return {"active_entry_reference": first.get("entry_id"), "active_mission_reference": first.get("mission_id"), "active_session_reference": first.get("session_id"), "active_reference_count": len(active)}

__all__ = ["ACTIVE_ENTRY_STATUSES", "active_references", "build_reference_chains"]
