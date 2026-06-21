from __future__ import annotations

"""Goal-to-work-package bridge for explicit workspace file goals.

This module owns the narrow mainline from an engineering goal into the sealed
RuntimeWorkPackageOperator contract. It does not introduce a second work package
format; Planner.normalize_aer_execution_intent remains the formatter.
"""

import copy
import re
import time
from pathlib import Path
from typing import Any, Mapping

from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.goals.goal_lineage_contract import attach_goal_lineage, extract_goal_lineage
from core.planning.planner import Planner
from core.tasks.engineering_adaptive_planner import EngineeringAdaptivePlanner
from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.task_runner import TaskRunner
from core.runtime.work_package_queue import RuntimePackageQueue


GOAL_WORK_PACKAGE_MAINLINE_SCHEMA = "zero.engineering_goal.work_package_mainline.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _goal_id(goal: Mapping[str, Any]) -> str:
    return _clean_text(goal.get("goal_id") or goal.get("task_id") or goal.get("package_id"))


def _extract_workspace_target(text: str) -> str:
    match = re.search(
        r"\b(workspace[/\\][A-Za-z0-9_./\\ -]+?\.(?:txt|md|json|yaml|yml|csv|log))\b",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).strip().replace("\\", "/").lstrip("./")


def _extract_any_file_target(text: str) -> str:
    match = re.search(
        r"\b((?:workspace|core|services|tests|ui|runtime|app)[/\\][A-Za-z0-9_./\\ -]+?\.(?:txt|md|json|yaml|yml|csv|log|py))\b",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).strip().replace("\\", "/").lstrip("./")


def _looks_like_workspace_create_goal(text: str, target_path: str) -> bool:
    if not target_path:
        return False
    lowered = str(text or "").lower()
    return any(token in lowered for token in ("create", "write", "generate", "make", "建立", "新增", "產生", "寫入"))


def _is_recoverable_work_package_failure(reason: Any) -> bool:
    text = str(reason or "").strip().lower()
    return any(
        marker in text
        for marker in (
            "verification_failed",
            "validation_failed",
            "missing_artifact",
            "missing_output",
            "artifact_not_found",
            "output_not_found",
        )
    )


def _next_workspace_target(target_path: str) -> str:
    normalized = _clean_text(target_path).replace("\\", "/").lstrip("./")
    if not normalized.startswith("workspace/") or "." not in normalized:
        return ""
    path = Path(normalized)
    if path.stem.endswith("_next"):
        return ""
    return str(path.with_name(f"{path.stem}_next{path.suffix}")).replace("\\", "/")


class _SealedWorkspacePlanner:
    def __init__(self, *, target_path: str, content: str, verify_contains: str) -> None:
        self.target_path = target_path
        self.content = content
        self.verify_contains = verify_contains

    def plan(self, **_kwargs: Any) -> dict[str, Any]:
        steps: list[dict[str, Any]] = [
            {
                "id": "workspace-write",
                "type": "write_file",
                "path": self.target_path,
                "target_path": self.target_path,
                "content": self.content,
            }
        ]
        if self.verify_contains:
            steps.append(
                {
                    "id": "workspace-verify",
                    "type": "verify",
                    "path": self.target_path,
                    "target_path": self.target_path,
                    "contains": self.verify_contains,
                }
            )
        return {
            "ok": True,
            "steps": steps,
            "meta": {"semantic_type": "governed_workspace_edit"},
        }


class _SealedWorkspaceTaskRunner(TaskRunner):
    """Bounded TaskRunner adapter for deterministic workspace-file steps."""

    def run_task(self, *, task: Mapping[str, Any], current_tick: int = 0, **_kwargs: Any) -> dict[str, Any]:
        owned = copy.deepcopy(dict(task))
        steps = owned.get("steps") if isinstance(owned.get("steps"), list) else []
        if current_tick < 0 or current_tick >= len(steps):
            return {"ok": False, "status": "failed", "error": "workspace_step_cursor_out_of_range"}
        step = steps[current_tick] if isinstance(steps[current_tick], Mapping) else {}
        result = self.execute_owned_step(
            copy.deepcopy(dict(step)),
            task=owned,
            step_index=current_tick,
            step_count=len(steps),
        )
        ok = bool(result.get("ok"))
        next_index = current_tick + 1 if ok else current_tick
        owned["current_step_index"] = next_index
        owned["status"] = "finished" if ok and next_index >= len(steps) else "running" if ok else "failed"
        return {
            "ok": ok,
            "status": owned["status"],
            "current_step_index": next_index,
            "error": None if ok else result.get("error"),
            "task": owned,
            "runtime_state": {
                "status": owned["status"],
                "current_step_index": next_index,
                "results": [{"step_index": current_tick, "result": copy.deepcopy(result)}],
            },
            "evidence_refs": [
                str(owned.get("runtime_authority_decision_id") or "")
            ],
        }


def _continuation_plan_for_completed_goal(
    *,
    goal_id: str,
    source_target_path: str,
    runtime_state: str,
    evidence: EvidenceRecord,
) -> dict[str, Any]:
    next_target = _next_workspace_target(source_target_path)
    if not next_target:
        return {}
    next_goal = f"建立 {next_target}"
    payload = {
        "goal": next_goal,
        "target_path": next_target,
        "operation": "create_file",
        "content": f"Generated for continuation of {goal_id}: {next_goal}\n",
        "task_type": "engineering_task",
        "engineering_goal_lifecycle": True,
    }
    evidence_chain = [evidence.to_dict()]
    return {
        "schema": "zero.engineering_adaptive_planner.continuation_plan.v2",
        "goal_id": goal_id,
        "reason": "post_completion_follow_up_goal_available",
        "remaining_tasks": [next_target],
        "next_runtime_request": {
            "goal_id": goal_id,
            "payload": payload,
            "source_runtime_state": runtime_state,
        },
        "work_item_template": {
            "objective": next_goal,
            "source_goal_id": goal_id,
            "task_type": "engineering_task",
            "remaining_tasks": [next_target],
            "acceptance": {
                "goal_state": "completed",
                "created_file": next_target,
            },
            "provenance": {
                "source_runtime_state": runtime_state,
                "evidence_ids": [evidence.evidence_id],
            },
        },
        "evidence_chain": evidence_chain,
        "execution_path": {
            "plan_only": True,
            "executes_tasks": False,
            "new_goal_format": False,
        },
        "created_at": time.time(),
    }


def run_goal_work_package_mainline(
    goal: Mapping[str, Any],
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    goal_id = _goal_id(goal)
    goal_lineage = extract_goal_lineage(goal)
    summary = _clean_text(goal.get("summary") or goal.get("goal"), goal_id)
    payload = copy.deepcopy(dict(goal.get("payload"))) if isinstance(goal.get("payload"), Mapping) else {}
    explicit_target_path = _clean_text(payload.get("target_path") or payload.get("path")) or _extract_any_file_target(summary)
    target_path = explicit_target_path if explicit_target_path.startswith("workspace/") else _extract_workspace_target(summary)
    if explicit_target_path and not explicit_target_path.startswith("workspace/") and _looks_like_workspace_create_goal(summary, explicit_target_path):
        runtime_result = {
            "schema": GOAL_WORK_PACKAGE_MAINLINE_SCHEMA,
            "ok": False,
            "state": "blocked",
            "decision_state": "blocked",
            "terminal": True,
            "stop_reason": "policy_blocked_non_workspace_target",
            "goal_id": goal_id,
            "work_package_result": {},
            "iterations": [
                {
                    "iteration": 1,
                    "state": "blocked",
                    "goal_id": goal_id,
                    "continuation_result": {
                        "ok": False,
                        "terminal": True,
                        "goal_lifecycle": {
                            "goal_id": goal_id,
                            "goal_state": "blocked",
                            "completed_tasks": [],
                            "remaining_tasks": [],
                            "failed_tasks": [],
                            "blocked_tasks": [explicit_target_path],
                        },
                    },
                    "evaluator_decision": {"decision": "block"},
                }
            ],
            "execution_path": {
                "goal": "Goal",
                "planner": "Planner.normalize_aer_execution_intent",
                "work_package": "blocked_before_work_package_submission",
                "scheduler": "not_called",
                "evidence": "not_created",
                "completion_authority": "not_called",
                "direct_execution": False,
                "new_work_package_format": False,
            },
        }
        adaptive_decision = EngineeringAdaptivePlanner().decide_next_action(
            goal=goal,
            runtime_result=runtime_result,
            runtime_root_cause={
                "reason": "policy_blocked_non_workspace_target",
                "stop_reason": "policy_blocked_non_workspace_target",
                "target_path": explicit_target_path,
            },
            issue_summary={"blocking_issues": ["policy_blocked_non_workspace_target"]},
        )
        return {
            "runtime_result": runtime_result,
            "adaptive_decision": adaptive_decision,
        }
    if not _looks_like_workspace_create_goal(summary, target_path):
        return {}

    package_id = _clean_text(payload.get("package_id") or goal_id, goal_id)
    planner_payload = {
        "task_type": "engineering_task",
        "package_id": package_id,
        "task_id": package_id,
        "goal": summary,
        "title": summary,
        "mode": "execute",
        "approval": True,
        "operation": _clean_text(payload.get("operation"), "create_file"),
        "target_path": target_path,
        "content": str(payload.get("content") or f"Generated for goal: {summary}\n"),
        "verify_contains": str(payload.get("verify_contains") or payload.get("expect_contains") or ""),
        "report_path": str(payload.get("report_path") or f"workspace/{package_id}_report.md"),
    }
    normalized = Planner().normalize_aer_execution_intent(planner_payload, user_input=summary)
    work_package = normalized.get("work_package") if isinstance(normalized, Mapping) else None
    if not isinstance(work_package, Mapping):
        return {}

    content = str(payload.get("content") or f"Generated for goal: {summary}\n")
    verify_contains = str(payload.get("verify_contains") or payload.get("expect_contains") or "")
    planner_bridge = WorkPackagePlannerBridge(
        planner=_SealedWorkspacePlanner(
            target_path=target_path,
            content=content,
            verify_contains=verify_contains,
        )
    )
    queue = RuntimePackageQueue(repo_root=repo_root)
    dispatcher = RuntimeDispatcher(
        queue=queue,
        task_runner=_SealedWorkspaceTaskRunner.for_workspace(Path(repo_root) / "workspace"),
        workspace_root=Path(repo_root) / "workspace",
        planner_bridge=planner_bridge,
    )
    operator = RuntimeWorkPackageOperator(
        repo_root=repo_root,
        queue=queue,
        planner_bridge=planner_bridge,
        dispatcher=dispatcher,
    )
    operator.submit_package(
        attach_goal_lineage(
            {
                "package_id": package_id,
                "goal_id": goal_id,
                "title": summary,
                "goal": summary,
                "description": summary,
                "target_files": [target_path],
                "requirements": ["sealed_runtime_dispatch", "validated_completion_evidence"],
                "hard_boundary": ["RuntimeDispatcher required", "workspace target only"],
                "non_mainline_issue_reporting": ["report all governance failures"],
                "validation_commands": [],
                "completion_report_format": ["runtime progress"],
            },
            goal_lineage,
        )
    )
    schedule_record = operator.run_package(package_id)
    completed = schedule_record.get("status") == "completed"
    runtime_state = schedule_record.get("runtime_state") if isinstance(schedule_record.get("runtime_state"), Mapping) else {}
    runtime_task = runtime_state.get("task") if isinstance(runtime_state.get("task"), Mapping) else {}
    runtime_graph = copy.deepcopy(
        schedule_record.get("runtime_identity_graph")
        or runtime_state.get("runtime_identity_graph")
        or runtime_task.get("runtime_identity_graph")
        or {}
    )
    schedule_record["completion_authority"] = {
        "package_id": package_id,
        "goal_id": goal_id,
        "session_id": goal_lineage["session_id"],
        "runtime_session_id": goal_lineage["runtime_session_id"],
        "goal_lineage_id": goal_lineage["goal_lineage_id"],
        "evidence_id": runtime_graph.get("evidence_id"),
        "authority_source": "RuntimeDispatcher",
        "sealed": completed and bool(runtime_graph.get("evidence_id")),
    }
    work_package_result = {
        "ok": completed,
        "changed_files": [target_path] if completed else [],
        "reason": "controlled_workspace_execution_completed" if completed else schedule_record.get("root_cause"),
        "evidence": {
            "guard": "workspace_only",
            "evidence_id": runtime_graph.get("evidence_id"),
            "goal_lineage_id": goal_lineage["goal_lineage_id"],
        },
        "runtime_identity_graph": runtime_graph,
        "execution_evidence": copy.deepcopy(schedule_record.get("execution_evidence") or []),
    }
    evidence = EvidenceValidator().validate(
        EvidenceRecord(
            evidence_id=f"{goal_id}:work_package:{schedule_record.get('package_id')}",
            goal_id=goal_id,
            subgoal_id=None,
            source="core.tasks.engineering_goal_work_package_mainline",
            summary={
                "scheduler_status": schedule_record.get("status"),
                "package_id": schedule_record.get("package_id"),
                "changed_files": list(work_package_result.get("changed_files") or []),
                "reason": work_package_result.get("reason"),
                "completion_authority": schedule_record.get("completion_authority"),
            },
            timestamp=str(time.time()),
            metadata={
                "schema": GOAL_WORK_PACKAGE_MAINLINE_SCHEMA,
                **goal_lineage,
                "goal_lineage": copy.deepcopy(goal_lineage),
                "normalized_payload": copy.deepcopy(dict(normalized)),
                "scheduler_record": copy.deepcopy(dict(schedule_record)),
            },
        )
    )
    completion = GoalCompletionAuthority().complete_goal(
        goal_id=goal_id,
        from_state="active",
        evidence_refs=[evidence],
        all_subgoals_completed=completed,
        reason="work_package_scheduler_completed_goal" if completed else "work_package_scheduler_failed",
        goal_lineage=goal_lineage or None,
    )
    failure_reason = _clean_text(schedule_record.get("error") or work_package_result.get("reason"), "work_package_failed")
    if "verify" in failure_reason.lower() or "validation" in failure_reason.lower():
        failure_reason = "verification_failed"
    recoverable_failure = (not completed) and _is_recoverable_work_package_failure(failure_reason)
    runtime_state = "complete" if completed else "replan" if recoverable_failure else "blocked"
    continuation_plan = (
        _continuation_plan_for_completed_goal(
            goal_id=goal_id,
            source_target_path=target_path,
            runtime_state=runtime_state,
            evidence=evidence,
        )
        if completed
        else {}
    )
    runtime_result = {
        "schema": GOAL_WORK_PACKAGE_MAINLINE_SCHEMA,
        "ok": completed,
        "state": runtime_state,
        "decision_state": runtime_state,
        "terminal": True,
        "stop_reason": "complete" if completed else failure_reason,
        "goal_id": goal_id,
        "next_runtime_request": copy.deepcopy(_mapping(continuation_plan.get("next_runtime_request"))),
        "post_completion_continuation_plan": copy.deepcopy(continuation_plan),
        "planner_result": copy.deepcopy(dict(normalized)),
        "work_package": copy.deepcopy(dict(work_package)),
        "scheduler_record": copy.deepcopy(dict(schedule_record)),
        "work_package_result": copy.deepcopy(dict(work_package_result)),
        "evidence_refs": [evidence.to_dict()],
        "iterations": [
            {
                "iteration": 1,
                "state": runtime_state,
                "goal_id": goal_id,
                "planning_result": copy.deepcopy(dict(normalized)),
                "scheduler_result": copy.deepcopy(dict(schedule_record)),
                "continuation_result": {
                    "ok": completed,
                    "terminal": True,
                    "goal_lifecycle": {
                        "goal_id": goal_id,
                        "goal_state": "completed" if completed else "failed" if recoverable_failure else "blocked",
                        "completed_tasks": [str(schedule_record.get("package_id"))] if completed else [],
                        "remaining_tasks": [] if completed else [target_path],
                        "failed_tasks": [f"{failure_reason}:{target_path}"] if recoverable_failure else [],
                        "blocked_tasks": [] if completed or recoverable_failure else [str(schedule_record.get("package_id"))],
                    },
                    "latest_result": {
                        "result_bundle": {
                            "observations": [
                                {
                                    "package_id": schedule_record.get("package_id"),
                                    "ok": completed,
                                    "status": schedule_record.get("status"),
                                    "changed_files": list(work_package_result.get("changed_files") or []),
                                    "reason": work_package_result.get("reason") or schedule_record.get("error"),
                                }
                            ]
                        }
                    },
                },
                "evaluator_decision": {"decision": "complete" if completed else "replan" if recoverable_failure else "block"},
            }
        ],
        "execution_path": {
            "goal": "Goal",
            "planner": "Planner.normalize_aer_execution_intent",
            "work_package": "RuntimeWorkPackageOperator contract",
            "scheduler": "RuntimeDispatcher.dispatch",
            "evidence": "EvidenceValidator",
            "completion_authority": "GoalCompletionAuthority",
            "direct_execution": False,
            "new_work_package_format": False,
        },
    }
    runtime_root_cause = {} if completed else {
        "reason": failure_reason,
        "stop_reason": failure_reason,
        "failed_tasks": [package_id],
        "failed_step": {"task_id": package_id, "target_path": target_path, "reason": failure_reason},
        "missing_artifacts": [target_path] if recoverable_failure else [],
        "target_path": target_path,
    }
    adaptive_decision = EngineeringAdaptivePlanner().decide_next_action(
        goal=goal,
        runtime_result=runtime_result,
        runtime_root_cause=runtime_root_cause,
        issue_summary={
            "blocking_issues": [] if completed or recoverable_failure else [runtime_result["stop_reason"]],
        },
    )
    adaptive_decision["goal_completion_authority_result"] = completion
    adaptive_decision["evidence_chain"] = [evidence.to_dict()]
    if completed and continuation_plan:
        adaptive_decision["continuation_plan"] = continuation_plan
        adaptive_decision["mainline_decision"] = "create_continuation"
        adaptive_decision["create_continuation_requested"] = True
        adaptive_decision["next_action"] = "create_continuation_work_item"
    return {
        "runtime_result": runtime_result,
        "adaptive_decision": adaptive_decision,
    }


__all__ = [
    "GOAL_WORK_PACKAGE_MAINLINE_SCHEMA",
    "run_goal_work_package_mainline",
]
