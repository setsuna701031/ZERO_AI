from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


RUNTIME_CHANGE_PROPOSAL_ENGINE_SCHEMA = (
    "zero.runtime.change_proposal_engine.v1"
)
_EVIDENCE_KEYS = (
    "result_path",
    "rollback_evidence_path",
    "git_commit_actuator_record_path",
    "governed_commit_record_path",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return deepcopy(list(value)) if isinstance(value, (list, tuple)) else []


def _unique_text(values: Any) -> list[str]:
    result: list[str] = []
    for value in _list(values):
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


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


def _safe_relative_path(value: Any) -> str:
    text = _text(value).replace("\\", "/")
    if not text or Path(text).is_absolute():
        return ""
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        return ""
    normalized = path.as_posix().removeprefix("./")
    return normalized if normalized not in {"", "."} else ""


def _target_files(
    result: Mapping[str, Any],
    observation: Mapping[str, Any],
    memory: Mapping[str, Any],
    planner: Mapping[str, Any],
) -> list[str]:
    current: list[str] = []
    changed = _first(result, "changed_files", [])
    for value in _list(changed):
        safe = _safe_relative_path(value)
        if safe and safe not in current:
            current.append(safe)
    for item in _list(observation.get("file_observations")):
        if not isinstance(item, Mapping) or item.get("exists") is not True:
            continue
        safe = _safe_relative_path(item.get("path"))
        if safe and safe not in current:
            current.append(safe)
    for value in _list(planner.get("preferred_paths")):
        safe = _safe_relative_path(value)
        if safe and safe not in current:
            current.append(safe)

    current_set = set(current)
    for value in _list(memory.get("successful_paths")):
        safe = _safe_relative_path(value)
        if safe and safe in current_set and safe not in current:
            current.append(safe)
    return current


def _evidence_references(
    result: Mapping[str, Any], observation: Mapping[str, Any]
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in _list(observation.get("evidence_observations")):
        if not isinstance(item, Mapping):
            continue
        evidence_type = _text(item.get("evidence_type"))
        path = _text(item.get("path"))
        if not path or (evidence_type, path) in seen:
            continue
        seen.add((evidence_type, path))
        references.append({
            "evidence_type": evidence_type,
            "path": path,
            "exists": item.get("exists") is True,
            "readable": item.get("readable") is True,
            "content_hash_sha256": _text(item.get("content_hash_sha256")),
        })
    for evidence_type in _EVIDENCE_KEYS:
        for value in _nested_values(result, evidence_type):
            path = _text(value)
            if not path or (evidence_type, path) in seen:
                continue
            seen.add((evidence_type, path))
            references.append({
                "evidence_type": evidence_type,
                "path": path,
                "exists": False,
                "readable": False,
                "content_hash_sha256": "",
            })
    return references


_CATEGORY_ACTIONS = {
    "validation_failure": ["inspect_validation_output", "review_target_file", "verify_expected_content", "rerun_validation_after_approved_change"],
    "mutation_failure": ["review_target_file", "verify_mutation_result", "request_operator_edit", "rerun_validation_after_approved_change"],
    "rollback_failure": ["inspect_rollback_evidence", "request_operator_edit"],
    "runner_exception": ["inspect_runner_exception", "request_operator_edit"],
    "adapter_unavailable": ["verify_adapter_attachment", "request_operator_edit"],
    "adapter_incomplete": ["verify_adapter_attachment", "request_operator_edit"],
    "path_safety_failure": ["review_target_file", "request_operator_edit"],
}


def _risk_level(category: str) -> str:
    if category in {"adapter_unavailable", "adapter_incomplete", "path_safety_failure"}:
        return "blocked"
    if category in {"rollback_failure", "observation_failure", "evidence_parse_failure"}:
        return "high"
    if category in {"mutation_failure", "runner_exception", "unknown_failure"}:
        return "medium"
    return "low"


def _validation_requirements(category: str) -> list[str]:
    requirements = [
        "run_focused_validation",
        "confirm_expected_file_state",
        "confirm_no_unapproved_paths_changed",
    ]
    additions = {
        "validation_failure": "inspect_validation_failure",
        "mutation_failure": "verify_mutation_result",
        "adapter_unavailable": "verify_adapter_attachment",
        "adapter_incomplete": "verify_adapter_attachment",
        "rollback_failure": "verify_rollback_integrity",
    }
    if category in additions:
        requirements.append(additions[category])
    return requirements


def build_runtime_change_proposal(
    *,
    goal: Any,
    task_id: Any,
    runner_result: Mapping[str, Any] | None,
    workspace_observation: Mapping[str, Any] | None,
    repair_advice: Mapping[str, Any] | None,
    memory_context: Mapping[str, Any] | None = None,
    decision_advice: Mapping[str, Any] | None = None,
    planner_advisor_bridge: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = _mapping(runner_result)
    observation = _mapping(workspace_observation)
    repair = _mapping(repair_advice)
    memory = _mapping(memory_context)
    decision = _mapping(decision_advice)
    planner = _mapping(planner_advisor_bridge)
    category = _text(repair.get("failure_category")) or "none"
    repairability = _text(repair.get("repairability")) or "not_applicable"
    repair_needed = repair.get("repair_needed") is True
    targets = _target_files(result, observation, memory, planner)
    evidence = _evidence_references(result, observation)
    issues = _unique_text(observation.get("issues"))
    planner_risks = _unique_text(planner.get("avoid_risk_flags"))
    if not planner_risks:
        planner_risks = _unique_text(decision.get("risk_flags"))
    risk_flags = _unique_text(repair.get("risk_flags"))
    for value in planner_risks:
        if value not in risk_flags:
            risk_flags.append(value)
    for value in _unique_text(memory.get("prior_denial_reasons")):
        flag = f"prior_denial_risk:{value}"
        if flag not in risk_flags:
            risk_flags.append(flag)
    for value in issues:
        flag = f"observation_issue:{value}"
        if flag not in risk_flags:
            risk_flags.append(flag)

    advisor_status = _text(repair.get("advisor_status"))
    eligible = (
        repair_needed
        and advisor_status in {"repair_advised", "manual_review_required"}
        and category != "none"
    )
    blocked = category in {
        "path_safety_failure", "adapter_unavailable", "adapter_incomplete"
    }
    if not repair_needed or category == "none":
        proposal_status = "proposal_not_needed"
    elif blocked:
        proposal_status = "proposal_blocked_by_safety"
    elif advisor_status == "insufficient_evidence" or not (targets or evidence):
        proposal_status = "insufficient_evidence"
    elif not eligible:
        proposal_status = "manual_review_required"
    elif advisor_status == "manual_review_required":
        proposal_status = "manual_review_required"
    else:
        proposal_status = "proposal_created"

    actions = deepcopy(_CATEGORY_ACTIONS.get(category, ["request_operator_edit"]))
    if targets and "compare_observed_hash" not in actions:
        actions.append("compare_observed_hash")
    risk_level = _risk_level(category)
    rollback_requirements: list[Any] = [
        {"rollback_plan_required": True},
        {"rollback_evidence_required": True},
    ]
    if targets:
        rollback_requirements.append("snapshot_target_files_before_change")

    proposal_seed = {
        "task_id": _text(task_id),
        "goal": _text(goal),
        "failure_category": category,
        "target_files": targets,
        "evidence_references": evidence,
    }
    digest = sha256(json.dumps(
        proposal_seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()[:16]
    proposal_id = f"change-proposal-{digest}"
    changed = _first(result, "changed_files", [])
    source_summary = {
        "runner_ok": result.get("ok") is True,
        "task_completed": _first(result, "task_completed", result.get("ok")) is True,
        "validation_passed": _first(result, "validation_passed", False) is True,
        "denial_reason": _text(_first(result, "denial_reason", "")),
        "error_type": _text(_first(result, "error_type", "")),
        "failure_category": category,
        "repairability": repairability,
        "changed_files_count": len(changed) if isinstance(changed, (list, tuple)) else 0,
        "observed_file_count": len(_list(observation.get("file_observations"))),
        "observation_issue_count": len(issues),
        "memory_experience_count": int(memory.get("experience_count") or 0),
        "prior_denial_reasons": _unique_text(memory.get("prior_denial_reasons")),
        "planner_risk_flags": planner_risks,
    }
    approval_status = "not_required" if proposal_status == "proposal_not_needed" else "pending"
    return {
        "schema": RUNTIME_CHANGE_PROPOSAL_ENGINE_SCHEMA,
        "ok": True,
        "proposal_status": proposal_status,
        "proposal_id": proposal_id,
        "goal": _text(goal),
        "task_id": _text(task_id),
        "repair_needed": repair_needed,
        "failure_category": category,
        "repairability": repairability,
        "proposal": {
            "title": f"Operator review proposal for {category}",
            "summary": "Review existing runtime evidence before any approved change.",
            "reason": _text(_first(repair, "failure_reasons", [""])[0] if _list(repair.get("failure_reasons")) else category),
            "target_files": targets if proposal_status != "proposal_not_needed" else [],
            "recommended_actions": actions if proposal_status != "proposal_not_needed" else [],
            "expected_effect": "Resolve the reported failure while preserving runtime safety boundaries.",
            "risk_level": risk_level,
            "risk_flags": risk_flags,
            "validation_requirements": _validation_requirements(category),
            "rollback_requirements": rollback_requirements,
            "evidence_references": evidence,
        },
        "source_summary": source_summary,
        "read_only": True,
        "mutation_allowed": False,
        "patch_generation_allowed": False,
        "repair_execution_allowed": False,
        "decision_authority": False,
        "requested_changes_modified": False,
        "autonomous_apply_allowed": False,
        "requires_operator_approval": True,
        "approval_status": approval_status,
    }


@dataclass(frozen=True)
class RuntimeChangeProposalEngine:
    def propose(self, **kwargs: Any) -> dict[str, Any]:
        return build_runtime_change_proposal(**kwargs)


__all__ = [
    "RUNTIME_CHANGE_PROPOSAL_ENGINE_SCHEMA",
    "RuntimeChangeProposalEngine",
    "build_runtime_change_proposal",
]
