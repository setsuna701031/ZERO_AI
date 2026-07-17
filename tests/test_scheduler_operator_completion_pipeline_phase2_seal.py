from __future__ import annotations
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




class _Registry:
    def __init__(self, has_completion: bool = False) -> None:
        self.has_completion_value = has_completion
        self.completed = []
        self.failed = []

    def mark_complete(self, session_id, completion_id):
        self.completed.append((session_id, completion_id))

    def mark_failed(self, session_id, failure_id):
        self.failed.append((session_id, failure_id))

    def has_completion(self, session_id):
        return self.has_completion_value


def test_operator_pipeline_marks_complete_then_preserves_completion(monkeypatch):
    import core.tasks.scheduler as scheduler_module

    registry = _Registry(has_completion=True)
    monkeypatch.setattr(scheduler_module, "get_operator_registry_service", lambda: registry)

    task = {
        "id": "task-a",
        "operator_session_id": "session-a",
        "steps": [{"type": "normal"}],
        "current_step_index": 0,
    }

    scheduler_module._zero_scheduler_mark_operator_complete_if_ok(task, {"ok": True})
    scheduler_module._zero_scheduler_mark_failed_if_ok_without_completion(task, {"ok": True})

    assert registry.completed == [("session-a", "task-a-complete")]
    assert registry.failed == []


def test_operator_pipeline_marks_failed_when_ok_without_completion(monkeypatch):
    import core.tasks.scheduler as scheduler_module

    registry = _Registry(has_completion=False)
    monkeypatch.setattr(scheduler_module, "get_operator_registry_service", lambda: registry)

    task = {
        "id": "task-b",
        "operator_session_id": "session-b",
        "steps": [{"type": "normal"}],
        "current_step_index": 0,
    }

    scheduler_module._zero_scheduler_mark_failed_if_ok_without_completion(task, {"ok": True})

    assert registry.failed == [("session-b", "task-b-fail")]


def test_operator_pipeline_marks_failed_step(monkeypatch):
    import core.tasks.scheduler as scheduler_module

    registry = _Registry(has_completion=False)
    monkeypatch.setattr(scheduler_module, "get_operator_registry_service", lambda: registry)

    task = {
        "id": "task-c",
        "operator_session_id": "session-c",
        "steps": [{"type": "failure_handler"}],
        "current_step_index": 0,
    }

    scheduler_module._zero_scheduler_mark_failed_step_if_needed(task, {"ok": True})

    assert registry.failed == [("session-c", "task-c-fail")]


def test_operator_pipeline_ignores_missing_session(monkeypatch):
    import core.tasks.scheduler as scheduler_module

    registry = _Registry(has_completion=False)
    monkeypatch.setattr(scheduler_module, "get_operator_registry_service", lambda: registry)

    task = {
        "id": "task-d",
        "steps": [{"type": "failure_handler"}],
        "current_step_index": 0,
    }

    scheduler_module._zero_scheduler_mark_operator_complete_if_ok(task, {"ok": True})
    scheduler_module._zero_scheduler_mark_operator_complete_or_failed(task, {"ok": False})
    scheduler_module._zero_scheduler_mark_failed_step_if_needed(task, {"ok": True})
    scheduler_module._zero_scheduler_mark_failed_if_ok_without_completion(task, {"ok": True})

    assert registry.completed == []
    assert registry.failed == []