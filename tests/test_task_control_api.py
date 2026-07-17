from __future__ import annotations

import inspect

from core.control.task_control_api import TaskControlAPI
from core.tasks.scheduler import Scheduler
from core.tasks.task_repository import TaskRepository


class FakeRepository:
    def __init__(self) -> None:
        self.tasks = [
            {
                "task_id": "task_old",
                "title": "Old",
                "goal": "older work",
                "status": "finished",
                "created_at": 1,
                "updated_at": 2,
                "final_answer": "done",
            },
            {
                "task_id": "task_new",
                "title": "New",
                "goal": "new work",
                "task_type": "engineering_task",
                "status": "failed",
                "created_at": 3,
                "updated_at": 4,
                "last_error": "verification failed",
                "issue_report": {"issue": "non-mainline failure"},
            },
        ]
        self.reads = 0

    def get_task(self, task_id: str):
        self.reads += 1
        return next((task for task in self.tasks if task["task_id"] == task_id), None)

    def list_tasks(self):
        self.reads += 1
        return list(self.tasks)


class FakeSubmissionGateway:
    def __init__(self, repository: FakeRepository) -> None:
        self.task_repo = repository
        self.submissions = []
        self.cancellations = []
        self.execution_calls = 0

    def submit_task(self, **kwargs):
        self.submissions.append(kwargs)
        return {"ok": True, "task_id": "task_submitted", "status": "queued"}

    def cancel_task(self, task_id: str):
        self.cancellations.append(task_id)
        return {"ok": True, "task_id": task_id, "status": "cancelled"}

    def tick(self):
        self.execution_calls += 1


def test_submit_task_routes_through_approved_submission_boundary() -> None:
    repository = FakeRepository()
    gateway = FakeSubmissionGateway(repository)

    result = TaskControlAPI(gateway, repository).submit_task(
        title="Controlled task",
        instruction="Implement the requested engineering change",
        mode="controlled",
    )

    assert result == {
        "ok": True,
        "accepted": True,
        "task_id": "task_submitted",
        "reason": "",
        "status": "queued",
    }
    assert gateway.submissions[0]["source"] == "task_control_api"
    assert gateway.submissions[0]["task_type"] == "engineering_task"
    assert gateway.execution_calls == 0


def test_inspect_and_list_are_read_only_and_preserve_issue_reports() -> None:
    repository = FakeRepository()
    gateway = FakeSubmissionGateway(repository)
    control = TaskControlAPI(gateway, repository)

    inspected = control.inspect_task("task_new")
    listed = control.list_recent_tasks(limit=1)

    assert inspected["status"] == "failed"
    assert inspected["last_result_summary"] == "verification failed"
    assert inspected["issue_report"] == {"issue": "non-mainline failure"}
    assert listed["tasks"][0]["task_id"] == "task_new"
    assert gateway.submissions == []
    assert gateway.execution_calls == 0


def test_cancel_uses_public_boundary_or_reports_unsupported_explicitly() -> None:
    repository = FakeRepository()
    gateway = FakeSubmissionGateway(repository)

    supported = TaskControlAPI(gateway, repository).request_cancel("task_new")
    unsupported = TaskControlAPI(object(), repository).request_cancel("task_new")

    assert supported["ok"] is True
    assert supported["cancel_supported"] is True
    assert gateway.cancellations == ["task_new"]
    assert unsupported == {
        "ok": False,
        "task_id": "task_new",
        "cancel_supported": False,
        "reason": "Runtime cancellation boundary not implemented yet",
    }


def test_control_layer_has_no_direct_execution_or_tool_dependency() -> None:
    source = inspect.getsource(__import__("core.control.task_control_api", fromlist=["TaskControlAPI"]))
    legacy_source = inspect.getsource(__import__("core.control.control_api", fromlist=["ZeroControlAPI"]))

    assert "core.tools" not in source
    assert "StepExecutor" not in source
    assert ".tick(" not in source
    assert ".run_next(" not in source
    assert ".execute" not in source
    assert "_get_task_from_repo" not in legacy_source


def test_real_scheduler_submission_is_queued_without_execution(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    repository = TaskRepository(db_path=str(workspace / "tasks.json"))
    scheduler = Scheduler(task_repo=repository, workspace_dir=str(workspace))
    control = TaskControlAPI(scheduler, repository)

    submitted = control.submit_task(
        title="Local control submission",
        instruction="Summarize workspace/shared/input.txt into workspace/shared/output.txt",
        mode="controlled",
    )
    inspected = control.inspect_task(submitted["task_id"])

    assert submitted["ok"] is True
    assert submitted["status"] == "queued"
    assert inspected["status"] == "queued"
    assert inspected["last_result_summary"] == ""
    persisted = repository.get_task(submitted["task_id"])
    assert persisted["current_step_index"] == 0
    assert persisted["results"] == []
