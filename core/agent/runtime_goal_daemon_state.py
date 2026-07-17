from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint, time_text

CONTRACT = "zero.agent.goal_daemon.v1"
CYCLE_CONTRACT = "zero.agent.goal_daemon_cycle.v1"
VERSION = "1.0"
VALID_STATUSES = {"created", "running", "idle", "stopping", "stopped", "failed"}

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _unsafe(path: Path) -> bool:
    try: return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError: return False
def positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1: raise ValueError(f"invalid_goal_daemon_{name}")
    return value

@dataclass(frozen=True)
class GoalDaemonConfig:
    poll_interval_seconds: float = 1.0
    max_goals_per_cycle: int = 2
    max_missions_started_per_cycle: int = 4
    max_projection_updates_per_cycle: int = 10
    max_replans_per_cycle: int = 1
    stop_on_critical_error: bool = True
    def __post_init__(self) -> None:
        if isinstance(self.poll_interval_seconds, bool) or not isinstance(self.poll_interval_seconds, (int, float)) or not 0.1 <= float(self.poll_interval_seconds) <= 60.0: raise ValueError("invalid_goal_daemon_poll_interval")
        for field in ("max_goals_per_cycle", "max_missions_started_per_cycle", "max_projection_updates_per_cycle", "max_replans_per_cycle"): positive_integer(getattr(self, field), field)
        if not isinstance(self.stop_on_critical_error, bool): raise ValueError("invalid_goal_daemon_stop_on_critical_error")
    def to_dict(self) -> dict[str, Any]: return asdict(self)
    @property
    def configuration_fingerprint(self) -> str: return fingerprint({"version": VERSION, **self.to_dict()})

@dataclass(frozen=True)
class GoalDaemonCycleResult:
    value: Mapping[str, Any]
    def to_dict(self) -> dict[str, Any]: return deepcopy(dict(self.value))
    @property
    def cycle_id(self) -> str: return str(self.value.get("cycle_id") or "")

@dataclass(frozen=True)
class GoalDaemonStatus:
    value: Mapping[str, Any]
    def to_dict(self) -> dict[str, Any]: return deepcopy(dict(self.value))
    @property
    def daemon_status(self) -> str: return str(self.value.get("daemon_status") or "")

def _unsigned(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = _mapping(value); result.pop(field, None); return result
def seal_goal_daemon_state(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _unsigned(value, "daemon_fingerprint"); result["daemon_fingerprint"] = fingerprint(result); return result
def seal_goal_daemon_cycle(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _unsigned(value, "cycle_fingerprint"); result["cycle_fingerprint"] = fingerprint(result); return result
def validate_goal_daemon_state(value: Mapping[str, Any]) -> list[str]:
    item = _mapping(value); reasons = []
    if item.get("contract") != CONTRACT: reasons.append("invalid_goal_daemon_contract")
    if item.get("daemon_fingerprint") != fingerprint(_unsigned(item, "daemon_fingerprint")): reasons.append("goal_daemon_fingerprint_mismatch")
    if item.get("daemon_status") not in VALID_STATUSES: reasons.append("invalid_goal_daemon_status")
    for key in ("daemon_id", "version", "workspace_root", "controller_state_root", "state_path", "created_at", "updated_at", "configuration_fingerprint"):
        if not str(item.get(key) or "").strip(): reasons.append(f"{key}_required")
    for key in ("cycle_count", "round_robin_cursor"):
        if isinstance(item.get(key), bool) or not isinstance(item.get(key), int) or item.get(key, -1) < 0: reasons.append(f"invalid_{key}")
    try:
        config = GoalDaemonConfig(**_mapping(item.get("configuration")))
        if config.configuration_fingerprint != item.get("configuration_fingerprint"): reasons.append("goal_daemon_configuration_fingerprint_mismatch")
    except (TypeError, ValueError): reasons.append("invalid_goal_daemon_configuration")
    return sorted(set(reasons))
def validate_goal_daemon_cycle(value: Mapping[str, Any]) -> list[str]:
    item = _mapping(value); reasons = []
    if item.get("contract") != CYCLE_CONTRACT: reasons.append("invalid_goal_daemon_cycle_contract")
    if item.get("cycle_fingerprint") != fingerprint(_unsigned(item, "cycle_fingerprint")): reasons.append("goal_daemon_cycle_fingerprint_mismatch")
    for key in ("cycle_id", "daemon_id", "configuration_fingerprint", "created_at", "cycle_status"):
        if not str(item.get(key) or "").strip(): reasons.append(f"{key}_required")
    if not isinstance(item.get("pre_cycle_goal_fingerprints"), Mapping): reasons.append("pre_cycle_goal_fingerprints_required")
    for key in ("selected_goal_ids", "goal_results", "processed_entry_ids", "errors"):
        if not isinstance(item.get(key), list): reasons.append(f"{key}_required")
    if isinstance(item.get("cycle_sequence"), bool) or not isinstance(item.get("cycle_sequence"), int) or item.get("cycle_sequence", 0) < 1: reasons.append("invalid_cycle_sequence")
    return sorted(set(reasons))
def save_goal_daemon_state(value: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path).resolve(strict=False); destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(destination) or _unsafe(destination.parent): raise ValueError("unsafe_goal_daemon_state_path")
    sealed = seal_goal_daemon_state(value); reasons = validate_goal_daemon_state(sealed)
    if reasons: raise ValueError(";".join(reasons))
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle: handle.write(json.dumps(sealed, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination); return sealed
def load_goal_daemon_state(path: Any) -> dict[str, Any]:
    try: value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_goal_daemon_json") from exc
    reasons = validate_goal_daemon_state(value)
    if reasons: raise ValueError(";".join(reasons))
    return value
def create_goal_daemon_state(*, controller: Any, config: GoalDaemonConfig, state_path: Any, now: Any = None) -> dict[str, Any]:
    destination = Path(state_path).resolve(strict=False); identity = {"contract": CONTRACT, "version": VERSION, "workspace_root": str(controller.workspace_root).replace("\\", "/").casefold(), "controller_state_root": str(controller.agent_state_root).replace("\\", "/").casefold()}; at = time_text(now)
    return save_goal_daemon_state({"contract": CONTRACT, "version": VERSION, "daemon_id": f"goal-daemon-{fingerprint(identity)[:20]}", "daemon_status": "created", "workspace_root": str(controller.workspace_root), "controller_state_root": str(controller.agent_state_root), "state_path": str(destination), "configuration": config.to_dict(), "configuration_fingerprint": config.configuration_fingerprint, "created_at": at, "updated_at": at, "started_at": None, "stopped_at": None, "last_cycle_id": None, "last_cycle_timestamp": None, "cycle_count": 0, "round_robin_cursor": 0, "last_selected_goal_ids": [], "last_error": None, "stop_requested": False}, destination)

__all__ = ["CONTRACT", "CYCLE_CONTRACT", "VERSION", "GoalDaemonConfig", "GoalDaemonCycleResult", "GoalDaemonStatus", "create_goal_daemon_state", "load_goal_daemon_state", "positive_integer", "save_goal_daemon_state", "seal_goal_daemon_cycle", "seal_goal_daemon_state", "validate_goal_daemon_cycle", "validate_goal_daemon_state"]
