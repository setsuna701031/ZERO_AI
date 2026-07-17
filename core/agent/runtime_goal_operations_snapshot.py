from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from core.agent.runtime_agent_controller import default_agent_state_root, load_agent_state
from core.agent.runtime_goal_daemon_state import load_goal_daemon_state
from core.agent.runtime_long_horizon_goal import load_long_horizon_goal
from core.agent.runtime_mission_inbox import load_mission_inbox
from core.agent.runtime_mission_reflection import load_reflection
from core.runtime.runtime_event_bus import load_event_bus_state
from core.runtime.runtime_operator_session import fingerprint

CONTRACT = "zero.agent.goal_operations.v1"
VERSION = "1.0"
PROJECTION_VERSION = "goal-operations-projection-v1"
SOURCE_MANIFEST_KEYS = ("workspace_root", "runtime_state_root", "goal_store", "inbox_store", "daemon_state", "mission_store", "session_store", "approval_store", "activity_memory", "event_bus", "reflection", "experience")

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def sanitize_projection(value: Any) -> Any:
    if isinstance(value, Mapping): return {str(key): sanitize_projection(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [sanitize_projection(item) for item in value]
    if isinstance(value, Path): return str(value)
    if value is None or isinstance(value, (str, int, float, bool)): return deepcopy(value)
    return str(value)
def redact_projection(value: Any, key: str = "") -> Any:
    lowered = key.casefold()
    if any(term in lowered for term in ("password", "secret", "authorization", "access_token", "claim_token")): return "<redacted>" if value is not None else None
    if isinstance(value, Mapping): return {str(item_key): redact_projection(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list): return [redact_projection(item, key) for item in value]
    if isinstance(value, str):
        if (lowered.endswith("_path") or lowered.endswith("_root")) and not value.startswith("<"): return "<redacted-path>"
        return re.sub(r"(?i)(?:[A-Z]:[\\/][^\s\"']+|(?<![\w.])/(?:[^\s\"']+/)+[^\s\"']*)", "<redacted-path>", value)
    return deepcopy(value)
def seal_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(value); result.pop("projection_fingerprint", None); result["projection_fingerprint"] = fingerprint(result); return result
def finalize_projection(value: Mapping[str, Any]) -> dict[str, Any]: return seal_projection(redact_projection(sanitize_projection(value)))
def serialize_projection(value: Mapping[str, Any]) -> str:
    reasons = validate_projection(value, CONTRACT)
    if reasons: raise ValueError(";".join(reasons))
    return json.dumps(sanitize_projection(value), ensure_ascii=False, sort_keys=True)
def validate_projection(value: Mapping[str, Any], expected_contract: str) -> list[str]:
    item = _mapping(value); reasons = []
    if item.get("contract") != expected_contract: reasons.append("invalid_operations_projection_contract")
    unsigned = _mapping(item); claimed = unsigned.pop("projection_fingerprint", None)
    if claimed != fingerprint(unsigned): reasons.append("operations_projection_fingerprint_mismatch")
    if item.get("version") != VERSION: reasons.append("invalid_operations_projection_version")
    return reasons

@dataclass(frozen=True)
class GoalOperationsConfig:
    workspace_root: str
    state_root: str | None = None
    runtime_budget_limit: int = 4
    reference_time: str | None = None
    def __post_init__(self) -> None:
        workspace = Path(self.workspace_root).resolve(strict=True)
        if not workspace.is_dir(): raise ValueError("operations_workspace_root_not_directory")
        if isinstance(self.runtime_budget_limit, bool) or not isinstance(self.runtime_budget_limit, int) or self.runtime_budget_limit < 1: raise ValueError("invalid_operations_runtime_budget")
        object.__setattr__(self, "workspace_root", str(workspace))
        object.__setattr__(self, "state_root", str(Path(self.state_root).resolve(strict=False)) if self.state_root else str(default_agent_state_root(workspace)))
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class _Projection:
    value: Mapping[str, Any]
    def to_dict(self) -> dict[str, Any]: return deepcopy(dict(self.value))

class GoalOperationsOverview(_Projection): pass
class GoalOperationsGoalInspection(_Projection): pass
class GoalOperationsTimeline(_Projection): pass
class GoalOperationsHealth(_Projection): pass
class GoalOperationsPendingApprovals(_Projection): pass

def load_goal_sources(config: GoalOperationsConfig) -> dict[str, Any]:
    state_root = Path(str(config.state_root)); goals_root = state_root / "goals"; index_path = goals_root / "goal-index.json"; errors = []
    goals = []
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8-sig")); unsigned = _mapping(index); claimed = unsigned.pop("index_fingerprint", None)
            if index.get("contract") != "zero.agent.long_horizon_goal_index.v1" or claimed != fingerprint(unsigned): raise ValueError("long_goal_index_fingerprint_mismatch")
            goals = [load_long_horizon_goal(goals_root / goal_id / "goal.json") for goal_id in index.get("goal_ids") or []]
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc: errors.append({"source": "goal_store", "error": str(exc), "critical": True})
    agent_path = state_root / "agent-state.json"; inbox_path = state_root / "mission-inbox.json"; daemon_path = goals_root / "goal-daemon.json"
    agent = inbox = daemon = None
    for name, path, loader in (("agent_state", agent_path, load_agent_state), ("mission_inbox", inbox_path, load_mission_inbox), ("goal_daemon", daemon_path, load_goal_daemon_state)):
        if not path.exists(): continue
        try:
            value = loader(path)
            if name == "agent_state": agent = value
            elif name == "mission_inbox": inbox = value
            else: daemon = value
        except (OSError, ValueError, json.JSONDecodeError) as exc: errors.append({"source": name, "error": str(exc), "critical": name != "goal_daemon" or bool(goals)})
    entries = _mapping(_mapping(inbox).get("mission_entries"))
    referenced = {"bootstrap_artifacts": {}, "missions": {}, "sessions": {}, "approvals": {}}
    for entry_id, entry_value in entries.items():
        entry = _mapping(entry_value); artifact_path = Path(str(entry.get("bootstrap_artifact_path") or ""))
        if not artifact_path.is_file(): continue
        try: artifact = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError): continue
        referenced["bootstrap_artifacts"][entry_id] = artifact.get("artifact_fingerprint")
        for group, reference_key, identity_key, fingerprint_key in (("missions", "mission_reference", "mission_id", "mission_fingerprint"), ("sessions", "session_reference", "session_id", "session_fingerprint")):
            reference = _mapping(artifact.get(reference_key)); path = Path(str(reference.get("path") or ""))
            if not path.is_file(): continue
            try: payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError): continue
            referenced[group][str(reference.get(identity_key) or entry_id)] = payload.get(fingerprint_key)
        approval_path = artifact_path.with_name("execution-approval.json")
        if approval_path.is_file():
            try: approval = json.loads(approval_path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError): continue
            referenced["approvals"][str(approval.get("approval_id") or entry_id)] = approval.get("approval_fingerprint")
    memory_path = state_root / "activity-memory.jsonl"; event_bus_path = state_root / "agent-event-bus.json"; reflections = {}; event_bus_fingerprint = None
    if event_bus_path.is_file():
        try: event_bus_fingerprint = load_event_bus_state(event_bus_path).get("bus_fingerprint")
        except ValueError as exc: errors.append({"source": "event_bus", "error": str(exc), "critical": True})
    for goal in goals:
        reflection_path = Path(str(_mapping(goal.get("reflection_reference")).get("path") or ""))
        if not reflection_path.is_file(): continue
        try:
            reflection = load_reflection(reflection_path); reflections[str(reflection.get("reflection_id") or goal["goal_id"])] = reflection.get("reflection_fingerprint")
        except ValueError as exc: errors.append({"source": "reflection", "error": str(exc), "critical": True})
    fingerprints = {"goals": {goal["goal_id"]: goal["goal_fingerprint"] for goal in goals}, "goal_index": None, "agent": _mapping(agent).get("agent_fingerprint"), "inbox": _mapping(inbox).get("inbox_fingerprint"), "daemon": _mapping(daemon).get("daemon_fingerprint"), "event_bus": event_bus_fingerprint, "activity_memory": hashlib.sha256(memory_path.read_bytes()).hexdigest() if memory_path.is_file() else None, "reflections": reflections, **referenced}
    if index_path.exists() and not any(error["source"] == "goal_store" for error in errors): fingerprints["goal_index"] = index.get("index_fingerprint")
    return {"config": config, "state_root": state_root, "goals_root": goals_root, "goals": goals, "agent": agent, "inbox": inbox, "entries": entries, "daemon": daemon, "errors": errors, "source_fingerprints": fingerprints, "paths": {"agent": agent_path, "inbox": inbox_path, "daemon": daemon_path, "memory": memory_path, "event_bus": event_bus_path}}

def runtime_budget_projection(sources: Mapping[str, Any]) -> dict[str, Any]:
    config: GoalOperationsConfig = sources["config"]; entries = _mapping(sources.get("entries")); active_statuses = {"selected", "preparing", "running"}; active = sum(_mapping(entry).get("status") in active_statuses for entry in entries.values())
    daemon_limit = int(_mapping(_mapping(sources.get("daemon")).get("configuration")).get("max_missions_started_per_cycle") or config.runtime_budget_limit); budget = min(config.runtime_budget_limit, daemon_limit)
    value = {"contract": "zero.agent.runtime_mission_budget_observation.v1", "runtime_budget": budget, "active_mission_count": active, "remaining_mission_capacity": max(0, budget - active), "invariant_satisfied": active <= budget, "source_agent_fingerprint": _mapping(sources.get("agent")).get("agent_fingerprint"), "source_inbox_fingerprint": _mapping(sources.get("inbox")).get("inbox_fingerprint")}
    value["budget_fingerprint"] = fingerprint(value); return value

def byte_invariance_manifest(sources: Mapping[str, Any]) -> dict[str, list[Path]]:
    paths = sources["paths"]; manifest: dict[str, list[Path]] = {key: [] for key in SOURCE_MANIFEST_KEYS}
    manifest.update(workspace_root=[Path(sources["config"].workspace_root)], runtime_state_root=[Path(sources["state_root"])], goal_store=[Path(sources["goals_root"])], inbox_store=[Path(paths["inbox"])], daemon_state=[Path(paths["daemon"])], activity_memory=[Path(paths["memory"])], event_bus=[Path(paths["event_bus"])], experience=[Path(paths["memory"])])
    for entry_value in _mapping(sources.get("entries")).values():
        entry = _mapping(entry_value); artifact_path = Path(str(entry.get("bootstrap_artifact_path") or ""))
        if not artifact_path.is_file(): continue
        try: artifact = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError): continue
        mission = _mapping(artifact.get("mission_reference")); session = _mapping(artifact.get("session_reference"))
        if mission.get("path"): manifest["mission_store"].append(Path(str(mission["path"])))
        if session.get("path"): manifest["session_store"].append(Path(str(session["path"])))
        approval = artifact_path.with_name("execution-approval.json")
        if approval.exists(): manifest["approval_store"].append(approval)
        if entry.get("reflection_path"): manifest["reflection"].append(Path(str(entry["reflection_path"])))
    for goal in sources.get("goals") or []:
        reflection = _mapping(goal.get("reflection_reference"))
        if reflection.get("path"): manifest["reflection"].append(Path(str(reflection["path"])))
    return {key: sorted(set(values), key=lambda path: str(path).casefold()) for key, values in manifest.items()}

def source_manifest_projection(sources: Mapping[str, Any]) -> dict[str, Any]:
    manifest = byte_invariance_manifest(sources); fingerprints = sources["source_fingerprints"]
    return {key: {"logical_root": f"<{key.replace('_', '-')}>", "present": any(path.exists() for path in manifest[key]), "source_count": len(manifest[key])} for key in SOURCE_MANIFEST_KEYS} | {"manifest_version": "goal-operations-source-manifest-v1", "source_fingerprints": deepcopy(fingerprints)}

def snapshot_fingerprint(kind: str, sources: Mapping[str, Any], query: Mapping[str, Any] | None = None) -> str:
    seed = {"contract": CONTRACT, "version": VERSION, "projection_version": PROJECTION_VERSION, "kind": kind, "source_fingerprints": deepcopy(sources["source_fingerprints"]), "query": _mapping(query)}
    return fingerprint(seed)
def snapshot_identity(kind: str, sources: Mapping[str, Any], query: Mapping[str, Any] | None = None) -> str:
    return f"goal-operations-{kind}-{snapshot_fingerprint(kind, sources, query)[:20]}"

__all__ = ["CONTRACT", "VERSION", "PROJECTION_VERSION", "SOURCE_MANIFEST_KEYS", "GoalOperationsConfig", "GoalOperationsOverview", "GoalOperationsGoalInspection", "GoalOperationsTimeline", "GoalOperationsHealth", "GoalOperationsPendingApprovals", "byte_invariance_manifest", "finalize_projection", "load_goal_sources", "redact_projection", "runtime_budget_projection", "sanitize_projection", "seal_projection", "serialize_projection", "snapshot_fingerprint", "snapshot_identity", "source_manifest_projection", "validate_projection"]
