from __future__ import annotations

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import EngineeringGoalRunner


class RuntimeStub:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls: list[list[dict]] = []

    def run(self, goals):
        self.calls.append([dict(goal) for goal in goals])
        return self.result


class DummyReporter:
    def __init__(self, summary: dict) -> None:
        self.summary = summary

    def build_summary(self) -> dict:
        return self.summary


def _runtime(*, ok: bool, state: str, goal_state: str, remaining=None, completed=None, failed=None) -> dict:
    return {
        "schema": "zero.engineering_runtime_orchestrator.v1",
        "ok": ok,
        "mode": "engineering_runtime_orchestrator",
        "state": state,
        "decision_state": state,
        "stop_reason": state,
        "iterations": [
            {
                "iteration": 1,
                "goal_id": "goal_1",
                "state": state,
                "continuation_result": {
                    "ok": ok,
                    "terminal": goal_state in {"completed", "failed", "blocked", "cancelled"},
                    "stopped_reason": goal_state,
                    "goal_lifecycle": {
                        "goal_id": "goal_1",
                        "goal_state": goal_state,
                        "completed_tasks": list(completed or []),
                        "remaining_tasks": list(remaining or []),
                        "failed_tasks": list(failed or []),
                        "blocked_tasks": [],
                    },
                },
            }
        ],
    }


def _repository_with_goal(tmp_path) -> EngineeringGoalRepository:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_1", "summary": "Build demo system"})
    return repository


def test_goal_runner_adds_complete_adaptive_decision_after_runtime_complete(tmp_path) -> None:
    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=_repository_with_goal(tmp_path),
        runtime_orchestrator=RuntimeStub(
            _runtime(ok=True, state="complete", goal_state="completed", completed=["goal_1_breakdown", "goal_1_result"])
        ),
    ).run_goal("goal_1")

    assert result["ok"] is True
    assert result["adaptive_decision"]["decision"] == "complete"
    assert result["adaptive_decision"]["continuation_plan"] == {}
    assert result["adaptive_decision"]["progress"]["complete"] is True


def test_goal_runner_adds_continue_plan_for_incomplete_goal(tmp_path) -> None:
    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=_repository_with_goal(tmp_path),
        runtime_orchestrator=RuntimeStub(
            _runtime(
                ok=True,
                state="running",
                goal_state="next_task_generated",
                completed=["goal_1_breakdown"],
                remaining=["goal_1_result"],
            )
        ),
    ).run_goal("goal_1")

    decision = result["adaptive_decision"]
    assert result["ok"] is True
    assert decision["decision"] == "continue"
    assert decision["continuation_plan"]["remaining_tasks"] == ["goal_1_result"]
    assert decision["continuation_plan"]["next_runtime_request"]["goal_id"] == "goal_1"
    assert decision["execution_path"]["executes_tasks"] is False


def test_goal_runner_blocks_and_preserves_runtime_root_cause(tmp_path) -> None:
    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=_repository_with_goal(tmp_path),
        runtime_orchestrator=RuntimeStub(
            _runtime(ok=False, state="failed", goal_state="failed", completed=["goal_1_breakdown"], failed=["critical_failure"])
        ),
    ).run_goal("goal_1")

    assert result["ok"] is False
    assert result["adaptive_decision"]["decision"] == "blocked"
    assert result["runtime_root_cause"]["failed_tasks"] == ["critical_failure"]
    assert result["adaptive_decision"]["root_cause"]["failed_tasks"] == ["critical_failure"]


def test_goal_runner_replans_recoverable_missing_output(tmp_path) -> None:
    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=_repository_with_goal(tmp_path),
        runtime_orchestrator=RuntimeStub(
            _runtime(ok=False, state="replan", goal_state="failed", completed=["goal_1_breakdown"], failed=["missing_output"])
        ),
    ).run_goal("goal_1")

    decision = result["adaptive_decision"]
    assert result["ok"] is False
    assert decision["decision"] == "replan"
    assert decision["replan_request"]["reason"] == "replan"
    assert decision["continuation_plan"] == {}
    assert result["runtime_result"]["iterations"][0]["continuation_result"]["goal_lifecycle"]["failed_tasks"] == ["missing_output"]


def test_goal_runner_blocking_issue_forces_blocked_without_mutating_runtime(tmp_path) -> None:
    runtime = _runtime(ok=True, state="complete", goal_state="completed", completed=["goal_1_breakdown", "goal_1_result"])
    issue = {"issue_id": "blocker-1", "severity": "critical", "blocks_current_task": True}

    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=_repository_with_goal(tmp_path),
        runtime_orchestrator=RuntimeStub(runtime),
        issue_reporter=DummyReporter({"issues": [issue], "blocking_issues": [], "success_allowed": True}),
    ).run_goal("goal_1")

    assert result["ok"] is False
    assert result["adaptive_decision"]["decision"] == "blocked"
    assert result["adaptive_decision"]["blocking_issues"] == [issue]
    assert result["blocking_issues"] == [issue]
    assert runtime["iterations"][0]["continuation_result"]["goal_lifecycle"]["goal_state"] == "completed"
    assert result["runtime_result"] == runtime


def test_goal_runner_non_blocking_issue_does_not_block_complete(tmp_path) -> None:
    issue = {"issue_id": "later-1", "severity": "low", "recommended_action": "report_only"}

    result = EngineeringGoalRunner(
        repo_root=tmp_path,
        repository=_repository_with_goal(tmp_path),
        runtime_orchestrator=RuntimeStub(
            _runtime(ok=True, state="complete", goal_state="completed", completed=["goal_1_breakdown", "goal_1_result"])
        ),
        issue_reporter=DummyReporter({"issues": [issue], "blocking_issues": [], "success_allowed": True}),
    ).run_goal("goal_1")

    assert result["ok"] is True
    assert result["adaptive_decision"]["decision"] == "complete"
    assert result["issues_deferred"] == [issue]
    assert result["blocking_issues"] == []


def test_real_goal_run_complete_is_not_secondarily_continued_or_polluted(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"summary": "Build demo system"})

    result = EngineeringGoalRunner(repo_root=tmp_path, repository=repository).run_goal(goal["goal_id"])

    runtime = result["runtime_result"]
    continuation = runtime["iterations"][0]["continuation_result"]
    lifecycle = continuation["goal_lifecycle"]
    assert runtime["state"] == "complete"
    assert continuation["cycle_count"] == 2
    assert lifecycle["goal_state"] == "completed"
    assert lifecycle["failed_tasks"] == []
    assert continuation["goal_lifecycle"]["failed_tasks"] == []
    assert result["adaptive_decision"]["decision"] == "complete"
    assert result["issues_found"] == []
    assert result["issues_deferred"] == []
    assert result["deferred_issues"] == []
    assert result["blocking_issues"] == []
    assert result["success_allowed"] is True
    assert result["engineering_result_contract"]["blocking_issue_blocks_success"] is True
