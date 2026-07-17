from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from core.control.task_lifecycle_monitor import TaskLifecycleMonitor
from core.evidence.decision_evidence import DecisionEvidenceRepository
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.evidence import EvidenceRecord, EvidenceValidator
from core.tasks.engineering_adaptive_planner import EngineeringAdaptivePlanner
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.scheduler import Scheduler
from core.tasks.task_repository import TaskRepository
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]




GOAL = "Build a deterministic CLI note-processing utility."
TERMINAL_STATUSES = {"finished", "done", "failed", "error"}


def _authority(task_id: str, step_id: str, scope: str, action_type: str) -> dict[str, Any]:
    return {
        "authority_source": "human_review",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": action_type,
        "ownership_source": "human_review",
        "authority_scope": scope,
        "task_id": task_id,
        "step_id": step_id,
        "runtime_session": "long_goal_validation_v2",
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
    recoverable_failure: bool,
    failure_reason: str,
) -> dict[str, Any]:
    failed = [str(task["task_id"])] if recoverable_failure else []
    state = "replan" if recoverable_failure else "complete" if complete else "running"
    goal_state = "failed" if recoverable_failure else "completed" if complete else "next_task_generated"
    return {
        "ok": not recoverable_failure,
        "state": state,
        "decision_state": state,
        "stop_reason": failure_reason if recoverable_failure else state,
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


class SchedulerBackedValidationRunner:
    """Validation-only bridge from GoalLoop decisions into real Scheduler ticks."""

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
            execution_authority=_authority(
                spec["task_id"],
                spec["step_id"],
                spec["scope"],
                spec["action_type"],
            ),
            authority_propagation_required=True,
            max_replans=1,
        )
        assert created["ok"] is True
        task_id = str(created.get("task_id") or created.get("task_name") or created["task"]["task_id"])
        self.task_ids.append(task_id)

        ticks: list[dict[str, Any]] = []
        for _ in range(10):
            ticks.append(self.scheduler.tick())
            task = self.scheduler._get_task_from_repo(task_id)
            assert isinstance(task, dict)
            if str(task.get("status") or "").lower() in TERMINAL_STATUSES:
                break

        task = self.scheduler._get_task_from_repo(task_id)
        assert isinstance(task, dict)
        recoverable_failure = bool(spec.get("recoverable_failure"))
        actual_status = str(task.get("status") or "").lower()
        assert actual_status in ({"failed", "error"} if recoverable_failure else {"finished", "done"})

        completed = [item["task_id"] for item in self.result_history if item["ok"]]
        if not recoverable_failure:
            completed.append(task_id)
        remaining = [item["task_id"] for item in self.task_specs[self._index :]]
        failure_reason = str(spec.get("failure_reason") or "missing_requirement")
        runtime_result = _runtime_result(
            goal_id=goal_id,
            task=task,
            completed=completed,
            remaining=remaining,
            complete=self._index == len(self.task_specs),
            recoverable_failure=recoverable_failure,
            failure_reason=failure_reason,
        )
        root_cause = (
            {
                "stop_reason": failure_reason,
                "failed_tasks": [task_id],
                "latest_observation": {
                    "recoverable": True,
                    "missing": str(spec.get("missing") or "required validation output"),
                },
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
            "last_error": copy.deepcopy(task.get("last_error")),
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


def _spec(
    task_id: str,
    step_id: str,
    goal: str,
    scope: str,
    *,
    action_type: str = "mutation",
    recoverable_failure: bool = False,
    failure_reason: str = "",
    missing: str = "",
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "step_id": step_id,
        "goal": goal,
        "scope": scope,
        "action_type": action_type,
        "recoverable_failure": recoverable_failure,
        "failure_reason": failure_reason,
        "missing": missing,
    }


def _run_phase(
    *,
    tmp_path: Path,
    scheduler: Scheduler,
    repository: EngineeringGoalRepository,
    goal_id: str,
    summary: str,
    task_specs: list[dict[str, Any]],
    source_replan_record: Mapping[str, Any] | None = None,
    max_replans: int = 1,
) -> tuple[dict[str, Any], SchedulerBackedValidationRunner]:
    repository.save_goal(
        {
            "goal_id": goal_id,
            "summary": summary,
            "metadata": {"source_replan_record": copy.deepcopy(dict(source_replan_record or {}))},
        }
    )
    runner = SchedulerBackedValidationRunner(
        scheduler=scheduler,
        repository=repository,
        task_specs=task_specs,
    )
    loop = EngineeringGoalLoop(repo_root=tmp_path, repository=repository, runner=runner).run_until_terminal(
        goal_id,
        max_cycles=5,
        max_replans=max_replans,
        max_continuations=4,
    )
    return loop, runner


def test_long_running_engineering_goal_v2(tmp_path: Path) -> None:
    workspace = tmp_path / "runtime_workspace"
    task_repository = TaskRepository(db_path=str(workspace / "tasks.json"))
    scheduler = Scheduler(task_repo=task_repository, workspace_dir=str(workspace), allow_commands=True)
    scheduler.agent_loop = None
    scheduler._agent_loop = None
    scheduler.task_manager = None
    decision_evidence_repository = DecisionEvidenceRepository(tmp_path)
    monitor = TaskLifecycleMonitor(task_repository, decision_evidence_repository)
    goal_repository = EngineeringGoalRepository(tmp_path)

    tool_code = (
        "import sys; normalize=lambda lines: sorted({line.strip() for line in lines if line.strip()}); "
        "print('\\n'.join(normalize(sys.stdin.readlines()))) if __name__ == '__main__' else None"
    )
    test_code = (
        "import pathlib,subprocess,sys; p=pathlib.Path(__file__).with_name('note_tool.py'); "
        "r=subprocess.run([sys.executable,str(p)],input='beta\\nalpha\\nbeta\\n',text=True,capture_output=True); "
        "assert r.returncode == 0 and r.stdout == 'alpha\\nbeta\\n'; print('CLI_OK')"
    )

    phase_one, runner_one = _run_phase(
        tmp_path=tmp_path,
        scheduler=scheduler,
        repository=goal_repository,
        goal_id="long_goal_note_v2",
        summary=GOAL,
        task_specs=[
            _spec(
                "write_note_tool",
                "write_note_tool",
                f"Write note tool :: step=write_file:shared/long_goal_v2/note_tool.py|{tool_code}",
                "workspace/shared/long_goal_v2/note_tool.py",
            ),
            _spec(
                "verify_missing_test",
                "verify_missing_test",
                "Verify missing test :: step=verify:shared/long_goal_v2/test_note_tool.py,contains=CLI_OK",
                "workspace/shared/long_goal_v2/test_note_tool.py",
                action_type="read",
                recoverable_failure=True,
                failure_reason="missing_cli_test",
                missing="test_note_tool.py with CLI_OK assertion",
            ),
        ],
    )
    assert phase_one["stop_reason"] == "replan"
    assert phase_one["cycles"][-1]["outcome_class"] == "recoverable_failure"

    phase_two, runner_two = _run_phase(
        tmp_path=tmp_path,
        scheduler=scheduler,
        repository=goal_repository,
        goal_id="long_goal_note_v2_revised_1",
        summary="Add and execute the missing deterministic CLI test.",
        source_replan_record=phase_one["cycles"][-1]["replan_record"],
        task_specs=[
            _spec(
                "write_cli_test",
                "write_cli_test",
                f"Write CLI test :: step=write_file:shared/long_goal_v2/test_note_tool.py|{test_code}",
                "workspace/shared/long_goal_v2/test_note_tool.py",
            ),
            _spec(
                "run_cli_test_initial",
                "run_cli_test_initial",
                "Run CLI test :: step=run_python:shared/long_goal_v2/test_note_tool.py",
                "workspace/shared/long_goal_v2/test_note_tool.py",
                action_type="execute",
            ),
            _spec(
                "verify_missing_readme",
                "verify_missing_readme",
                "Verify missing README :: step=verify:shared/long_goal_v2/README.md,contains=Deterministic CLI",
                "workspace/shared/long_goal_v2/README.md",
                action_type="read",
                recoverable_failure=True,
                failure_reason="missing_readme_requirement",
                missing="README deterministic CLI usage",
            ),
        ],
    )
    assert phase_two["stop_reason"] == "replan"
    assert phase_two["cycles"][-1]["outcome_class"] == "recoverable_failure"

    phase_three, runner_three = _run_phase(
        tmp_path=tmp_path,
        scheduler=scheduler,
        repository=goal_repository,
        goal_id="long_goal_note_v2_revised_2",
        summary="Repair documentation, revalidate CLI, and write the final result report.",
        source_replan_record=phase_two["cycles"][-1]["replan_record"],
        max_replans=0,
        task_specs=[
            _spec(
                "write_readme",
                "write_readme",
                "Write README :: step=write_file:shared/long_goal_v2/README.md|# Note Tool - Deterministic CLI: reads stdin, removes blank and duplicate notes, sorts output.",
                "workspace/shared/long_goal_v2/README.md",
            ),
            _spec(
                "run_cli_test_final",
                "run_cli_test_final",
                "Run final CLI test :: step=run_python:shared/long_goal_v2/test_note_tool.py",
                "workspace/shared/long_goal_v2/test_note_tool.py",
                action_type="execute",
            ),
            _spec(
                "write_result_report",
                "write_result_report",
                "Write result report :: step=write_file:shared/long_goal_v2/result_report.md|Goal complete: four artifacts, eight Scheduler tasks, two recoverable failures, bounded replanning, and deterministic CLI execution verified.",
                "workspace/shared/long_goal_v2/result_report.md",
            ),
        ],
    )

    loops = [phase_one, phase_two, phase_three]
    runners = [runner_one, runner_two, runner_three]
    task_ids = [task_id for runner in runners for task_id in runner.task_ids]
    result_history = [item for runner in runners for item in runner.result_history]
    records = [task_repository.get_task(task_id) for task_id in task_ids]
    snapshots = [monitor.inspect(task_id) for task_id in task_ids]
    failed_records = [item for item in result_history if not item["ok"]]
    adaptive_decisions = [
        cycle["adaptive_decision_record"]
        for loop in loops
        for cycle in loop["cycles"]
    ]
    artifacts = [
        workspace / "shared" / "long_goal_v2" / "note_tool.py",
        workspace / "shared" / "long_goal_v2" / "test_note_tool.py",
        workspace / "shared" / "long_goal_v2" / "README.md",
        workspace / "shared" / "long_goal_v2" / "result_report.md",
    ]
    replan_count = sum(loop["replan_count"] for loop in loops)
    continuation_count = sum(loop["continuation_count"] for loop in loops)
    decision_evidence_records = decision_evidence_repository.list_records()
    replan_evidence = [item for item in decision_evidence_records if item["next_action"] == "request_replan"]

    assert phase_three["ok"] is True
    assert phase_three["stop_reason"] == "complete"
    assert phase_three["goal_completion_authority_result"]["accepted"] is True
    assert phase_three["goal_completion_authority_result"]["completed"] is True
    assert phase_three["goal_completion_authority_result"]["evidence_refs"]
    assert len(task_ids) == 8
    assert len(failed_records) == 2
    assert replan_count == 2
    assert continuation_count >= 2
    assert len(adaptive_decisions) >= 2
    assert len(replan_evidence) == 2
    assert all(item["task_id"] in task_ids for item in replan_evidence)
    assert all(item["decision_reason"] for item in replan_evidence)
    assert all(item["observed_event"]["runtime_state"] == "replan" for item in replan_evidence)
    assert sum(bool(snapshot["decision_evidence"]) for snapshot in snapshots) == len(task_ids)
    assert all(path.exists() for path in artifacts)
    assert "normalize=lambda lines" in artifacts[0].read_text(encoding="utf-8")
    assert "CLI_OK" in artifacts[1].read_text(encoding="utf-8")
    assert "Deterministic CLI" in artifacts[2].read_text(encoding="utf-8")
    assert "eight Scheduler tasks" in artifacts[3].read_text(encoding="utf-8")
    assert all(snapshot["ok"] for snapshot in snapshots)
    assert sum(bool(snapshot["error_summary"]) for snapshot in snapshots) >= 2
    assert all(record and record["history"] for record in records)
    assert all(record and isinstance(record.get("results"), list) for record in records)
    assert all(item["results"] for item in result_history)
    assert all(item["last_error"] for item in failed_records)

    evidence = {
        "goal_id": "long_goal_note_v2",
        "task_ids": task_ids,
        "lifecycle_timeline": [record["history"] for record in records if record],
        "step_history": [record["results"] for record in records if record],
        "failed_verification_records": failed_records,
        "result_history": result_history,
        "adaptive_decisions": adaptive_decisions,
        "decision_evidence": decision_evidence_records,
        "replan_count": replan_count,
        "continuation_count": continuation_count,
        "artifacts_created": [str(path) for path in artifacts],
        "final_result_summary": artifacts[-1].read_text(encoding="utf-8"),
        "monitor_snapshots": snapshots,
    }
    assert {item["outcome_class"] for item in evidence["adaptive_decisions"]} >= {
        "recoverable_failure",
        "partial_success",
        "success",
    }
    assert sum(item["decision"] == "replan" for item in evidence["adaptive_decisions"]) == 2
    assert sum(item["decision"] == "continue" for item in evidence["adaptive_decisions"]) >= 2
    assert all(loop["execution_path"]["goal_loop_owns_long_horizon_cycles"] is True for loop in loops)
    assert all(loop["execution_path"]["adaptive_planner_decides_only"] is True for loop in loops)
    assert all(item["execution_path"]["executes_tasks"] is False for item in evidence["adaptive_decisions"])
    assert all(
        record
        and record["execution_authority"]["execution_authority_endpoint"] == "step_executor"
        and record["authority_propagation_required"] is True
        for record in records
    )
