from __future__ import annotations


def test_scheduler_operator_failed_chain_v15_marks_failure_step(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module
    from core.tasks.scheduler import Scheduler

    calls = []

    class FakeRegistry:
        def mark_failed(self, session_id, step_id):
            calls.append((session_id, step_id))

    monkeypatch.setattr(
        scheduler_module,
        "get_operator_registry_service",
        lambda: FakeRegistry(),
    )
    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v15",
        lambda self, *args, **kwargs: {"ok": False},
    )

    scheduler = Scheduler.__new__(Scheduler)
    task = {
        "id": "task-a",
        "operator_session_id": "session-a",
        "current_step_index": 0,
        "steps": [{"id": "step-a", "type": "failure"}],
    }

    result = scheduler_module._zero_scheduler_run_one_step_v15(scheduler, task=task)

    assert result == {"ok": False}
    assert calls == [("session-a", "task-a-fail")]


def test_scheduler_operator_failed_chain_v16_marks_missing_completion(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module
    from core.tasks.scheduler import Scheduler

    calls = []

    class FakeRegistry:
        def has_completion(self, session_id):
            return False

        def mark_failed(self, session_id, step_id):
            calls.append((session_id, step_id))

    monkeypatch.setattr(
        scheduler_module,
        "get_operator_registry_service",
        lambda: FakeRegistry(),
    )
    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v16",
        lambda self, *args, **kwargs: {"ok": True},
    )

    scheduler = Scheduler.__new__(Scheduler)
    task = {
        "id": "task-b",
        "operator_session_id": "session-b",
    }

    result = scheduler_module._zero_scheduler_run_one_step_v16(scheduler, task=task)

    assert result == {"ok": True}
    assert calls == [("session-b", "task-b-fail")]


def test_scheduler_operator_failed_chain_v16_does_not_mark_when_completion_exists(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module
    from core.tasks.scheduler import Scheduler

    calls = []

    class FakeRegistry:
        def has_completion(self, session_id):
            return True

        def mark_failed(self, session_id, step_id):
            calls.append((session_id, step_id))

    monkeypatch.setattr(
        scheduler_module,
        "get_operator_registry_service",
        lambda: FakeRegistry(),
    )
    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v16",
        lambda self, *args, **kwargs: {"ok": True},
    )

    scheduler = Scheduler.__new__(Scheduler)
    task = {
        "id": "task-c",
        "operator_session_id": "session-c",
    }

    result = scheduler_module._zero_scheduler_run_one_step_v16(scheduler, task=task)

    assert result == {"ok": True}
    assert calls == []
