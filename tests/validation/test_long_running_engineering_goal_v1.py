from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from core.control.task_lifecycle_monitor import TaskLifecycleMonitor
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.evidence import EvidenceRecord, EvidenceValidator
from core.tasks.engineering_adaptive_planner import EngineeringAdaptivePlanner
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.scheduler import Scheduler
from core.tasks.task_repository import TaskRepository
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]




GOAL = "Build a minimal deterministic todo text-processing utility."


def _authority(task_id: str, step_id: str, scope: str) -> dict[str, Any]:
    return {
        "authority_source": "human_review",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "mutation",
        "ownership_source": "human_review",
        "authority_scope": scope,
        "task_id": task_id,
        "step_id": step_id,
        "runtime_session": "long_goal_validation_v1",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": f"trace_{task_id}",
    }


def _runtime_result(
    *,
    goal_id: str,
    task: Mapping[str, Any],
    completed: list[str],
    remaining: list[str],
    complete: bool,
    recoverable_failure: bool = False,
) -> dict[str, Any]:
    failed = [str(task["task_id"])] if recoverable_failure else []
    state = "replan" if recoverable_failure else "complete" if complete else "running"
    goal_state = "failed" if recoverable_failure else "completed" if complete else "next_task_generated"
    result = {
        "ok": not recoverable_failure,
        "state": state,
        "decision_state": state,
        "stop_reason": "missing_requirement" if recoverable_failure else state,
        "next_runtime_request": (
            {}
            if complete or recoverable_failure
            else {"goal_id": goal_id, "payload": {"goal_id": goal_id, "goal": GOAL, "remaining_tasks": remaining}}
        ),
        "iterations": [
            {
                "goal_id": goal_id,
                "continuation_result": {
                    "ok": not recoverable_failure,
                    "goal_lifecycle": {
                        "goal_id": goal_id,
                        "goal_state": goal_state,
                        "completed_tasks": copy.deepcopy(completed),
                        "remaining_tasks": copy.deepcopy(remaining),
                        "failed_tasks": failed,
                        "blocked_tasks": [],
                    },
                    "latest_result": copy.deepcopy(dict(task)),
                },
            }
        ],
    }
    return result


class SchedulerBackedValidationRunner:
    """Validation bridge: GoalLoop -> adaptive decision -> Scheduler/Runtime."""

    def __init__(
        self,
        *,
        scheduler: Scheduler,
        repository: EngineeringGoalRepository,
        task_specs: list[dict[str, Any]],
    ) -> None:
        self.scheduler = scheduler
        self.repository = repository
        self.task_specs = copy.deepcopy(task_specs)
        self.planner = EngineeringAdaptivePlanner()
        self.completion_authority = GoalCompletionAuthority()
        self.task_ids: list[str] = []
        self.result_history: list[dict[str, Any]] = []
        self._index = 0

    def run_goal(self, goal_id: str, *, goal_lineage=None) -> dict[str, Any]:
        spec = self.task_specs[self._index]
        self._index += 1
        created = self.scheduler._create_task_record(
            goal=spec["goal"],
            initial_status="queued",
            execution_authority=_authority(spec["task_id"], spec["step_id"], spec["scope"]),
            authority_propagation_required=True,
            max_replans=1,
        )
        assert created["ok"] is True
        task_id = str(created.get("task_id") or created.get("task_name") or created["task"]["task_id"])
        self.task_ids.append(task_id)

        ticks: list[dict[str, Any]] = []
        for _ in range(8):
            ticks.append(self.scheduler.tick())
            task = self.scheduler._get_task_from_repo(task_id)
            assert isinstance(task, dict)
            if str(task.get("status") or "").lower() in {"finished", "done", "failed", "error"}:
                break

        task = self.scheduler._get_task_from_repo(task_id)
        assert isinstance(task, dict)
        recoverable_failure = bool(spec.get("recoverable_failure"))
        actual_status = str(task.get("status") or "").lower()
        if recoverable_failure:
            assert actual_status in {"failed", "error"}
        else:
            assert actual_status in {"finished", "done"}
        completed = [item["task_id"] for item in self.result_history if item["ok"]]
        if not recoverable_failure:
            completed.append(task_id)
        remaining = [item["task_id"] for item in self.task_specs[self._index :]]
        runtime_result = _runtime_result(
            goal_id=goal_id,
            task=task,
            completed=completed,
            remaining=remaining,
            complete=self._index == len(self.task_specs),
            recoverable_failure=recoverable_failure,
        )
        root_cause = (
            {
                "stop_reason": "missing_requirement",
                "failed_tasks": [task_id],
                "latest_observation": {"recoverable": True, "missing": "Deterministic ordering"},
            }
            if recoverable_failure
            else {}
        )
        decision = self.planner.decide_next_action(
            goal=self.repository.load_goal(goal_id) or {"goal_id": goal_id, "summary": GOAL},
            runtime_result=runtime_result,
            runtime_root_cause=root_cause,
        )
        if decision["decision"] == "complete":
            decision["goal_completion_authority_result"] = self.completion_authority.complete_goal(
                goal_id=goal_id,
                evidence_refs=[
                    EvidenceValidator().validate(
                        EvidenceRecord(completed_task_id, goal_id, None, "validation", "completed", "now")
                    )
                    for completed_task_id in completed
                ],
                all_subgoals_completed=not remaining and not recoverable_failure,
                reason="long_running_validation_tasks_completed",
            )
        history_record = {
            "task_id": task_id,
            "ok": not recoverable_failure,
            "status": task["status"],
            "history": copy.deepcopy(task.get("history") or []),
            "results": copy.deepcopy(task.get("results") or []),
            "ticks": ticks,
            "adaptive_decision": copy.deepcopy(decision),
        }
        self.result_history.append(history_record)
        return {
            "ok": not recoverable_failure,
            "goal_id": goal_id,
            "runtime_result": runtime_result,
            "runtime_root_cause": root_cause,
            "adaptive_decision": decision,
            "result_history": copy.deepcopy(self.result_history),
            "execution_path": {
                "scheduler_dispatches_only": True,
                "runtime_execution_owner": True,
                "direct_execution": False,
            },
        }


def _spec(task_id: str, step_id: str, goal: str, scope: str, *, recoverable_failure: bool = False) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "step_id": step_id,
        "goal": goal,
        "scope": scope,
        "recoverable_failure": recoverable_failure,
    }


def test_long_running_engineering_goal_v1(tmp_path: Path) -> None:
    workspace = tmp_path / "runtime_workspace"
    task_repository = TaskRepository(db_path=str(workspace / "tasks.json"))
    scheduler = Scheduler(task_repo=task_repository, workspace_dir=str(workspace), allow_commands=True)
    scheduler.agent_loop = None
    scheduler._agent_loop = None
    scheduler.task_manager = None
    monitor = TaskLifecycleMonitor(task_repository)
    goal_repository = EngineeringGoalRepository(tmp_path)

    initial_goal = goal_repository.save_goal({"goal_id": "long_goal_todo_v1", "summary": GOAL})
    first_runner = SchedulerBackedValidationRunner(
        scheduler=scheduler,
        repository=goal_repository,
        task_specs=[
            _spec(
                "todo_tool",
                "write_tool",
                "Write tool :: step=write_file:shared/long_goal/todo_tool.py|def normalize(lines): return sorted({line.strip() for line in lines if line.strip()})",
                "workspace/shared/long_goal/todo_tool.py",
            ),
            _spec(
                "missing_readme_requirement",
                "verify_missing_requirement",
                "Verify missing requirement :: step=verify:shared/long_goal/README.md,contains=Deterministic ordering",
                "workspace/shared/long_goal/README.md",
                recoverable_failure=True,
            ),
        ],
    )
    first_loop = EngineeringGoalLoop(
        repo_root=tmp_path,
        repository=goal_repository,
        runner=first_runner,
    ).run_until_terminal(initial_goal["goal_id"], max_cycles=3, max_replans=1, max_continuations=2)

    assert first_loop["stop_reason"] == "replan"
    assert first_loop["replan_count"] == 1
    assert first_loop["cycles"][-1]["outcome_class"] == "recoverable_failure"
    assert first_loop["cycles"][-1]["adaptive_planning_record"]["next_action"] == "request_replan"

    revised_goal = goal_repository.save_goal(
        {
            "goal_id": "long_goal_todo_v1_revised",
            "summary": "Satisfy missing README requirement and finish the todo utility.",
            "metadata": {"source_replan_record": first_loop["cycles"][-1]["replan_record"]},
        }
    )
    second_runner = SchedulerBackedValidationRunner(
        scheduler=scheduler,
        repository=goal_repository,
        task_specs=[
            _spec(
                "readme_repair",
                "write_readme",
                "Write README :: step=write_file:shared/long_goal/README.md|# Todo Tool - Deterministic ordering and duplicate removal.",
                "workspace/shared/long_goal/README.md",
            ),
            _spec(
                "result_report",
                "write_report",
                "Write report :: step=write_file:shared/long_goal/result_report.md|Goal complete: tool, README, recoverable failure, bounded replan, and runtime history verified.",
                "workspace/shared/long_goal/result_report.md",
            ),
        ],
    )
    second_loop = EngineeringGoalLoop(
        repo_root=tmp_path,
        repository=goal_repository,
        runner=second_runner,
    ).run_until_terminal(revised_goal["goal_id"], max_cycles=3, max_replans=0, max_continuations=2)

    task_ids = first_runner.task_ids + second_runner.task_ids
    snapshots = [monitor.inspect(task_id) for task_id in task_ids]
    records = [task_repository.get_task(task_id) for task_id in task_ids]
    artifacts = [
        workspace / "shared" / "long_goal" / "todo_tool.py",
        workspace / "shared" / "long_goal" / "README.md",
        workspace / "shared" / "long_goal" / "result_report.md",
    ]

    assert second_loop["ok"] is True
    assert second_loop["stop_reason"] == "complete"
    assert second_loop["goal_completion_authority_result"]["accepted"] is True
    assert second_loop["goal_completion_authority_result"]["completed"] is True
    assert second_loop["goal_completion_authority_result"]["evidence_refs"]
    assert len(task_ids) == 4
    assert all(snapshot["ok"] for snapshot in snapshots)
    assert any(snapshot["error_summary"] for snapshot in snapshots)
    assert all(record and record["history"] for record in records)
    assert all(record and isinstance(record.get("results"), list) for record in records)
    assert all(path.exists() for path in artifacts)
    assert "Deterministic ordering" in artifacts[1].read_text(encoding="utf-8")

    evidence = {
        "goal_id": initial_goal["goal_id"],
        "revised_goal_id": revised_goal["goal_id"],
        "task_ids": task_ids,
        "lifecycle_timeline": [record["history"] for record in records if record],
        "step_history": [record["results"] for record in records if record],
        "result_history": first_runner.result_history + second_runner.result_history,
        "adaptive_decisions": [
            first_loop["cycles"][-1]["adaptive_decision_record"],
            second_loop["cycles"][-1]["adaptive_decision_record"],
        ],
        "replan_count": first_loop["replan_count"] + second_loop["replan_count"],
        "continuation_count": first_loop["continuation_count"] + second_loop["continuation_count"],
        "final_status": second_loop["stop_reason"],
        "final_artifacts": [str(path) for path in artifacts],
        "final_result_summary": artifacts[-1].read_text(encoding="utf-8"),
        "monitor_snapshots": snapshots,
    }
    assert evidence["replan_count"] == 1
    assert evidence["continuation_count"] == 2
    assert {item["outcome_class"] for item in evidence["adaptive_decisions"]} >= {"recoverable_failure", "success"}
    assert first_loop["execution_path"]["goal_loop_owns_long_horizon_cycles"] is True
    assert first_loop["execution_path"]["adaptive_planner_decides_only"] is True
    assert all(item["execution_path"]["executes_tasks"] is False for item in evidence["adaptive_decisions"])
    assert all(
        record
        and record["execution_authority"]["execution_authority_endpoint"] == "step_executor"
        and record["authority_propagation_required"] is True
        for record in records
    )
