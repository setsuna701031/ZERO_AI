from __future__ import annotations

"""
ZERO Engineering Task Runner v1.

This module turns a real engineering task payload into a repeatable result
bundle while preserving the existing AER/work-package execution path.

Boundary:
- Payload normalization and result packaging only.
- No direct repository writes.
- No runtime dispatch.
- No allowlist changes.
- Execution stays in WorkPackageScheduler -> WorkPackageIntake -> run_repo_edit.
"""

import copy
import json
import time
from pathlib import Path
from typing import Any, Mapping

from core.planning.planner import Planner
from core.tasks.work_package_scheduler import WorkPackageScheduler


SCHEMA = "zero.engineering_task_runner.v1"
REQUIREMENT_SUMMARY_SCHEMA = "zero.engineering_task.requirement_summary.v1"
FINAL_BUNDLE_SCHEMA = "zero.engineering_task.result_bundle.v1"
MULTI_STEP_PLAN_SCHEMA = "zero.engineering_task.multi_step_plan.v1"
MULTI_STEP_BUNDLE_SCHEMA = "zero.engineering_task.multi_step_result_bundle.v1"
MULTI_STEP_OBSERVATION_SCHEMA = "zero.engineering_task.step_observation.v1"
MULTI_STEP_DECISION_SCHEMA = "zero.engineering_task.observation_decision.v1"
MULTI_STEP_STATE_SCHEMA = "zero.engineering_task.multi_step_state.v1"
TASK_BREAKDOWN_SCHEMA = "zero.engineering_task.task_breakdown.v1"
GENERATED_TASK_SCHEMA = "zero.engineering_task.generated_task.v1"
ITERATION_TRACE_SCHEMA = "zero.engineering_task.iteration_trace.v1"
CANDIDATE_TASK_SCHEMA = "zero.engineering_task.candidate_task.v1"
CANDIDATE_EVALUATION_SCHEMA = "zero.engineering_task.candidate_evaluation.v1"
SELECTED_TASK_SCHEMA = "zero.engineering_task.selected_task.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _normalize_relative_path(value: Any) -> str:
    return _clean_text(value).replace("\\", "/")


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_state_id(value: Any) -> str:
    text = _clean_text(value, "engineering_task")
    safe = []
    for char in text:
        if char.isalnum() or char in ("-", "_", "."):
            safe.append(char)
        else:
            safe.append("_")
    cleaned = "".join(safe).strip("._-")
    return cleaned[:120] or "engineering_task"


def _safe_file_stem(value: Any) -> str:
    return _safe_state_id(value).lower()


def _multi_step_state_path(repo_root: str | Path, package_id: str) -> Path:
    return Path(repo_root) / "workspace" / "work_packages" / f"{_safe_state_id(package_id)}.engineering_state.json"


def _display_path(path: Path, repo_root: str | Path) -> str:
    try:
        return str(path.relative_to(Path(repo_root)))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _task_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    package = payload.get("package")
    if isinstance(package, Mapping):
        return dict(package)
    work_package = payload.get("work_package")
    if isinstance(work_package, Mapping):
        return dict(work_package)
    return dict(payload)


def _raw_step_payloads(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    task = _task_payload(payload)
    for key in ("steps", "engineering_steps", "task_steps"):
        steps = task.get(key)
        if isinstance(steps, list):
            return [dict(item) for item in steps if isinstance(item, Mapping)]
    return []


def _is_multi_step_payload(payload: Mapping[str, Any]) -> bool:
    return bool(_raw_step_payloads(payload))


def _has_executable_payload(payload: Mapping[str, Any]) -> bool:
    return _is_multi_step_payload(payload) or bool(_raw_edit_payloads(payload))


def _raw_edit_payloads(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    task = _task_payload(payload)
    if _raw_step_payloads(payload):
        edits: list[dict[str, Any]] = []
        for step in _raw_step_payloads(payload):
            edits.extend(_raw_edit_payloads(step))
        return edits

    edits = task.get("edits")
    if isinstance(edits, list):
        return [dict(item) for item in edits if isinstance(item, Mapping)]

    edit = task.get("edit")
    if isinstance(edit, list):
        return [dict(item) for item in edit if isinstance(item, Mapping)]
    if isinstance(edit, Mapping):
        return [dict(edit)]

    target_path = task.get("target_path") or task.get("path")
    operation = task.get("operation")
    if target_path or operation:
        edit_payload: dict[str, Any] = {
            "operation": _clean_text(operation, "write_file"),
            "target_path": _normalize_relative_path(target_path),
            "content": str(task.get("content") or ""),
        }
        verify_contains = _clean_text(task.get("verify_contains") or task.get("expect_contains"))
        if verify_contains:
            edit_payload["verify_contains"] = verify_contains
        return [edit_payload]

    return []


def build_requirement_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact operator-facing requirement summary."""

    task = _task_payload(payload)
    edits = _raw_edit_payloads(payload)
    target_files = [
        _normalize_relative_path(item.get("target_path") or item.get("path"))
        for item in edits
        if _normalize_relative_path(item.get("target_path") or item.get("path"))
    ]
    package_id = _clean_text(
        task.get("package_id") or task.get("task_id") or payload.get("task_id"),
        "engineering_task",
    )
    goal = _clean_text(task.get("goal") or task.get("title") or payload.get("goal"), package_id)
    acceptance = task.get("acceptance") or task.get("acceptance_criteria")
    if isinstance(acceptance, str):
        acceptance_items = [acceptance]
    elif isinstance(acceptance, list):
        acceptance_items = [str(item) for item in acceptance if str(item).strip()]
    else:
        acceptance_items = []

    return {
        "schema": REQUIREMENT_SUMMARY_SCHEMA,
        "package_id": package_id,
        "goal": goal,
        "mode": _clean_text(task.get("mode"), "execute"),
        "approval": bool(task.get("approval") or task.get("approved")),
        "target_files": target_files,
        "operation_count": len(edits),
        "acceptance": acceptance_items,
        "acceptance_criteria": acceptance_items,
        "verification_expectations": [
            _clean_text(item.get("verify_contains") or item.get("expect_contains"))
            for item in edits
            if _clean_text(item.get("verify_contains") or item.get("expect_contains"))
        ],
    }


def _goal_requires_blocked_generated_step(goal: str) -> bool:
    normalized = goal.lower()
    return "blocked generated step" in normalized or "blocked runtime target" in normalized


def decompose_engineering_goal(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a goal-only engineering task into executable AER steps."""

    task = _task_payload(payload)
    package_id = _clean_text(task.get("package_id") or task.get("task_id") or payload.get("task_id"), "engineering_goal")
    goal = _clean_text(task.get("goal") or task.get("title") or payload.get("goal"), package_id)
    safe_id = _safe_file_stem(package_id)
    blocked_second_step = _goal_requires_blocked_generated_step(goal)
    first_package_id = f"{package_id}_breakdown"
    second_package_id = f"{package_id}_result"
    first_target = f"workspace/generated_engineering/{safe_id}_breakdown.txt"
    second_target = (
        f"core/runtime/{safe_id}_blocked_generated_step.py"
        if blocked_second_step
        else f"workspace/generated_engineering/{safe_id}_result.txt"
    )
    acceptance = task.get("acceptance") or task.get("acceptance_criteria")
    if isinstance(acceptance, str):
        acceptance_criteria = [acceptance]
    elif isinstance(acceptance, list):
        acceptance_criteria = [str(item) for item in acceptance if str(item).strip()]
    else:
        acceptance_criteria = [
            "goal decomposes into executable engineering steps",
            "generated steps execute through the existing AER work-package path",
            "final result bundle includes observations and replan decisions",
        ]

    steps = [
        {
            "package_id": first_package_id,
            "goal": f"Write requirement breakdown for {goal}",
            "edits": [
                {
                    "operation": "write_file",
                    "target_path": first_target,
                    "content": f"Goal: {goal}\nStep: requirement breakdown\n",
                    "verify_contains": f"Goal: {goal}",
                }
            ],
        },
        {
            "package_id": second_package_id,
            "goal": f"Produce generated engineering result for {goal}",
            "replan_from_observation": {
                "goal_template": "Produce generated result after {previous_package_id}",
                "target_path_template": second_target,
                "content_template": "Generated result for {previous_package_id}\nObserved: {first_changed_file}\n",
                "verify_contains_template": "Observed: {first_changed_file}",
                "reason_template": "observed {first_changed_file}",
            },
            "edits": [
                {
                    "operation": "write_file",
                    "target_path": second_target,
                    "content": f"Generated result for {package_id}\n",
                    "verify_contains": f"Generated result for {package_id}",
                }
            ],
        },
    ]
    dependencies = [
        {
            "step_id": second_package_id,
            "depends_on": [first_package_id],
            "reason": "result step uses the first step observation",
        }
    ]
    execution_order = [first_package_id, second_package_id]
    task_breakdown = {
        "schema": TASK_BREAKDOWN_SCHEMA,
        "package_id": package_id,
        "goal": goal,
        "steps": [
            {
                "step_index": index,
                "package_id": step["package_id"],
                "goal": step["goal"],
                "target_files": [
                    _normalize_relative_path(edit.get("target_path"))
                    for edit in step.get("edits", [])
                    if isinstance(edit, Mapping)
                ],
            }
            for index, step in enumerate(steps, start=1)
        ],
        "dependencies": dependencies,
        "acceptance_criteria": acceptance_criteria,
        "execution_order": execution_order,
        "full_file_outputs_only": True,
        "existing_aer_path_required": True,
    }
    decomposed = copy.deepcopy(dict(payload))
    decomposed.update(
        {
            "task_id": package_id,
            "package_id": package_id,
            "mode": _clean_text(task.get("mode"), "execute"),
            "approval": bool(task.get("approval") if "approval" in task else True),
            "acceptance": acceptance_criteria,
            "acceptance_criteria": acceptance_criteria,
            "steps": steps,
            "task_breakdown": task_breakdown,
            "dependencies": dependencies,
            "execution_order": execution_order,
            "decomposed_from_goal": True,
        }
    )
    return decomposed


def _force_transactional_execute_payload(work_package: Mapping[str, Any], source_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Force execute tasks through the existing multi-edit transaction path."""

    package = copy.deepcopy(dict(work_package))
    if _clean_text(package.get("mode"), "execute") != "execute":
        return package
    if isinstance(package.get("edits"), list):
        return package

    raw_edits = _raw_edit_payloads(source_payload)
    if raw_edits:
        package["edits"] = raw_edits
        package.pop("edit", None)
    return package


def normalize_engineering_task_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a real engineering task into the existing work-package contract."""

    planner = Planner()
    normalized = planner.normalize_aer_execution_intent(dict(payload), user_input=_clean_text(payload.get("goal")))
    work_package = normalized.get("work_package") if isinstance(normalized, Mapping) else None
    if not isinstance(work_package, Mapping):
        raise ValueError("engineering_task_payload_did_not_normalize_to_work_package")

    work_package_payload = _force_transactional_execute_payload(work_package, payload)
    work_package_payload.pop("repo_root", None)
    return {
        "schema": "zero.engineering_task.normalized_payload.v1",
        "intent": "work_package",
        "work_package": work_package_payload,
        "normalizer": "Planner.normalize_aer_execution_intent",
        "transactional_execute_payload": isinstance(work_package_payload.get("edits"), list),
    }


def _format_from_observation(template: Any, observation: Mapping[str, Any]) -> str:
    text = str(template or "")
    changed_files = observation.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = []
    values = {
        "changed_files": ", ".join(str(item) for item in changed_files),
        "first_changed_file": str(changed_files[0]) if changed_files else "",
        "previous_package_id": str(observation.get("package_id") or ""),
        "previous_result_path": str(observation.get("result_path") or ""),
        "previous_reason": str(observation.get("reason") or ""),
        "previous_ok": str(bool(observation.get("ok"))).lower(),
    }
    try:
        return text.format(**values)
    except Exception:
        return text


def _apply_observation_derivation(step_payload: dict[str, Any], observation: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(observation, Mapping):
        return step_payload

    derive = step_payload.get("derive_from_observation")
    if not isinstance(derive, Mapping):
        return step_payload

    derived = copy.deepcopy(step_payload)
    first_edit: dict[str, Any] | None = None
    edits = derived.get("edits")
    if isinstance(edits, list) and edits and isinstance(edits[0], Mapping):
        first_edit = dict(edits[0])
        edits[0] = first_edit
    elif isinstance(derived.get("edit"), Mapping):
        first_edit = dict(derived["edit"])
        derived["edit"] = first_edit

    def set_value(field: str, value: str) -> None:
        if first_edit is not None:
            first_edit[field] = value
        else:
            derived[field] = value

    if "content_template" in derive:
        set_value("content", _format_from_observation(derive.get("content_template"), observation))
    if "verify_contains_template" in derive:
        set_value("verify_contains", _format_from_observation(derive.get("verify_contains_template"), observation))
    if "target_path_template" in derive:
        set_value("target_path", _format_from_observation(derive.get("target_path_template"), observation))
    if "goal_template" in derive:
        derived["goal"] = _format_from_observation(derive.get("goal_template"), observation)
    if "instructions_template" in derive:
        derived["instructions"] = _format_from_observation(derive.get("instructions_template"), observation)

    metadata = dict(derived.get("metadata") or {})
    metadata["derived_from_observation"] = True
    metadata["source_observation"] = {
        "step_index": observation.get("step_index"),
        "package_id": observation.get("package_id"),
        "changed_files": list(observation.get("changed_files") or []),
        "result_path": observation.get("result_path"),
    }
    derived["metadata"] = metadata
    return derived


def _apply_observation_replan(step_payload: dict[str, Any], observation: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(observation, Mapping):
        return step_payload

    replan = step_payload.get("replan_from_observation")
    if not isinstance(replan, Mapping):
        return step_payload

    replanned = _apply_observation_derivation(
        {
            **copy.deepcopy(step_payload),
            "derive_from_observation": dict(replan),
        },
        observation,
    )
    metadata = dict(replanned.get("metadata") or {})
    metadata["replanned_from_observation"] = True
    metadata["replan_reason"] = _format_from_observation(
        replan.get("reason_template") or replan.get("reason") or "next_step_replanned_from_observation",
        observation,
    )
    replanned["metadata"] = metadata
    return replanned


def _generated_task_record(
    *,
    step_index: int,
    step_payload: Mapping[str, Any],
    previous_observation: Mapping[str, Any] | None,
    generated_reason: str,
) -> dict[str, Any]:
    metadata = _as_mapping(step_payload.get("metadata"))
    return {
        "schema": GENERATED_TASK_SCHEMA,
        "step_index": int(step_index),
        "package_id": str(step_payload.get("package_id") or step_payload.get("task_id") or ""),
        "goal": str(step_payload.get("goal") or ""),
        "generated_from_observation": isinstance(previous_observation, Mapping),
        "source_observation": {
            "step_index": previous_observation.get("step_index") if isinstance(previous_observation, Mapping) else None,
            "package_id": previous_observation.get("package_id") if isinstance(previous_observation, Mapping) else "",
            "changed_files": list(previous_observation.get("changed_files") or []) if isinstance(previous_observation, Mapping) else [],
            "status": previous_observation.get("status") if isinstance(previous_observation, Mapping) else "",
        },
        "generated_reason": str(generated_reason or "initial_engineering_task"),
        "derived_from_observation": bool(metadata.get("derived_from_observation")),
        "replanned_from_observation": bool(metadata.get("replanned_from_observation")),
        "full_file_outputs_only": True,
        "enters_existing_engineering_task_runner_path": True,
        "existing_runner_entrypoint": "_run_single_engineering_task",
        "existing_aer_path": "Planner.normalize_aer_execution_intent -> WorkPackageScheduler.submit -> submit_work_package",
        "existing_intake_path": "WorkPackageIntake -> change_set",
        "task_payload": copy.deepcopy(dict(step_payload)),
    }


def _append_iteration_trace(
    trace: list[dict[str, Any]],
    *,
    event: str,
    step_index: int = 0,
    package_id: str = "",
    detail: Mapping[str, Any] | None = None,
) -> None:
    trace.append(
        {
            "schema": ITERATION_TRACE_SCHEMA,
            "event": str(event),
            "step_index": int(step_index or 0),
            "package_id": str(package_id or ""),
            "detail": copy.deepcopy(dict(detail)) if isinstance(detail, Mapping) else {},
        }
    )


def _step_target_paths(step_payload: Mapping[str, Any]) -> list[str]:
    targets: list[str] = []
    for edit in _raw_edit_payloads(step_payload):
        target = _normalize_relative_path(edit.get("target_path") or edit.get("path"))
        if target:
            targets.append(target)
    return targets


def _candidate_is_blocked_without_execution(step_payload: Mapping[str, Any]) -> bool:
    return any(path.startswith("core/runtime/") for path in _step_target_paths(step_payload))


def _candidate_priority(step_payload: Mapping[str, Any]) -> int:
    metadata = _as_mapping(step_payload.get("metadata"))
    raw_value = metadata.get("selection_priority")
    if raw_value is None:
        raw_value = step_payload.get("selection_priority")
    try:
        return int(raw_value)
    except Exception:
        return 0


def _candidate_task_record(
    *,
    step_index: int,
    candidate_index: int,
    step_payload: Mapping[str, Any],
    previous_observation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    blocked = _candidate_is_blocked_without_execution(step_payload)
    return {
        "schema": CANDIDATE_TASK_SCHEMA,
        "step_index": int(step_index),
        "candidate_index": int(candidate_index),
        "package_id": str(step_payload.get("package_id") or step_payload.get("task_id") or ""),
        "goal": str(step_payload.get("goal") or ""),
        "generated_from_observation": isinstance(previous_observation, Mapping),
        "source_observation": {
            "step_index": previous_observation.get("step_index") if isinstance(previous_observation, Mapping) else None,
            "package_id": previous_observation.get("package_id") if isinstance(previous_observation, Mapping) else "",
            "changed_files": list(previous_observation.get("changed_files") or []) if isinstance(previous_observation, Mapping) else [],
        },
        "target_paths": _step_target_paths(step_payload),
        "selection_priority": _candidate_priority(step_payload),
        "blocked_without_execution": blocked,
        "full_file_outputs_only": True,
        "would_enter_existing_engineering_task_runner_path": True,
        "existing_aer_path": "Planner.normalize_aer_execution_intent -> WorkPackageScheduler.submit -> submit_work_package",
        "task_payload": copy.deepcopy(dict(step_payload)),
    }


def _raw_candidate_task_payloads(raw_step: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("candidate_next_tasks", "candidate_tasks", "candidate_tasks_from_observation"):
        value = raw_step.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _evaluate_candidate_tasks(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for candidate in candidates:
        priority = int(candidate.get("selection_priority") or 0)
        blocked = bool(candidate.get("blocked_without_execution"))
        score = priority - (1000 if blocked else 0)
        reasons = []
        if blocked:
            reasons.append("candidate_target_would_be_blocked_by_existing_work_package_intake")
        if priority:
            reasons.append(f"selection_priority:{priority}")
        if not reasons:
            reasons.append("default_candidate_priority")
        evaluations.append(
            {
                "schema": CANDIDATE_EVALUATION_SCHEMA,
                "step_index": candidate.get("step_index"),
                "candidate_index": candidate.get("candidate_index"),
                "package_id": str(candidate.get("package_id") or ""),
                "score": score,
                "blocked_without_execution": blocked,
                "reason": "; ".join(reasons),
                "existing_aer_path_required": True,
                "direct_write_shortcut": False,
            }
        )
    return evaluations


def _select_candidate_task(
    *,
    step_index: int,
    candidates: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    if not candidates:
        return {}
    evaluation_by_index = {int(item.get("candidate_index") or 0): item for item in evaluations}
    selected = max(
        candidates,
        key=lambda item: (
            int(evaluation_by_index.get(int(item.get("candidate_index") or 0), {}).get("score") or 0),
            -int(item.get("candidate_index") or 0),
        ),
    )
    selected_index = int(selected.get("candidate_index") or 0)
    selected_evaluation = evaluation_by_index.get(selected_index, {})
    return {
        "schema": SELECTED_TASK_SCHEMA,
        "step_index": int(step_index),
        "candidate_index": selected_index,
        "package_id": str(selected.get("package_id") or ""),
        "selected_task": copy.deepcopy(selected),
        "selection_reason": str(selected_evaluation.get("reason") or "highest_scoring_candidate"),
        "selection_score": int(selected_evaluation.get("score") or 0),
        "blocked_without_execution": bool(selected.get("blocked_without_execution")),
        "only_selected_task_executes": True,
        "existing_engineering_task_runner_path": "_run_single_engineering_task",
        "existing_aer_path": "Planner.normalize_aer_execution_intent -> WorkPackageScheduler.submit -> submit_work_package",
    }


def _build_step_payload(
    *,
    parent_payload: Mapping[str, Any],
    raw_step: Mapping[str, Any],
    step_index: int,
    previous_observation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    parent = _task_payload(parent_payload)
    parent_id = _clean_text(parent.get("package_id") or parent.get("task_id") or parent_payload.get("task_id"), "engineering_task")
    step = _apply_observation_derivation(copy.deepcopy(dict(raw_step)), previous_observation)
    step = _apply_observation_replan(step, previous_observation)
    package_id = _clean_text(step.get("package_id") or step.get("task_id"), f"{parent_id}_step_{step_index}")

    step_payload = {
        "task_type": "engineering_task",
        "task_id": package_id,
        "package_id": package_id,
        "goal": _clean_text(step.get("goal") or step.get("title") or parent.get("goal"), f"{parent_id} step {step_index}"),
        "mode": _clean_text(step.get("mode") or parent.get("mode"), "execute"),
        "approval": bool(step.get("approval") if "approval" in step else parent.get("approval") or parent.get("approved")),
        "acceptance": copy.deepcopy(step.get("acceptance") or parent.get("acceptance") or parent.get("acceptance_criteria") or []),
        "metadata": copy.deepcopy(step.get("metadata") or {}),
    }

    for key in (
        "kind",
        "title",
        "scope_paths",
        "report_path",
        "instructions",
        "operation",
        "target_path",
        "path",
        "content",
        "verify_contains",
        "expect_contains",
        "edit",
        "edits",
        "selection_priority",
    ):
        if key in step:
            step_payload[key] = copy.deepcopy(step[key])

    step_payload.pop("steps", None)
    step_payload.pop("engineering_steps", None)
    step_payload.pop("task_steps", None)
    step_payload.pop("candidate_next_tasks", None)
    step_payload.pop("candidate_tasks", None)
    step_payload.pop("candidate_tasks_from_observation", None)
    step_payload.pop("derive_from_observation", None)
    step_payload.pop("replan_from_observation", None)
    return step_payload


def build_multi_step_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    parent = _task_payload(payload)
    package_id = _clean_text(parent.get("package_id") or parent.get("task_id") or payload.get("task_id"), "engineering_task")
    raw_steps = _raw_step_payloads(payload)
    task_breakdown = _as_mapping(parent.get("task_breakdown"))
    dependencies = parent.get("dependencies") if isinstance(parent.get("dependencies"), list) else task_breakdown.get("dependencies", [])
    acceptance_criteria = (
        parent.get("acceptance_criteria")
        if isinstance(parent.get("acceptance_criteria"), list)
        else parent.get("acceptance")
        if isinstance(parent.get("acceptance"), list)
        else task_breakdown.get("acceptance_criteria", [])
    )
    execution_order = parent.get("execution_order") if isinstance(parent.get("execution_order"), list) else task_breakdown.get("execution_order", [])
    return {
        "schema": MULTI_STEP_PLAN_SCHEMA,
        "package_id": package_id,
        "goal": _clean_text(parent.get("goal") or parent.get("title"), package_id),
        "task_breakdown": task_breakdown,
        "step_count": len(raw_steps),
        "steps": [
            {
                "step_index": index,
                "package_id": _clean_text(step.get("package_id") or step.get("task_id"), f"{package_id}_step_{index}"),
                "goal": _clean_text(step.get("goal") or step.get("title") or parent.get("goal"), f"{package_id} step {index}"),
                "derived_from_observation": isinstance(step.get("derive_from_observation"), Mapping),
                "operation_count": len(_raw_edit_payloads(step)),
            }
            for index, step in enumerate(raw_steps, start=1)
        ],
        "dependencies": copy.deepcopy(dependencies),
        "acceptance_criteria": copy.deepcopy(acceptance_criteria),
        "execution_order": copy.deepcopy(execution_order),
        "decomposed_from_goal": bool(parent.get("decomposed_from_goal")),
        "flow": ["task", "plan", "execute", "observe", "replan_if_needed", "continue", "complete", "result_bundle"],
        "execution_path": {
            "existing_engineering_task_runner": True,
            "existing_aer_work_package_path": "Planner.normalize_aer_execution_intent -> WorkPackageScheduler.submit -> submit_work_package",
            "existing_change_set_path": "WorkPackageIntake -> change_set",
            "no_new_runtime_path": True,
            "direct_write_shortcut": False,
            "full_file_outputs_only": True,
        },
    }


def _observe_step_result(*, step_index: int, step_payload: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    bundle = _as_mapping(result.get("result_bundle"))
    work_package_result = _as_mapping(result.get("work_package_result"))
    change_set = _as_mapping(result.get("change_set"))
    artifact_paths = _as_mapping(bundle.get("artifact_paths"))
    changed_files = work_package_result.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = change_set.get("files") if isinstance(change_set.get("files"), list) else []
    ok = bool(result.get("ok"))
    blocked = bool(work_package_result.get("blocked"))
    status = "completed" if ok else "blocked" if blocked else "failed"
    reason = _clean_text(work_package_result.get("reason") or result.get("error") or result.get("final_message"))
    return {
        "schema": MULTI_STEP_OBSERVATION_SCHEMA,
        "step_index": step_index,
        "package_id": str(result.get("package_id") or step_payload.get("package_id") or step_payload.get("task_id") or ""),
        "ok": ok,
        "status": status,
        "blocked": blocked,
        "reason": reason,
        "changed_files": list(changed_files),
        "result_bundle_schema": str(bundle.get("schema") or ""),
        "change_set_id": str(change_set.get("change_set_id") or ""),
        "verification_ok": bool(_as_mapping(bundle.get("verification_result")).get("ok")),
        "rollback_performed": bool(_as_mapping(bundle.get("rollback_status")).get("rollback_performed")),
        "result_path": str(artifact_paths.get("result_path") or work_package_result.get("result_path") or ""),
        "next_action": "continue" if ok else "stop_safely",
        "should_replan_candidate": bool((not ok) and not blocked),
        "should_fail_candidate": bool(blocked),
    }


def _next_step_uses_observation_replan(raw_step: Mapping[str, Any] | None) -> bool:
    return isinstance(_as_mapping(raw_step).get("replan_from_observation"), Mapping)


def _next_step_uses_observation_derivation(raw_step: Mapping[str, Any] | None) -> bool:
    return isinstance(_as_mapping(raw_step).get("derive_from_observation"), Mapping)


def _decide_after_observation(
    *,
    observation: Mapping[str, Any],
    next_raw_step: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not bool(observation.get("ok")):
        return {
            "schema": MULTI_STEP_DECISION_SCHEMA,
            "step_index": observation.get("step_index"),
            "observed_package_id": str(observation.get("package_id") or ""),
            "decision": "stop_safely",
            "next_action": "stop_safely",
            "replanned": False,
            "reason": str(observation.get("reason") or "step_failed"),
            "blocked": bool(observation.get("blocked")),
            "existing_rollback_preserved": True,
        }

    if _next_step_uses_observation_replan(next_raw_step):
        return {
            "schema": MULTI_STEP_DECISION_SCHEMA,
            "step_index": observation.get("step_index"),
            "observed_package_id": str(observation.get("package_id") or ""),
            "decision": "replan_next_step",
            "next_action": "replan",
            "replanned": True,
            "reason": "next_step_declared_replan_from_observation",
            "blocked": False,
            "existing_aer_path_required": True,
        }

    return {
        "schema": MULTI_STEP_DECISION_SCHEMA,
        "step_index": observation.get("step_index"),
        "observed_package_id": str(observation.get("package_id") or ""),
        "decision": "continue",
        "next_action": "continue",
        "replanned": False,
        "reason": "step_succeeded",
        "blocked": False,
        "next_step_derived_from_observation": _next_step_uses_observation_derivation(next_raw_step),
    }


def _aggregate_verification(step_results: list[dict[str, Any]]) -> dict[str, Any]:
    targets = []
    for item in step_results:
        bundle = _as_mapping(_as_mapping(item.get("result")).get("result_bundle"))
        targets.append(
            {
                "step_index": item.get("step_index"),
                "package_id": item.get("package_id"),
                "verification_result": _as_mapping(bundle.get("verification_result")),
            }
        )
    return {
        "schema": "zero.engineering_task.multi_step_verification_result.v1",
        "ok": all(bool(_as_mapping(target.get("verification_result")).get("ok")) for target in targets) if targets else False,
        "targets": targets,
    }


def _aggregate_change_set(step_results: list[dict[str, Any]]) -> dict[str, Any]:
    files: list[str] = []
    change_sets: list[dict[str, Any]] = []
    for item in step_results:
        change_set = _as_mapping(_as_mapping(item.get("result")).get("change_set"))
        if change_set:
            change_sets.append(change_set)
        for path in change_set.get("files") or []:
            text = str(path)
            if text not in files:
                files.append(text)
    return {
        "schema": "zero.engineering_task.multi_step_change_set.v1",
        "complete": bool(step_results) and all(bool(_as_mapping(_as_mapping(item.get("result")).get("change_set")).get("complete")) for item in step_results),
        "successful": bool(step_results) and all(bool(_as_mapping(_as_mapping(item.get("result")).get("change_set")).get("successful")) for item in step_results),
        "files": files,
        "step_change_sets": change_sets,
    }


def build_multi_step_result_bundle(
    *,
    requirement_summary: Mapping[str, Any],
    plan: Mapping[str, Any],
    step_results: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    replans: list[dict[str, Any]],
    generated_tasks: list[dict[str, Any]] | None = None,
    iteration_trace: list[dict[str, Any]] | None = None,
    candidate_tasks: list[dict[str, Any]] | None = None,
    candidate_evaluations: list[dict[str, Any]] | None = None,
    selected_tasks: list[dict[str, Any]] | None = None,
    stopped_reason: str = "",
    state_path: str = "",
    resumed: bool = False,
    interrupted: bool = False,
) -> dict[str, Any]:
    verification_result = _aggregate_verification(step_results)
    change_set = _aggregate_change_set(step_results)
    rollback_performed = any(
        bool(_as_mapping(_as_mapping(_as_mapping(item.get("result")).get("result_bundle")).get("rollback_status")).get("rollback_performed"))
        for item in step_results
    )
    planned_step_count = int(plan.get("step_count") or 0)
    ok = (
        bool(step_results)
        and len(step_results) == planned_step_count
        and all(bool(_as_mapping(item.get("result")).get("ok")) for item in step_results)
    )
    last_result = _as_mapping(step_results[-1].get("result")) if step_results else {}
    last_bundle = _as_mapping(last_result.get("result_bundle"))
    return {
        "schema": MULTI_STEP_BUNDLE_SCHEMA,
        "ok": ok,
        "status": "completed" if ok else "blocked_or_failed",
        "package_id": str(requirement_summary.get("package_id") or plan.get("package_id") or ""),
        "requirement_summary": dict(requirement_summary),
        "multi_step_plan": dict(plan),
        "task_breakdown": _as_mapping(plan.get("task_breakdown")),
        "steps": copy.deepcopy(plan.get("steps") if isinstance(plan.get("steps"), list) else []),
        "dependencies": copy.deepcopy(plan.get("dependencies") if isinstance(plan.get("dependencies"), list) else []),
        "acceptance_criteria": copy.deepcopy(plan.get("acceptance_criteria") if isinstance(plan.get("acceptance_criteria"), list) else []),
        "execution_order": copy.deepcopy(plan.get("execution_order") if isinstance(plan.get("execution_order"), list) else []),
        "step_results": copy.deepcopy(step_results),
        "observations": copy.deepcopy(observations),
        "decisions": copy.deepcopy(decisions),
        "replans": copy.deepcopy(replans),
        "generated_tasks": copy.deepcopy(generated_tasks if isinstance(generated_tasks, list) else []),
        "iteration_trace": copy.deepcopy(iteration_trace if isinstance(iteration_trace, list) else []),
        "candidate_tasks": copy.deepcopy(candidate_tasks if isinstance(candidate_tasks, list) else []),
        "candidate_evaluations": copy.deepcopy(candidate_evaluations if isinstance(candidate_evaluations, list) else []),
        "selected_tasks": copy.deepcopy(selected_tasks if isinstance(selected_tasks, list) else []),
        "selected_task": copy.deepcopy(selected_tasks[-1]) if isinstance(selected_tasks, list) and selected_tasks else {},
        "selection_reason": str(_as_mapping(selected_tasks[-1]).get("selection_reason") or "") if isinstance(selected_tasks, list) and selected_tasks else "",
        "resumed": bool(resumed),
        "interrupted": bool(interrupted),
        "state_path": str(state_path or ""),
        "state_saved_after_each_step": bool(step_results),
        "last_result_bundle": copy.deepcopy(last_bundle),
        "verification_result": verification_result,
        "verification_set": {"schema": "zero.engineering_task.multi_step_verification_set.v1", "ok": bool(verification_result.get("ok")), "targets": verification_result.get("targets", [])},
        "rollback_status": {
            "schema": "zero.engineering_task.multi_step_rollback_status.v1",
            "ok": not rollback_performed or all(
                bool(_as_mapping(_as_mapping(_as_mapping(item.get("result")).get("result_bundle")).get("rollback_status")).get("ok", True))
                for item in step_results
            ),
            "rollback_performed": rollback_performed,
        },
        "rollback_performed": rollback_performed,
        "change_set": change_set,
        "work_package_result": _as_mapping(last_result.get("work_package_result")),
        "artifact_paths": _as_mapping(last_bundle.get("artifact_paths")),
        "stopped_reason": stopped_reason,
        "execution_path": {
            "schema": "zero.engineering_task.execution_path.v1",
            "existing_aer_work_package_path": "Planner.normalize_aer_execution_intent -> WorkPackageScheduler.submit -> submit_work_package",
            "existing_controlled_edit_path": "WorkPackageIntake._execute_controlled_multi_write -> _apply_controlled_repo_write -> run_repo_edit",
            "existing_change_set_bundle": bool(change_set.get("step_change_sets")),
            "existing_transaction_rollback_verification": True,
            "no_new_runtime_path": True,
            "direct_write_shortcut": False,
            "full_file_outputs_only": True,
        },
    }


def build_result_bundle(
    *,
    requirement_summary: Mapping[str, Any],
    normalized_payload: Mapping[str, Any],
    schedule_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the complete engineering result bundle to the caller."""

    work_package_result = _as_mapping(schedule_record.get("result"))
    verification_result = _as_mapping(work_package_result.get("verification_result"))
    verification_set = _as_mapping(work_package_result.get("verification_set"))
    rollback_status = _as_mapping(work_package_result.get("rollback_status"))
    change_set = _as_mapping(work_package_result.get("change_set"))
    edit_plan = _as_mapping(work_package_result.get("edit_plan") or work_package_result.get("plan"))
    impact_analysis = _as_mapping(work_package_result.get("impact_analysis"))

    return {
        "schema": FINAL_BUNDLE_SCHEMA,
        "ok": bool(work_package_result.get("ok")),
        "status": str(schedule_record.get("status") or work_package_result.get("status") or ""),
        "package_id": str(work_package_result.get("package_id") or requirement_summary.get("package_id") or ""),
        "requirement_summary": dict(requirement_summary),
        "normalized_payload": dict(normalized_payload),
        "edit_plan": edit_plan,
        "impact_analysis": impact_analysis,
        "change_set": change_set,
        "execution_result": _as_mapping(work_package_result.get("execution_result")),
        "verification_result": verification_result,
        "verification_set": verification_set,
        "rollback_status": rollback_status,
        "rollback_performed": bool(work_package_result.get("rollback_performed")),
        "work_package_result": work_package_result,
        "scheduler_record": dict(schedule_record),
        "artifact_paths": {
            "audit_path": str(work_package_result.get("audit_path") or ""),
            "evidence_path": str(work_package_result.get("evidence_path") or ""),
            "result_path": str(work_package_result.get("result_path") or ""),
            "report_path": str(work_package_result.get("report_path") or ""),
        },
        "execution_path": {
            "schema": "zero.engineering_task.execution_path.v1",
            "existing_aer_work_package_path": "Planner.normalize_aer_execution_intent -> WorkPackageScheduler.submit -> submit_work_package",
            "existing_controlled_edit_path": "WorkPackageIntake._execute_controlled_multi_write -> _apply_controlled_repo_write -> run_repo_edit",
            "existing_change_set_bundle": bool(change_set),
            "existing_transaction_rollback_verification": True,
            "no_new_runtime_path": True,
            "direct_write_shortcut": False,
        },
    }


def _run_single_engineering_task(
    payload: Mapping[str, Any],
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    requirement_summary = build_requirement_summary(payload)
    normalized_payload = normalize_engineering_task_payload(payload)
    work_package_payload = _as_mapping(normalized_payload.get("work_package"))
    scheduler = WorkPackageScheduler(repo_root=repo_root)
    schedule_record = scheduler.submit(work_package_payload, execute=True)
    result_bundle = build_result_bundle(
        requirement_summary=requirement_summary,
        normalized_payload=normalized_payload,
        schedule_record=schedule_record,
    )

    return {
        "schema": SCHEMA,
        "ok": bool(result_bundle.get("ok")),
        "mode": "engineering_task_runner",
        "package_id": result_bundle["package_id"],
        "requirement_summary": requirement_summary,
        "normalized_payload": normalized_payload,
        "result_bundle": result_bundle,
        "work_package_result": result_bundle["work_package_result"],
        "verification_result": result_bundle["verification_result"],
        "change_set": result_bundle["change_set"],
        "final_message": str(result_bundle["work_package_result"].get("final_message") or ""),
    }


def run_multi_step_engineering_task(
    payload: Mapping[str, Any],
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    """Run a multi-step engineering task as existing AER work-package executions."""

    requirement_summary = build_requirement_summary(payload)
    plan = build_multi_step_plan(payload)
    raw_steps = _raw_step_payloads(payload)
    parent = _task_payload(payload)
    package_id = str(plan.get("package_id") or requirement_summary.get("package_id") or "engineering_task")
    state_path = _multi_step_state_path(repo_root, package_id)
    resume_requested = bool(parent.get("resume") or payload.get("resume"))
    interrupt_after_step = int(parent.get("interrupt_after_step") or payload.get("interrupt_after_step") or 0)
    loaded_state = _read_json(state_path) if resume_requested else {}

    if loaded_state.get("schema") == MULTI_STEP_STATE_SCHEMA:
        step_results = [dict(item) for item in loaded_state.get("step_results", []) if isinstance(item, Mapping)]
        observations = [dict(item) for item in loaded_state.get("observations", []) if isinstance(item, Mapping)]
        decisions = [dict(item) for item in loaded_state.get("decisions", []) if isinstance(item, Mapping)]
        replans = [dict(item) for item in loaded_state.get("replans", []) if isinstance(item, Mapping)]
        generated_tasks = [dict(item) for item in loaded_state.get("generated_tasks", []) if isinstance(item, Mapping)]
        iteration_trace = [dict(item) for item in loaded_state.get("iteration_trace", []) if isinstance(item, Mapping)]
        candidate_tasks = [dict(item) for item in loaded_state.get("candidate_tasks", []) if isinstance(item, Mapping)]
        candidate_evaluations = [dict(item) for item in loaded_state.get("candidate_evaluations", []) if isinstance(item, Mapping)]
        selected_tasks = [dict(item) for item in loaded_state.get("selected_tasks", []) if isinstance(item, Mapping)]
    else:
        step_results = []
        observations = []
        decisions = []
        replans = []
        generated_tasks = []
        iteration_trace = []
        candidate_tasks = []
        candidate_evaluations = []
        selected_tasks = []

    previous_observation: dict[str, Any] | None = observations[-1] if observations else None
    stopped_reason = ""
    interrupted = False

    if not iteration_trace:
        _append_iteration_trace(
            iteration_trace,
            event="goal",
            package_id=package_id,
            detail={"goal": plan.get("goal"), "requirement_summary": requirement_summary},
        )
        _append_iteration_trace(
            iteration_trace,
            event="task_decomposition",
            package_id=package_id,
            detail={"step_count": plan.get("step_count"), "task_breakdown": plan.get("task_breakdown")},
        )

    def save_state(status: str, next_step_index: int) -> None:
        _write_json(
            state_path,
            {
                "schema": MULTI_STEP_STATE_SCHEMA,
                "package_id": package_id,
                "status": status,
                "resumed": resume_requested,
                "next_step_index": next_step_index,
                "completed_step_count": len(step_results),
                "step_count": len(raw_steps),
                "plan": copy.deepcopy(plan),
                "step_results": copy.deepcopy(step_results),
                "observations": copy.deepcopy(observations),
                "decisions": copy.deepcopy(decisions),
                "replans": copy.deepcopy(replans),
                "generated_tasks": copy.deepcopy(generated_tasks),
                "iteration_trace": copy.deepcopy(iteration_trace),
                "candidate_tasks": copy.deepcopy(candidate_tasks),
                "candidate_evaluations": copy.deepcopy(candidate_evaluations),
                "selected_tasks": copy.deepcopy(selected_tasks),
                "updated_at": time.time(),
            },
        )

    save_state("running", len(step_results) + 1)

    for step_index, raw_step in enumerate(raw_steps, start=1):
        if step_index <= len(step_results):
            continue

        step_payload = _build_step_payload(
            parent_payload=payload,
            raw_step=raw_step,
            step_index=step_index,
            previous_observation=previous_observation,
        )
        raw_candidates = _raw_candidate_task_payloads(raw_step)
        if raw_candidates:
            step_candidates: list[dict[str, Any]] = []
            for candidate_index, raw_candidate in enumerate(raw_candidates, start=1):
                candidate_payload = _build_step_payload(
                    parent_payload=payload,
                    raw_step=raw_candidate,
                    step_index=step_index,
                    previous_observation=previous_observation,
                )
                step_candidates.append(
                    _candidate_task_record(
                        step_index=step_index,
                        candidate_index=candidate_index,
                        step_payload=candidate_payload,
                        previous_observation=previous_observation,
                    )
                )
            evaluations = _evaluate_candidate_tasks(step_candidates)
            selected_task = _select_candidate_task(
                step_index=step_index,
                candidates=step_candidates,
                evaluations=evaluations,
            )
            candidate_tasks.extend(step_candidates)
            candidate_evaluations.extend(evaluations)
            selected_tasks.append(selected_task)
            selected_payload = _as_mapping(_as_mapping(selected_task.get("selected_task")).get("task_payload"))
            if selected_payload:
                step_payload = selected_payload
            _append_iteration_trace(
                iteration_trace,
                event="candidate_tasks",
                step_index=step_index,
                package_id=str(step_payload.get("package_id") or step_payload.get("task_id") or ""),
                detail={"candidate_tasks": copy.deepcopy(step_candidates)},
            )
            _append_iteration_trace(
                iteration_trace,
                event="evaluation",
                step_index=step_index,
                package_id=str(step_payload.get("package_id") or step_payload.get("task_id") or ""),
                detail={"candidate_evaluations": copy.deepcopy(evaluations)},
            )
            _append_iteration_trace(
                iteration_trace,
                event="selected_task",
                step_index=step_index,
                package_id=str(step_payload.get("package_id") or step_payload.get("task_id") or ""),
                detail={"selected_task": copy.deepcopy(selected_task)},
            )
        generated_reason = "initial_engineering_task" if previous_observation is None else "generated_from_previous_observation"
        generated_task = _generated_task_record(
            step_index=step_index,
            step_payload=step_payload,
            previous_observation=previous_observation,
            generated_reason=generated_reason,
        )
        generated_tasks.append(generated_task)
        _append_iteration_trace(
            iteration_trace,
            event=f"step_{step_index}",
            step_index=step_index,
            package_id=str(step_payload.get("package_id") or step_payload.get("task_id") or ""),
            detail={"task_payload": copy.deepcopy(step_payload), "generated_reason": generated_reason},
        )
        if previous_observation is not None:
            _append_iteration_trace(
                iteration_trace,
                event="generate_next_engineering_task",
                step_index=step_index,
                package_id=str(step_payload.get("package_id") or step_payload.get("task_id") or ""),
                detail={"generated_task": copy.deepcopy(generated_task)},
            )
        derived_from_observation = bool(_as_mapping(step_payload.get("metadata")).get("derived_from_observation"))
        if derived_from_observation:
            replans.append(
                {
                    "schema": "zero.engineering_task.continuation_plan.v1",
                    "step_index": step_index,
                    "decision": "continue",
                    "replanned": False,
                    "derived_from_observation": True,
                    "source_observation_step": previous_observation.get("step_index") if isinstance(previous_observation, Mapping) else None,
                    "next_step_package_id": step_payload.get("package_id") or step_payload.get("task_id"),
                }
            )

        result = _run_single_engineering_task(step_payload, repo_root=repo_root)
        observation = _observe_step_result(step_index=step_index, step_payload=step_payload, result=result)
        step_results.append(
            {
                "schema": "zero.engineering_task.multi_step_step_result.v1",
                "step_index": step_index,
                "package_id": str(result.get("package_id") or step_payload.get("package_id") or step_payload.get("task_id") or ""),
                "derived_from_observation": derived_from_observation,
                "step_payload": copy.deepcopy(step_payload),
                "result": copy.deepcopy(result),
                "observation": copy.deepcopy(observation),
            }
        )
        observations.append(observation)
        _append_iteration_trace(
            iteration_trace,
            event="observation",
            step_index=step_index,
            package_id=str(observation.get("package_id") or ""),
            detail={"observation": copy.deepcopy(observation)},
        )
        previous_observation = observation
        next_raw_step = raw_steps[step_index] if step_index < len(raw_steps) else None
        decision = _decide_after_observation(observation=observation, next_raw_step=next_raw_step)
        decisions.append(decision)
        _append_iteration_trace(
            iteration_trace,
            event="decision",
            step_index=step_index,
            package_id=str(observation.get("package_id") or ""),
            detail={"decision": copy.deepcopy(decision)},
        )

        if not bool(result.get("ok")):
            stopped_reason = observation.get("reason") or "step_failed"
            replans.append(
                {
                    "schema": "zero.engineering_task.replan_decision.v1",
                    "step_index": step_index,
                    "decision": "stop_safely",
                    "replanned": False,
                    "reason": stopped_reason,
                    "blocked_step_stops_safely": bool(observation.get("blocked")),
                    "existing_rollback_preserved": True,
                }
            )
            _append_iteration_trace(
                iteration_trace,
                event="complete",
                step_index=step_index,
                package_id=package_id,
                detail={"status": "blocked_or_failed", "stopped_reason": stopped_reason},
            )
            save_state("blocked_or_failed", step_index + 1)
            break

        if decision.get("decision") == "replan_next_step":
            replans.append(
                {
                    "schema": "zero.engineering_task.replan_decision.v1",
                    "step_index": step_index,
                    "decision": "replan_next_step",
                    "next_step_index": step_index + 1,
                    "replanned": True,
                    "reason": str(decision.get("reason") or "next_step_declared_replan_from_observation"),
                    "source_observation_step": observation.get("step_index"),
                    "existing_aer_path_preserved": True,
                }
            )

        save_state("running", step_index + 1)

        if interrupt_after_step == step_index and not resume_requested:
            interrupted = True
            stopped_reason = "simulated_interruption"
            save_state("interrupted", step_index + 1)
            break

    if not stopped_reason and len(step_results) >= len(raw_steps):
        _append_iteration_trace(
            iteration_trace,
            event="complete",
            package_id=package_id,
            detail={"status": "completed", "step_count": len(step_results)},
        )
        save_state("completed", len(raw_steps) + 1)

    result_bundle = build_multi_step_result_bundle(
        requirement_summary=requirement_summary,
        plan=plan,
        step_results=step_results,
        observations=observations,
        decisions=decisions,
        replans=replans,
        generated_tasks=generated_tasks,
        iteration_trace=iteration_trace,
        candidate_tasks=candidate_tasks,
        candidate_evaluations=candidate_evaluations,
        selected_tasks=selected_tasks,
        stopped_reason=stopped_reason,
        state_path=_display_path(state_path, repo_root),
        resumed=resume_requested,
        interrupted=interrupted,
    )

    return {
        "schema": SCHEMA,
        "ok": bool(result_bundle.get("ok")) and not interrupted,
        "mode": "engineering_task_runner",
        "package_id": result_bundle["package_id"],
        "requirement_summary": requirement_summary,
        "normalized_payload": {
            "schema": "zero.engineering_task.multi_step.normalized_payload.v1",
            "intent": "multi_step_engineering_task",
            "normalizer": "EngineeringTaskRunner.build_multi_step_plan",
            "multi_step_plan": plan,
        },
        "plan": plan,
        "task_breakdown": _as_mapping(plan.get("task_breakdown")),
        "steps": copy.deepcopy(plan.get("steps") if isinstance(plan.get("steps"), list) else []),
        "dependencies": copy.deepcopy(plan.get("dependencies") if isinstance(plan.get("dependencies"), list) else []),
        "acceptance_criteria": copy.deepcopy(plan.get("acceptance_criteria") if isinstance(plan.get("acceptance_criteria"), list) else []),
        "execution_order": copy.deepcopy(plan.get("execution_order") if isinstance(plan.get("execution_order"), list) else []),
        "result_bundle": result_bundle,
        "work_package_result": result_bundle["work_package_result"],
        "verification_result": result_bundle["verification_result"],
        "change_set": result_bundle["change_set"],
        "step_results": copy.deepcopy(step_results),
        "observations": copy.deepcopy(observations),
        "decisions": copy.deepcopy(decisions),
        "replans": copy.deepcopy(replans),
        "generated_tasks": copy.deepcopy(generated_tasks),
        "iteration_trace": copy.deepcopy(iteration_trace),
        "candidate_tasks": copy.deepcopy(candidate_tasks),
        "candidate_evaluations": copy.deepcopy(candidate_evaluations),
        "selected_tasks": copy.deepcopy(selected_tasks),
        "selected_task": copy.deepcopy(selected_tasks[-1]) if selected_tasks else {},
        "selection_reason": str(_as_mapping(selected_tasks[-1]).get("selection_reason") or "") if selected_tasks else "",
        "resumed": resume_requested,
        "interrupted": interrupted,
        "state_path": _display_path(state_path, repo_root),
        "final_message": "multi_step_engineering_task_completed" if bool(result_bundle.get("ok")) and not interrupted else stopped_reason or "multi_step_engineering_task_stopped",
    }


def run_engineering_task(
    payload: Mapping[str, Any],
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    """Run a real engineering task through ZERO's work-package path."""

    if not isinstance(payload, Mapping):
        raise ValueError("engineering_task_payload_must_be_mapping")

    if not _has_executable_payload(payload):
        return run_multi_step_engineering_task(decompose_engineering_goal(payload), repo_root=repo_root)

    if _is_multi_step_payload(payload):
        return run_multi_step_engineering_task(payload, repo_root=repo_root)

    return _run_single_engineering_task(payload, repo_root=repo_root)


__all__ = [
    "FINAL_BUNDLE_SCHEMA",
    "MULTI_STEP_BUNDLE_SCHEMA",
    "MULTI_STEP_DECISION_SCHEMA",
    "MULTI_STEP_OBSERVATION_SCHEMA",
    "MULTI_STEP_PLAN_SCHEMA",
    "REQUIREMENT_SUMMARY_SCHEMA",
    "SCHEMA",
    "build_requirement_summary",
    "build_multi_step_plan",
    "build_multi_step_result_bundle",
    "build_result_bundle",
    "decompose_engineering_goal",
    "normalize_engineering_task_payload",
    "run_engineering_task",
    "run_multi_step_engineering_task",
]
