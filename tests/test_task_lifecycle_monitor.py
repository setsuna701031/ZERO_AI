from __future__ import annotations

import inspect

from core.control.task_control_api import TaskControlAPI
from core.control.task_lifecycle_monitor import TaskLifecycleMonitor


class ReadOnlyRepository:
    def __init__(self, task):
        self.task = task
        self.get_calls = 0
        self.write_calls = 0

    def get_task(self, task_id):
        self.get_calls += 1
        return self.task if self.task.get("task_id") == task_id else None

    def update_task(self, *args, **kwargs):
        self.write_calls += 1
        raise AssertionError("monitor must not write")


class NoExecutionGateway:
    def __init__(self):
        self.execution_calls = 0

    def tick(self):
        self.execution_calls += 1

    def execute(self):
        self.execution_calls += 1


def _complete_task():
    return {
        "task_id": "task_lifecycle",
        "status": "running",
        "lifecycle_state": "executing",
        "current_stage": "verification",
        "goal": "Verify the controlled change",
        "current_step_index": 1,
        "steps": [{"type": "read_file"}, {"type": "verify"}],
        "created_at": 10,
        "updated_at": 20,
        "result_summary": "verification in progress",
        "last_error": "previous attempt failed",
        "issue_reports": [{"issue": "non-mainline warning"}],
        "artifact_paths": {"report": "workspace/report.json"},
        "next_action": "continue",
    }


def test_lifecycle_inspect_is_read_only_and_includes_required_fields() -> None:
    repository = ReadOnlyRepository(_complete_task())
    snapshot = TaskLifecycleMonitor(repository).inspect("task_lifecycle")

    required = {
        "task_id",
        "status",
        "lifecycle_state",
        "current_stage",
        "current_goal",
        "current_step",
        "created_at",
        "updated_at",
        "result_summary",
        "error_summary",
        "issue_reports",
        "artifacts",
        "next_action",
        "outcome_class",
        "replan_count",
        "continuation_count",
        "adaptive_decision",
        "decision_reason",
        "decision_evidence",
        "data_completeness",
    }
    assert snapshot["ok"] is True
    assert required.issubset(snapshot)
    assert snapshot["current_step"] == {"type": "verify"}
    assert repository.get_calls == 1
    assert repository.write_calls == 0


def test_unavailable_fields_are_explicit_and_not_fabricated() -> None:
    repository = ReadOnlyRepository({"task_id": "minimal", "status": "queued"})
    snapshot = TaskLifecycleMonitor(repository).inspect("minimal")
    unavailable = {item["field"]: item for item in snapshot["data_completeness"]}

    assert snapshot["current_stage"] is None
    assert snapshot["current_step"] is None
    assert snapshot["next_action"] is None
    assert unavailable["current_stage"]["available"] is False
    assert unavailable["current_step"]["available"] is False
    assert unavailable["next_action"]["available"] is False
    assert unavailable["outcome_class"]["available"] is False
    assert unavailable["adaptive_decision"]["available"] is False


def test_adaptive_planning_fields_are_projected_read_only() -> None:
    task = _complete_task()
    task["adaptive_planning_record"] = {
        "outcome_class": "recoverable_failure",
        "replan_count": 1,
        "continuation_count": 2,
        "next_action": "request_replan",
        "decision_reason": "runtime_outcome_recoverable_failure",
    }

    snapshot = TaskLifecycleMonitor(ReadOnlyRepository(task)).inspect("task_lifecycle")

    assert snapshot["outcome_class"] == "recoverable_failure"
    assert snapshot["replan_count"] == 1
    assert snapshot["continuation_count"] == 2
    assert snapshot["adaptive_decision"] == "request_replan"
    assert snapshot["decision_reason"] == "runtime_outcome_recoverable_failure"


def test_issue_reports_and_artifacts_are_surfaced() -> None:
    snapshot = TaskLifecycleMonitor(ReadOnlyRepository(_complete_task())).inspect("task_lifecycle")

    assert snapshot["issue_reports"] == [{"issue": "non-mainline warning"}]
    assert snapshot["artifacts"] == [{"name": "report", "path": "workspace/report.json"}]


def test_control_inspect_remains_backward_compatible_and_monitor_does_not_execute() -> None:
    repository = ReadOnlyRepository(_complete_task())
    gateway = NoExecutionGateway()
    control = TaskControlAPI(gateway, repository)

    inspected = control.inspect_task("task_lifecycle")
    monitored = control.monitor_task("task_lifecycle")

    assert inspected["last_result_summary"] == inspected["result_summary"]
    assert inspected["issue_report"] == inspected["issue_reports"]
    assert monitored["lifecycle_state"] == "executing"
    assert gateway.execution_calls == 0


def test_monitor_has_no_execution_tool_or_mutation_dependency() -> None:
    source = inspect.getsource(__import__("core.control.task_lifecycle_monitor", fromlist=["TaskLifecycleMonitor"]))

    assert "core.tools" not in source
    assert "core.runtime" not in source
    assert "StepExecutor" not in source
    assert ".execute(" not in source
    assert ".tick(" not in source
    assert "update_task" not in source
    assert "save(" not in source
