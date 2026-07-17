from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_agent_planning_feedback import validate_planning_feedback
from core.runtime.runtime_operator_session import fingerprint


CONTRACT = "zero.runtime.memory_guided_goal_plan.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def summarize_goal_plan(goals: Any, *, limit: int = 20) -> list[dict[str, Any]]:
    return [
        {key: item.get(key) for key in ("goal_id", "natural_operation", "target_scope", "depends_on", "validation_requirements")}
        for item in [_mapping(raw) for raw in list(goals or [])[:limit]]
    ]


def apply_planning_feedback_to_goal_plan(
    goal_plan: list[Mapping[str, Any]],
    planning_feedback: Mapping[str, Any],
    *,
    planner_version: str | None = None,
) -> dict[str, Any]:
    feedback = _mapping(planning_feedback)
    reasons = validate_planning_feedback(feedback)
    if reasons:
        raise ValueError(";".join(reasons))
    before = [_mapping(goal) for goal in goal_plan]
    after = deepcopy(before)
    applied = [str(item.get("recommendation")) for item in feedback.get("applied_recommendations") or []]
    experience_ids = [str(item.get("experience_id")) for item in feedback.get("experience_references") or [] if item.get("experience_id")]
    recommended_validations = list(feedback.get("recommended_validations") or [])
    evidence_requirements = list(feedback.get("recommended_evidence") or [])
    risks = list(feedback.get("risk_notes") or [])
    if applied:
        remapped: dict[str, str] = {}
        for goal in after:
            old_id = str(goal.get("goal_id") or "")
            dependencies = [remapped.get(str(dependency), str(dependency)) for dependency in goal.get("depends_on") or []]
            seed = {"canonical_intent": feedback.get("mission_input_fingerprint"), "operation": goal.get("natural_operation"), "target": goal.get("target_scope"), "dependencies": dependencies, "applied_planning_recommendations": applied, "planner_version": planner_version or feedback.get("planner_version")}
            new_id = f"memory-goal-{fingerprint(seed)[:16]}"
            remapped[old_id] = new_id
            goal["goal_id"] = new_id
            goal["depends_on"] = dependencies
    for goal in after:
        operation = str(goal.get("natural_operation") or "")
        target = list(goal.get("target_scope") or [])
        relevant = operation in {"create_file", "create_directory", "check_exists"}
        goal["planning_feedback_reference"] = feedback["feedback_id"]
        goal["memory_experience_references"] = experience_ids
        goal["recommended_by_memory"] = bool(relevant and applied)
        goal["risk_notes"] = risks
        goal["evidence_requirements"] = evidence_requirements if relevant else []
        goal["planning_rationale"] = "memory_guided_validation" if relevant and applied else "baseline_deterministic_intent"
        goal["validation_origin"] = "memory" if relevant and recommended_validations else "baseline"
        if relevant:
            existing = list(goal.get("validation_requirements") or [])
            for validation in recommended_validations:
                if validation not in existing:
                    existing.append(validation)
            goal["validation_requirements"] = existing
        goal["planner_version"] = planner_version or feedback.get("planner_version")
    create_goals = [goal for goal in after if goal.get("natural_operation") == "create_file"]
    should_add_verify = "create_then_verify" in applied or "verify_file_exists" in recommended_validations or "verify_target_exists" in recommended_validations
    existing_checks = {(goal.get("natural_operation"), tuple(goal.get("target_scope") or [])) for goal in after}
    for create_goal in create_goals:
        target = tuple(create_goal.get("target_scope") or [])
        if not should_add_verify or ("check_exists", target) in existing_checks:
            continue
        seed = {
            "operation": "check_exists",
            "target": target,
            "depends_on": [create_goal.get("goal_id")],
            "applied_recommendations": applied,
            "planner_version": planner_version or feedback.get("planner_version"),
        }
        verify_id = f"memory-goal-{fingerprint(seed)[:16]}"
        verify = {
            "goal_id": verify_id,
            "goal_title": f"Check Exists: {target[0] if target else ''}",
            "goal_description": f"Verify the current mission target exists using controlled read-only runtime evidence.",
            "goal_type": "inspect",
            "goal_status": "pending",
            "priority": 0,
            "depends_on": [create_goal["goal_id"]],
            "required_capabilities": ["inspect"],
            "target_scope": list(target),
            "acceptance_criteria": [f"Target existence is evidenced for {target[0] if target else ''}"],
            "validation_requirements": recommended_validations or ["verify_file_exists"],
            "operator_confirmation_required": False,
            "natural_operation": "check_exists",
            "natural_operation_inputs": {"path": target[0] if target else ""},
            "max_attempts": 3,
            "planning_feedback_reference": feedback["feedback_id"],
            "memory_experience_references": experience_ids,
            "recommended_by_memory": True,
            "validation_origin": "memory",
            "risk_notes": risks,
            "evidence_requirements": evidence_requirements or ["path_existence_evidence"],
            "planning_rationale": "create_then_verify",
            "planner_version": planner_version or feedback.get("planner_version"),
        }
        after.append(verify)
        existing_checks.add(("check_exists", target))
    return {
        "contract": CONTRACT,
        "goal_plan": after,
        "goal_plan_before_feedback": summarize_goal_plan(before),
        "goal_plan_after_feedback": summarize_goal_plan(after),
        "applied_recommendations": deepcopy(feedback.get("applied_recommendations") or []),
        "ignored_recommendations": deepcopy(feedback.get("ignored_recommendations") or []),
        "planning_feedback_reference": feedback["feedback_id"],
    }


apply_planning_feedback = apply_planning_feedback_to_goal_plan

__all__ = ["CONTRACT", "apply_planning_feedback", "apply_planning_feedback_to_goal_plan", "summarize_goal_plan"]
