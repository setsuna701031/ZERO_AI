from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.runtime.runtime_natural_language_mission_bootstrap import normalize_natural_language_mission
from core.runtime.runtime_operator_session import fingerprint, time_text


CONTRACT = "zero.agent.long_horizon_goal.v1"
MILESTONE_CONTRACT = "zero.agent.goal_milestone.v1"
GOAL_STATUSES = {"draft", "planned", "ready", "running", "waiting_for_approval", "paused", "blocked", "failed", "partially_completed", "completed", "cancelled", "stopped"}
MILESTONE_STATUSES = {"pending", "ready", "generating_missions", "waiting_for_missions", "waiting_for_approval", "running", "completed", "blocked", "failed", "cancelled"}
TERMINAL_GOALS = {"blocked", "failed", "completed", "cancelled", "stopped"}
TERMINAL_MILESTONES = {"completed", "blocked", "failed", "cancelled"}


def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _unsafe(path: Path) -> bool:
    try: return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError: return False
def _unsigned_goal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(value); result.pop("goal_fingerprint", None); return result
def _unsigned_milestone(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(value); result.pop("milestone_fingerprint", None); return result
def seal_milestone(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _unsigned_milestone(value); result["milestone_fingerprint"] = fingerprint(result); return result
def seal_long_horizon_goal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _unsigned_goal(value)
    result["milestones"] = {str(key): seal_milestone(item) for key, item in _mapping(result.get("milestones")).items()}
    result["goal_fingerprint"] = fingerprint(result); return result


def stable_milestone_order(milestones: Mapping[str, Mapping[str, Any]]) -> list[str]:
    values = {str(key): _mapping(item) for key, item in milestones.items()}
    incoming = {key: set(map(str, item.get("dependencies") or [])) for key, item in values.items()}
    order: list[str] = []
    while incoming:
        ready = sorted((key for key, deps in incoming.items() if not deps), key=lambda key: (-int(values[key].get("priority", 0)), key))
        if not ready: raise ValueError("milestone_dependency_cycle")
        order.extend(ready)
        for key in ready: incoming.pop(key)
        for deps in incoming.values(): deps.difference_update(ready)
    return order


def validate_milestone(value: Mapping[str, Any], *, known_ids: set[str] | None = None) -> list[str]:
    item = _mapping(value); reasons = []
    if item.get("contract") != MILESTONE_CONTRACT: reasons.append("invalid_milestone_contract")
    if item.get("milestone_fingerprint") != fingerprint(_unsigned_milestone(item)): reasons.append("milestone_fingerprint_mismatch")
    for key in ("milestone_id", "title", "description", "created_at", "updated_at"):
        if not str(item.get(key) or "").strip(): reasons.append(f"{key}_required")
    if item.get("milestone_status") not in MILESTONE_STATUSES: reasons.append("invalid_milestone_status")
    for key in ("dependencies", "mission_templates", "mission_entry_ids", "success_criteria", "evidence_requirements", "risk_notes", "reflection_references", "experience_references"):
        if not isinstance(item.get(key), list): reasons.append(f"{key}_required")
    if known_ids is not None and any(str(dep) not in known_ids for dep in item.get("dependencies") or []): reasons.append("missing_milestone_dependency")
    if item.get("milestone_id") in set(map(str, item.get("dependencies") or [])): reasons.append("self_milestone_dependency")
    if isinstance(item.get("attempt_count"), bool) or not isinstance(item.get("attempt_count"), int) or item.get("attempt_count", -1) < 0: reasons.append("invalid_milestone_attempt_count")
    if isinstance(item.get("max_attempts"), bool) or not isinstance(item.get("max_attempts"), int) or item.get("max_attempts", 0) < 1: reasons.append("invalid_milestone_max_attempts")
    for template in item.get("mission_templates") or []:
        candidate = _mapping(template)
        if not str(candidate.get("mission_template_id") or "").strip() or not str(candidate.get("natural_language") or "").strip(): reasons.append("invalid_mission_template")
        if any(key in candidate for key in ("command", "shell", "argv", "callable", "subprocess")): reasons.append("executable_mission_template_forbidden")
    return sorted(set(reasons))


def validate_long_horizon_goal(value: Mapping[str, Any]) -> list[str]:
    item = _mapping(value); reasons = []
    if item.get("contract") != CONTRACT: reasons.append("invalid_long_horizon_goal_contract")
    if item.get("goal_fingerprint") != fingerprint(_unsigned_goal(item)): reasons.append("long_horizon_goal_fingerprint_mismatch")
    for key in ("goal_id", "original_input", "normalized_goal", "goal_title", "goal_description", "workspace_root", "target_root", "created_at", "updated_at"):
        if not str(item.get(key) or "").strip(): reasons.append(f"{key}_required")
    if item.get("goal_status") not in GOAL_STATUSES: reasons.append("invalid_long_horizon_goal_status")
    for key in ("constraints", "milestone_order", "mission_entry_references", "success_criteria", "completion_evidence", "processed_input_ids", "checkpoints", "replan_history"):
        if not isinstance(item.get(key), list): reasons.append(f"{key}_required")
    milestones = _mapping(item.get("milestones")); known = set(milestones)
    if set(item.get("milestone_order") or []) != known or len(item.get("milestone_order") or []) != len(known): reasons.append("milestone_order_mismatch")
    for key, milestone in milestones.items():
        if _mapping(milestone).get("milestone_id") != key: reasons.append("milestone_identity_mismatch")
        reasons.extend(validate_milestone(milestone, known_ids=known))
    try:
        if milestones and stable_milestone_order(milestones) != item.get("milestone_order"): reasons.append("milestone_topological_order_mismatch")
    except ValueError as exc: reasons.append(str(exc))
    progress = _mapping(item.get("progress"))
    if int(progress.get("total_milestones", -1)) != len(milestones): reasons.append("goal_progress_total_mismatch")
    if isinstance(item.get("replan_count"), bool) or not isinstance(item.get("replan_count"), int) or item.get("replan_count", -1) < 0: reasons.append("invalid_replan_count")
    if isinstance(item.get("max_replans"), bool) or not isinstance(item.get("max_replans"), int) or item.get("max_replans", 0) < 0: reasons.append("invalid_max_replans")
    return sorted(set(reasons))


def calculate_goal_progress(milestones: Mapping[str, Mapping[str, Any]], order: list[str]) -> dict[str, Any]:
    values = {key: _mapping(milestones[key]) for key in order}
    def ids(status: str) -> list[str]: return [key for key in order if values[key].get("milestone_status") == status]
    completed = ids("completed"); running = [key for key in order if values[key].get("milestone_status") in {"generating_missions", "waiting_for_missions", "running"}]
    ready = [key for key in order if values[key].get("milestone_status") in {"pending", "ready"} and all(values[dep].get("milestone_status") == "completed" for dep in values[key].get("dependencies") or [])]
    total = len(order)
    return {"total_milestones": total, "completed_milestones": completed, "running_milestones": running, "waiting_approval_milestones": ids("waiting_for_approval"), "blocked_milestones": ids("blocked"), "failed_milestones": ids("failed"), "cancelled_milestones": ids("cancelled"), "completion_percentage": round((len(completed) * 100.0 / total) if total else 0.0, 2), "current_milestone_id": next((key for key in order if values[key].get("milestone_status") not in TERMINAL_MILESTONES), None), "next_ready_milestone_ids": ready}


def create_long_horizon_goal(original_input: str, *, workspace_root: Any, target_root: Any, priority: str = "normal", max_replans: int = 3, now: Any = None) -> dict[str, Any]:
    normalized = normalize_natural_language_mission(original_input); workspace = Path(workspace_root).resolve(strict=True); target = Path(target_root).resolve(strict=True)
    if not target.is_relative_to(workspace) and target != workspace: raise ValueError("long_goal_target_outside_workspace")
    if priority not in {"high", "normal", "low"}: raise ValueError("invalid_long_goal_priority")
    if isinstance(max_replans, bool) or not isinstance(max_replans, int) or not 0 <= max_replans <= 20: raise ValueError("invalid_max_replans")
    seed = {"normalized_goal": normalized, "workspace_root": str(workspace).replace("\\", "/").casefold(), "target_root": str(target).replace("\\", "/").casefold()}; goal_id = f"long-goal-{fingerprint(seed)[:20]}"; at = time_text(now)
    progress = calculate_goal_progress({}, [])
    value = {"contract": CONTRACT, "goal_id": goal_id, "original_input": str(original_input), "normalized_goal": normalized, "goal_title": normalized[:160], "goal_description": normalized, "workspace_root": str(workspace), "target_root": str(target), "constraints": ["controlled_execution", "path_containment", "operator_approval", "transactional_execution", "bounded_replanning"], "priority": priority, "goal_status": "draft", "created_at": at, "updated_at": at, "started_at": None, "completed_at": None, "pause_requested": False, "stop_requested": False, "current_milestone_id": None, "milestone_order": [], "milestones": {}, "mission_entry_references": [], "progress": progress, "success_criteria": ["All required milestones completed with persisted Mission evidence"], "completion_evidence": [], "failure": None, "replan_count": 0, "max_replans": max_replans, "replan_history": [], "plan_revision": 1, "memory_context_reference": None, "planning_feedback_reference": None, "processed_input_ids": [], "checkpoints": [], "reflection_reference": None, "experience_reference": None, "manual_review_required": False}
    return seal_long_horizon_goal(value)


def save_long_horizon_goal(value: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path).resolve(strict=False); destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(destination) or _unsafe(destination.parent): raise ValueError("unsafe_long_goal_state_path")
    sealed = seal_long_horizon_goal(value); reasons = validate_long_horizon_goal(sealed)
    if reasons: raise ValueError(";".join(reasons))
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle: handle.write(json.dumps(sealed, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination); return sealed


def load_long_horizon_goal(path: Any) -> dict[str, Any]:
    try: value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_long_goal_json") from exc
    reasons = validate_long_horizon_goal(value)
    if reasons: raise ValueError(";".join(reasons))
    return value


__all__ = ["CONTRACT", "GOAL_STATUSES", "MILESTONE_CONTRACT", "MILESTONE_STATUSES", "TERMINAL_GOALS", "TERMINAL_MILESTONES", "calculate_goal_progress", "create_long_horizon_goal", "load_long_horizon_goal", "save_long_horizon_goal", "seal_long_horizon_goal", "seal_milestone", "stable_milestone_order", "validate_long_horizon_goal", "validate_milestone"]
