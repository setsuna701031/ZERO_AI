from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.agent.runtime_long_horizon_goal import MILESTONE_CONTRACT, seal_milestone, stable_milestone_order
from core.runtime.runtime_operator_session import fingerprint, time_text


CONTRACT = "zero.agent.goal_milestone_plan.v1"
PLANNER_VERSION = "long-horizon-deterministic-v1"


def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _template(milestone: str, index: int, text: str, *, mutation: bool) -> dict[str, Any]:
    return {"mission_template_id": f"mission-template-{fingerprint({'milestone': milestone, 'index': index, 'text': text})[:16]}", "natural_language": text, "mutation_expected": mutation, "constraints": ["controlled_execution", "path_containment", "operator_approval"]}


def _website_specs() -> list[dict[str, Any]]:
    return [
        {"key": "inspect_workspace", "title": "Inspect workspace", "description": "Establish the bounded workspace planning checkpoint.", "templates": [], "criteria": ["Workspace scope is sealed before mutation"], "evidence": ["workspace_identity"]},
        {"key": "create_project_structure", "title": "Create project structure", "description": "Create a bounded project marker through Mission Runtime.", "templates": [_template("create_project_structure", 0, "create project.marker with content static website", mutation=True)], "criteria": ["Project marker exists"], "evidence": ["transaction_committed", "path_existence_evidence"]},
        {"key": "create_index_html", "title": "Create index.html", "description": "Create the website home page through Mission Runtime.", "templates": [_template("create_index_html", 0, "create index.html with content <!doctype html><html><head><link rel=stylesheet href=styles.css></head><body><h1>ZERO site</h1></body></html>", mutation=True)], "criteria": ["index.html exists"], "evidence": ["transaction_committed", "content_hash_evidence"]},
        {"key": "create_stylesheet", "title": "Create stylesheet", "description": "Create the site stylesheet through Mission Runtime.", "templates": [_template("create_stylesheet", 0, "create styles.css with content body { font-family: sans-serif; margin: 2rem; }", mutation=True)], "criteria": ["styles.css exists"], "evidence": ["transaction_committed", "content_hash_evidence"]},
        {"key": "verify_files", "title": "Verify files", "description": "Verify required website files using read-only Missions.", "templates": [_template("verify_files", 0, "check whether index.html exists", mutation=False), _template("verify_files", 1, "check whether styles.css exists", mutation=False)], "criteria": ["index.html and styles.css are evidenced"], "evidence": ["path_existence_evidence", "validation_evidence"]},
        {"key": "final_review", "title": "Final review", "description": "Close the project only after validation completes.", "templates": [_template("final_review", 0, "read index.html", mutation=False)], "criteria": ["Final read-only review completed"], "evidence": ["read_only_preview_evidence"]},
    ]


def _generic_specs(kind: str) -> list[dict[str, Any]]:
    filename = "PROJECT.md" if kind in {"document", "project"} else "workspace-report.txt"
    return [
        {"key": "inspect_workspace", "title": "Inspect workspace", "description": "Seal the workspace planning checkpoint.", "templates": [], "criteria": ["Workspace scope sealed"], "evidence": ["workspace_identity"]},
        {"key": "create_primary_artifact", "title": "Create primary artifact", "description": "Create the bounded project artifact.", "templates": [_template("create_primary_artifact", 0, f"create {filename} with content ZERO long horizon project", mutation=True)], "criteria": [f"{filename} exists"], "evidence": ["transaction_committed"]},
        {"key": "verify_artifact", "title": "Verify artifact", "description": "Verify the created artifact.", "templates": [_template("verify_artifact", 0, f"check whether {filename} exists", mutation=False)], "criteria": ["Artifact verification completed"], "evidence": ["validation_evidence"]},
        {"key": "final_review", "title": "Final review", "description": "Review the completed artifact.", "templates": [_template("final_review", 0, f"read {filename}", mutation=False)], "criteria": ["Review completed"], "evidence": ["read_only_preview_evidence"]},
    ]


def plan_goal_milestones(goal: Mapping[str, Any], *, memory_context: Mapping[str, Any] | None = None, planning_feedback: Mapping[str, Any] | None = None, now: Any = None) -> dict[str, Any]:
    item = _mapping(goal); text = str(item.get("normalized_goal") or "").casefold(); at = time_text(now)
    website = any(token in text for token in ("網站", "网页", "website", "static site", "首頁", "homepage"))
    generic_kind = "document" if any(token in text for token in ("文件", "document", "documentation")) else "project" if any(token in text for token in ("專案", "project", "workspace", "檔案", "file")) else None
    specs = _website_specs() if website else _generic_specs(generic_kind) if generic_kind else []
    context = _mapping(memory_context); feedback = _mapping(planning_feedback)
    risks = list(context.get("risk_notes") or [])[:8] + list(feedback.get("risk_notes") or [])[:8]
    validations = set(context.get("recommended_validations") or []) | set(feedback.get("recommended_validations") or [])
    memory_validation = bool(specs and validations and not any(spec["key"] == "validate_content" for spec in specs))
    if memory_validation:
        insert_at = max(1, len(specs) - 1)
        target_file = "index.html" if website else "PROJECT.md"
        specs.insert(insert_at, {"key": "validate_content", "title": "Validate content", "description": "Apply the memory-recommended read-only validation checkpoint.", "templates": [_template("validate_content", 0, f"read {target_file}", mutation=False)], "criteria": ["Recommended content validation completed"], "evidence": ["read_only_preview_evidence", "validation_evidence"]})
    milestones: dict[str, dict[str, Any]] = {}; previous = None
    for index, spec in enumerate(specs):
        seed = {"goal_id": item.get("goal_id"), "key": spec["key"], "dependencies": [previous] if previous else [], "planner_version": PLANNER_VERSION, "plan_revision": item.get("plan_revision", 1)}
        milestone_id = f"milestone-{fingerprint(seed)[:20]}"
        milestone = {"contract": MILESTONE_CONTRACT, "milestone_id": milestone_id, "milestone_key": spec["key"], "title": spec["title"], "description": spec["description"], "milestone_status": "pending", "dependencies": [previous] if previous else [], "priority": len(specs) - index, "created_at": at, "updated_at": at, "started_at": None, "completed_at": None, "mission_templates": deepcopy(spec["templates"]), "mission_entry_ids": [], "success_criteria": deepcopy(spec["criteria"]), "evidence_requirements": deepcopy(spec["evidence"]), "risk_notes": sorted(set(risks)), "approval_expected": any(template.get("mutation_expected") for template in spec["templates"]), "attempt_count": 0, "max_attempts": 3, "failure": None, "reflection_references": [], "experience_references": [], "planning_feedback_reference": feedback.get("feedback_id"), "plan_revision": item.get("plan_revision", 1), "projected_entry_states": {}}
        milestones[milestone_id] = seal_milestone(milestone); previous = milestone_id
    order = stable_milestone_order(milestones) if milestones else []
    value = {"contract": CONTRACT, "goal_id": item.get("goal_id"), "supported": bool(specs), "manual_review_required": not specs, "reason": None if specs else "unsupported_or_ambiguous_long_horizon_goal", "planner_version": PLANNER_VERSION, "milestones": milestones, "milestone_order": order, "memory_context_reference": context.get("context_fingerprint"), "planning_feedback_reference": feedback.get("feedback_id"), "memory_feedback_unavailable": not bool(context), "created_at": at}
    value["plan_fingerprint"] = fingerprint(value); return value


deterministic_milestone_planner = plan_goal_milestones

__all__ = ["CONTRACT", "PLANNER_VERSION", "deterministic_milestone_planner", "plan_goal_milestones"]
