from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint

CONTRACT = "zero.runtime.goal_graph.v1"
GOAL_TYPES = {"inspect", "modify", "validate", "document", "composite"}
GOAL_STATUSES = {"pending", "ready", "waiting_for_operator", "running", "completed", "failed", "blocked", "cancelled"}
MAX_GOALS = 100
MAX_DEPENDENCIES = 20
MAX_DESCRIPTION_LENGTH = 8000
MAX_ACCEPTANCE_CRITERIA = 50
FORBIDDEN_FIELDS = {"command", "commands", "shell", "argv", "callable", "python_callable", "subprocess"}

def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}

def semantic_goal_fingerprint(goal: Mapping[str, Any]) -> str:
    value = _mapping(goal)
    semantic = {key: value.get(key) for key in ("goal_title", "goal_description", "goal_type", "depends_on", "required_capabilities", "target_scope", "acceptance_criteria", "validation_requirements")}
    return fingerprint(semantic)

def deterministic_goal_id(mission_id: str, goal: Mapping[str, Any], index: int = 0) -> str:
    return f"goal-{fingerprint({'mission_id': mission_id, 'index': index, 'semantic': semantic_goal_fingerprint(goal)})[:20]}"

def validate_goal(goal: Mapping[str, Any], *, mission_id: str | None = None) -> list[str]:
    value = _mapping(goal); reasons: list[str] = []
    if not str(value.get("goal_id") or "").strip(): reasons.append("missing_goal_id")
    if mission_id is not None and value.get("mission_id") != mission_id: reasons.append("cross_mission_goal")
    if value.get("goal_type") not in GOAL_TYPES: reasons.append("invalid_goal_type")
    if value.get("goal_status") not in GOAL_STATUSES: reasons.append("unknown_goal_status")
    description = str(value.get("goal_description") or "")
    if not description.strip(): reasons.append("empty_goal_description")
    if len(description) > MAX_DESCRIPTION_LENGTH: reasons.append("goal_description_too_long")
    priority = value.get("priority")
    if isinstance(priority, bool) or not isinstance(priority, int) or not -100 <= priority <= 100: reasons.append("invalid_priority")
    dependencies = value.get("depends_on")
    if not isinstance(dependencies, list): reasons.append("invalid_dependencies")
    elif len(dependencies) > MAX_DEPENDENCIES: reasons.append("dependency_limit_exceeded")
    criteria = value.get("acceptance_criteria")
    if not isinstance(criteria, list): reasons.append("invalid_acceptance_criteria")
    elif len(criteria) > MAX_ACCEPTANCE_CRITERIA: reasons.append("acceptance_criteria_limit_exceeded")
    if FORBIDDEN_FIELDS.intersection(value): reasons.append("executable_goal_fields_forbidden")
    return reasons

def stable_topological_order(goals: Mapping[str, Mapping[str, Any]]) -> list[str]:
    values = {str(key): _mapping(item) for key, item in goals.items()}
    incoming = {key: set(map(str, item.get("depends_on") or [])) for key, item in values.items()}
    order: list[str] = []
    while incoming:
        ready = sorted((key for key, deps in incoming.items() if not deps), key=lambda key: (-int(values[key].get("priority", 0)), key))
        if not ready: raise ValueError("goal_graph_cycle")
        for key in ready:
            order.append(key); incoming.pop(key)
        for deps in incoming.values(): deps.difference_update(ready)
    return order

def build_goal_graph(goals: Any, *, mission_id: str, confirmed: bool = False) -> dict[str, Any]:
    source = deepcopy(goals)
    if isinstance(source, Mapping): items = list(source.get("goals", source).values())
    elif isinstance(source, list): items = source
    else: raise ValueError("invalid_goal_plan")
    if not items: raise ValueError("empty_goal_graph")
    if len(items) > MAX_GOALS: raise ValueError("goal_limit_exceeded")
    normalized: dict[str, dict[str, Any]] = {}; semantics: set[str] = set()
    for index, raw in enumerate(items):
        item = _mapping(raw)
        item.setdefault("goal_id", deterministic_goal_id(mission_id, item, index)); item.setdefault("mission_id", mission_id)
        item.setdefault("goal_title", item.get("title") or f"Goal {index + 1}"); item.setdefault("goal_description", item.get("description"))
        item.setdefault("goal_type", "composite"); item.setdefault("goal_status", "pending"); item.setdefault("priority", 0)
        item.setdefault("depends_on", []); item.setdefault("required_capabilities", []); item.setdefault("target_scope", [])
        item.setdefault("acceptance_criteria", []); item.setdefault("validation_requirements", [])
        if item["goal_id"] in normalized: raise ValueError("duplicate_goal_id")
        reasons = validate_goal(item, mission_id=mission_id)
        if reasons: raise ValueError(";".join(reasons))
        semantic = semantic_goal_fingerprint(item)
        if semantic in semantics: raise ValueError("duplicate_semantic_goal")
        semantics.add(semantic); normalized[item["goal_id"]] = item
    for goal_id, item in normalized.items():
        for dependency in item["depends_on"]:
            if dependency == goal_id: raise ValueError("self_dependency")
            if dependency not in normalized: raise ValueError("missing_dependency")
    order = stable_topological_order(normalized)
    graph = {"contract": CONTRACT, "mission_id": mission_id, "goal_ids": sorted(normalized), "goal_order": order,
             "dependencies": {key: deepcopy(normalized[key]["depends_on"]) for key in sorted(normalized)}, "confirmed": bool(confirmed)}
    graph["graph_fingerprint"] = fingerprint(graph)
    return {"graph": graph, "goals": normalized, "goal_order": order}

def validate_goal_graph(graph: Mapping[str, Any], goals: Mapping[str, Mapping[str, Any]], *, mission_id: str) -> list[str]:
    reasons: list[str] = []
    value = _mapping(graph)
    if value.get("contract") != CONTRACT: reasons.append("invalid_goal_graph_contract")
    unsigned = _mapping(value); claimed = unsigned.pop("graph_fingerprint", None)
    if claimed != fingerprint(unsigned): reasons.append("graph_fingerprint_mismatch")
    try:
        order = stable_topological_order(goals)
        if order != value.get("goal_order"): reasons.append("goal_order_mismatch")
    except ValueError as exc: reasons.append(str(exc))
    for goal in goals.values(): reasons.extend(validate_goal(goal, mission_id=mission_id))
    return reasons

def ready_goal_ids(goals: Mapping[str, Mapping[str, Any]]) -> list[str]:
    result = []
    for goal_id in stable_topological_order(goals):
        goal = goals[goal_id]
        if goal.get("goal_status") in {"pending", "ready"} and all(goals[dep].get("goal_status") == "completed" for dep in goal.get("depends_on", [])): result.append(goal_id)
    return result

def propagate_dependency_states(goals: Mapping[str, Mapping[str, Any]], *, policy: str = "block_dependents") -> dict[str, dict[str, Any]]:
    if policy not in {"block_dependents", "continue_independent"}: raise ValueError("invalid_dependency_policy")
    result = {key: _mapping(value) for key, value in goals.items()}
    changed = True
    while changed:
        changed = False
        for goal in result.values():
            if goal.get("goal_status") not in {"pending", "ready"}: continue
            states = [result[dep].get("goal_status") for dep in goal.get("depends_on", [])]
            if any(status in {"failed", "blocked", "cancelled"} for status in states):
                goal["goal_status"] = "blocked"; goal["failure"] = {"reasons": ["dependency_not_completed"]}; changed = True
    return result

__all__ = ["CONTRACT", "GOAL_STATUSES", "GOAL_TYPES", "MAX_ACCEPTANCE_CRITERIA", "MAX_DEPENDENCIES", "MAX_DESCRIPTION_LENGTH", "MAX_GOALS", "build_goal_graph", "deterministic_goal_id", "propagate_dependency_states", "ready_goal_ids", "semantic_goal_fingerprint", "stable_topological_order", "validate_goal", "validate_goal_graph"]
