from __future__ import annotations

"""Goal-to-work-package bridge for explicit workspace file goals.

This module owns the narrow mainline from an engineering goal into the existing
WorkPackageScheduler contract. It does not introduce a second work package
format; Planner.normalize_aer_execution_intent remains the formatter.
"""

import copy
import re
import time
from pathlib import Path
from typing import Any, Mapping

from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.planning.planner import Planner
from core.tasks.engineering_adaptive_planner import normalize_adaptive_decision
from core.tasks.work_package_scheduler import WorkPackageScheduler


GOAL_WORK_PACKAGE_MAINLINE_SCHEMA = "zero.engineering_goal.work_package_mainline.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


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


def _looks_like_workspace_create_goal(text: str, target_path: str) -> bool:
    if not target_path:
        return False
    lowered = str(text or "").lower()
    return any(token in lowered for token in ("create", "write", "generate", "make", "建立", "新增", "產生", "寫入"))


def run_goal_work_package_mainline(
    goal: Mapping[str, Any],
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    goal_id = _goal_id(goal)
    summary = _clean_text(goal.get("summary") or goal.get("goal"), goal_id)
    payload = copy.deepcopy(dict(goal.get("payload"))) if isinstance(goal.get("payload"), Mapping) else {}
    target_path = _clean_text(payload.get("target_path") or payload.get("path")) or _extract_workspace_target(summary)
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

    schedule_record = WorkPackageScheduler(repo_root=repo_root).submit(work_package, execute=True)
    work_package_result = schedule_record.get("result") if isinstance(schedule_record.get("result"), Mapping) else {}
    completed = schedule_record.get("status") == "completed" and bool(work_package_result.get("ok"))
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
                "normalized_payload": copy.deepcopy(dict(normalized)),
                "scheduler_record": copy.deepcopy(dict(schedule_record)),
            },
        )
    )
    completion = GoalCompletionAuthority().complete_goal(
        goal_id=goal_id,
        from_state="active",
        evidence_refs=[evidence],
        all_subgoals_completed=True,
        reason="work_package_scheduler_completed_goal",
    )
    runtime_result = {
        "schema": GOAL_WORK_PACKAGE_MAINLINE_SCHEMA,
        "ok": completed,
        "state": "complete" if completed else "blocked",
        "decision_state": "complete" if completed else "blocked",
        "terminal": True,
        "stop_reason": "complete" if completed else _clean_text(schedule_record.get("error"), "work_package_failed"),
        "goal_id": goal_id,
        "planner_result": copy.deepcopy(dict(normalized)),
        "work_package": copy.deepcopy(dict(work_package)),
        "scheduler_record": copy.deepcopy(dict(schedule_record)),
        "work_package_result": copy.deepcopy(dict(work_package_result)),
        "evidence_refs": [evidence.to_dict()],
        "iterations": [
            {
                "iteration": 1,
                "state": "complete" if completed else "blocked",
                "goal_id": goal_id,
                "planning_result": copy.deepcopy(dict(normalized)),
                "scheduler_result": copy.deepcopy(dict(schedule_record)),
                "continuation_result": {
                    "ok": completed,
                    "terminal": True,
                    "goal_lifecycle": {
                        "goal_id": goal_id,
                        "goal_state": "completed" if completed else "blocked",
                        "completed_tasks": [str(schedule_record.get("package_id"))] if completed else [],
                        "blocked_tasks": [] if completed else [str(schedule_record.get("package_id"))],
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
                "evaluator_decision": {"decision": "complete" if completed else "block"},
            }
        ],
        "execution_path": {
            "goal": "Goal",
            "planner": "Planner.normalize_aer_execution_intent",
            "work_package": "WorkPackageScheduler contract",
            "scheduler": "WorkPackageScheduler.submit",
            "evidence": "EvidenceValidator",
            "completion_authority": "GoalCompletionAuthority",
            "direct_execution": False,
            "new_work_package_format": False,
        },
    }
    adaptive_decision = normalize_adaptive_decision(
        {
            "decision": "complete" if completed else "blocked",
            "reason": "work_package_scheduler_completed_goal" if completed else runtime_result["stop_reason"],
            "confidence": 1.0 if completed else 0.0,
            "next_action": "stop" if completed else "stop_with_root_cause",
            "continuation_plan": {},
            "replan_request": {},
            "blocking_issues": [] if completed else [runtime_result["stop_reason"]],
            "root_cause": {} if completed else {"reason": runtime_result["stop_reason"]},
            "goal_completion_authority_result": completion,
            "evidence_chain": [evidence.to_dict()],
        }
    )
    return {
        "runtime_result": runtime_result,
        "adaptive_decision": adaptive_decision,
    }


__all__ = [
    "GOAL_WORK_PACKAGE_MAINLINE_SCHEMA",
    "run_goal_work_package_mainline",
]
