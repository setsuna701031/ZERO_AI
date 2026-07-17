from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping


RUNTIME_REPAIR_ADVISOR_SCHEMA = "zero.runtime.repair_advisor.v1"
_MISSING = object()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return deepcopy(list(value)) if isinstance(value, (list, tuple)) else []


def _nested_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, Mapping):
        if key in value:
            found.append(value[key])
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                found.extend(_nested_values(child, key))
    elif isinstance(value, (list, tuple)):
        for child in value:
            if isinstance(child, (Mapping, list, tuple)):
                found.extend(_nested_values(child, key))
    return found


def _first(value: Mapping[str, Any], key: str, default: Any = None) -> Any:
    values = _nested_values(value, key)
    return values[0] if values else default


def _unique_text(values: Any) -> list[str]:
    result: list[str] = []
    for value in _list(values):
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _task_completed(result: Mapping[str, Any]) -> bool:
    if "task_completed" in result:
        return result.get("task_completed") is True
    if result.get("ok") is not True:
        return False
    controlled = _mapping(_first(result, "controlled_mutation_result", {}))
    if controlled:
        return (
            controlled.get("ok") is True
            and controlled.get("mutation_completed") is True
            and controlled.get("validation_passed") is True
        )
    return True


def _failure_classification(
    result: Mapping[str, Any], observation: Mapping[str, Any]
) -> tuple[str, list[str]]:
    denial = _text(_first(result, "denial_reason", ""))
    normalized = denial.lower().replace("-", "_").replace(" ", "_")
    error_type = _text(_first(result, "error_type", ""))
    observation_status = _text(observation.get("observer_status"))
    evidence = _list(observation.get("evidence_observations"))
    parse_errors = [
        _text(item.get("parse_error"))
        for item in evidence
        if isinstance(item, Mapping) and _text(item.get("parse_error"))
    ]
    rollback_required = _first(result, "rollback_required", False) is True
    rollback_completed = _first(result, "rollback_completed", False) is True
    validation = _first(result, "validation_passed", _MISSING)
    mutation_completed = _first(result, "mutation_completed", _MISSING)

    if error_type or "runner_error" in normalized or "exception" in normalized:
        return "runner_exception", [error_type or denial or "runner_exception"]
    if observation_status == "observer_error":
        return "observation_failure", ["workspace_observer_error"]
    if parse_errors:
        return "evidence_parse_failure", parse_errors
    if any(term in normalized for term in ("unsafe_path", "traversal", "outside_workspace", "outside_workspace_root")):
        return "path_safety_failure", [denial]
    if "adapter" in normalized and "unavailable" in normalized:
        return "adapter_unavailable", [denial]
    if "adapter" in normalized and "incomplete" in normalized:
        return "adapter_incomplete", [denial]
    if rollback_required and not rollback_completed and result.get("ok") is not True:
        return "rollback_failure", [denial or "rollback_not_completed"]
    if validation is False:
        return "validation_failure", [denial or "validation_not_passed"]
    if mutation_completed is False or "mutation" in normalized:
        return "mutation_failure", [denial or "mutation_not_completed"]
    return "unknown_failure", [denial or "unclassified_failure"]


_CATEGORY_GUIDANCE = {
    "validation_failure": ("likely_repairable", "repair_advised", ["inspect_validation_output"], "request_operator_review"),
    "mutation_failure": ("likely_repairable", "repair_advised", ["inspect_validation_output", "request_operator_review"], "request_operator_review"),
    "path_safety_failure": ("blocked_by_safety_boundary", "manual_review_required", ["verify_target_path", "request_operator_review"], "request_operator_review"),
    "adapter_unavailable": ("blocked_by_safety_boundary", "manual_review_required", ["attach_governed_mutation_adapter", "request_operator_review"], "request_operator_review"),
    "adapter_incomplete": ("manual_only", "manual_review_required", ["attach_governed_mutation_adapter", "request_operator_review"], "request_operator_review"),
    "rollback_failure": ("manual_only", "manual_review_required", ["review_rollback_evidence", "request_operator_review"], "request_operator_review"),
    "observation_failure": ("insufficient_evidence", "insufficient_evidence", ["rerun_observation", "request_operator_review"], "rerun_observation"),
    "evidence_parse_failure": ("manual_only", "manual_review_required", ["review_rollback_evidence", "request_operator_review"], "request_operator_review"),
    "runner_exception": ("likely_repairable", "repair_advised", ["inspect_runner_exception", "request_operator_review"], "request_operator_review"),
    "unknown_failure": ("insufficient_evidence", "insufficient_evidence", ["request_operator_review"], "request_operator_review"),
}


def build_runtime_repair_advice(
    *,
    goal: Any,
    task_id: Any,
    runner_result: Mapping[str, Any] | None,
    workspace_observation: Mapping[str, Any] | None,
    memory_context: Mapping[str, Any] | None = None,
    decision_advice: Mapping[str, Any] | None = None,
    planner_advisor_bridge: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = _mapping(runner_result)
    observation = _mapping(workspace_observation)
    memory = _mapping(memory_context)
    decision = _mapping(decision_advice)
    planner = _mapping(planner_advisor_bridge)

    runner_ok = result.get("ok") is True
    task_completed = _task_completed(result)
    validation_value = _first(result, "validation_passed", _MISSING)
    validation_passed = validation_value is True
    observation_status = _text(observation.get("observer_status")) or "unavailable"
    issues = _list(observation.get("issues"))
    workspace_observed = observation.get("observation_complete") is True
    changed = _first(result, "changed_files", [])
    changed_count = len(changed) if isinstance(changed, (list, tuple)) else 0
    prior_denials = _unique_text(memory.get("prior_denial_reasons"))
    planner_risks = _unique_text(planner.get("avoid_risk_flags"))
    if not planner_risks:
        planner_risks = _unique_text(decision.get("risk_flags"))

    major_observation_issue = observation_status in {
        "observer_error", "denied_invalid_path", "denied_invalid_configuration"
    }
    success = (
        runner_ok and task_completed and validation_passed
        and workspace_observed and not major_observation_issue
    )

    if success:
        category = "none"
        status = "repair_not_needed"
        repairability = "not_applicable"
        failure_reasons: list[str] = []
        hints: list[str] = []
        next_action = "none"
        confidence = 1.0
        repair_needed = False
    elif (
        runner_ok
        and task_completed
        and not major_observation_issue
        and (validation_value is _MISSING or not workspace_observed)
    ):
        category = "none"
        status = "insufficient_evidence"
        repairability = "insufficient_evidence"
        failure_reasons = ["validation_or_observation_evidence_unavailable"]
        hints = ["rerun_observation", "request_operator_review"]
        next_action = "rerun_observation"
        confidence = 0.35
        repair_needed = False
    else:
        category, failure_reasons = _failure_classification(result, observation)
        repairability, status, hints, next_action = _CATEGORY_GUIDANCE[category]
        confidence = 0.8 if category not in {"unknown_failure", "observation_failure"} else 0.4
        repair_needed = True

    risk_flags = list(planner_risks)
    for denial in prior_denials:
        flag = f"prior_denial_risk:{denial}"
        if flag not in risk_flags:
            risk_flags.append(flag)
    if prior_denials:
        if "review_prior_denials" not in hints:
            hints.append("review_prior_denials")
        confidence = max(0.1, round(confidence - 0.1, 2))

    source_summary = {
        "runner_ok": runner_ok,
        "task_completed": task_completed,
        "validation_passed": validation_passed,
        "denial_reason": _text(_first(result, "denial_reason", "")),
        "error_type": _text(_first(result, "error_type", "")),
        "changed_files_count": changed_count,
        "workspace_observed": workspace_observed,
        "observation_status": observation_status,
        "observation_issue_count": len(issues),
        "rollback_required": _first(result, "rollback_required", False) is True,
        "rollback_completed": _first(result, "rollback_completed", False) is True,
        "memory_experience_count": int(memory.get("experience_count") or 0),
        "prior_denial_reasons": prior_denials,
        "planner_risk_flags": planner_risks,
    }
    return {
        "schema": RUNTIME_REPAIR_ADVISOR_SCHEMA,
        "ok": True,
        "advisor_status": status,
        "goal": _text(goal),
        "task_id": _text(task_id),
        "repair_needed": repair_needed,
        "repairability": repairability,
        "failure_category": category,
        "failure_reasons": failure_reasons,
        "repair_hints": hints,
        "recommended_next_action": next_action,
        "confidence": confidence,
        "source_summary": source_summary,
        "risk_flags": risk_flags,
        "read_only": True,
        "repair_execution_allowed": False,
        "mutation_allowed": False,
        "decision_authority": False,
        "requested_changes_modified": False,
        "autonomous_retry_allowed": False,
        "patch_generation_allowed": False,
    }


@dataclass(frozen=True)
class RuntimeRepairAdvisor:
    def advise(self, **kwargs: Any) -> dict[str, Any]:
        return build_runtime_repair_advice(**kwargs)


__all__ = [
    "RUNTIME_REPAIR_ADVISOR_SCHEMA",
    "RuntimeRepairAdvisor",
    "build_runtime_repair_advice",
]
