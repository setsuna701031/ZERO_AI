from __future__ import annotations


def test_scheduler_operator_completion_adapter_marks_registry_complete(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    calls: list[tuple[str, str, str]] = []

    class FakeRegistry:
        def mark_complete(self, session_id: str, step_id: str) -> None:
            calls.append(("complete", session_id, step_id))

        def mark_failed(self, session_id: str, step_id: str) -> None:
            calls.append(("failed", session_id, step_id))

    monkeypatch.setattr(
        scheduler_module,
        "get_operator_registry_service",
        lambda: FakeRegistry(),
    )

    applied = scheduler_module._zero_scheduler_complete_operator(
        object(),
        {"id": "task-alpha", "operator_session_id": "session-alpha"},
        {"ok": True},
        outcome="complete",
    )

    assert applied is True
    assert calls == [("complete", "session-alpha", "task-alpha-complete")]


def test_scheduler_operator_completion_adapter_marks_registry_failed(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    calls: list[tuple[str, str, str]] = []

    class FakeRegistry:
        def mark_complete(self, session_id: str, step_id: str) -> None:
            calls.append(("complete", session_id, step_id))

        def mark_failed(self, session_id: str, step_id: str) -> None:
            calls.append(("failed", session_id, step_id))

    monkeypatch.setattr(
        scheduler_module,
        "get_operator_registry_service",
        lambda: FakeRegistry(),
    )

    applied = scheduler_module._zero_scheduler_complete_operator(
        object(),
        {"id": "task-alpha", "operator_session_id": "session-alpha"},
        {"ok": False},
        outcome="fail",
    )

    assert applied is True
    assert calls == [("failed", "session-alpha", "task-alpha-fail")]


def test_scheduler_operator_completion_adapter_fallback_completed_steps(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    class BrokenRegistry:
        def mark_complete(self, session_id: str, step_id: str) -> None:
            raise RuntimeError("registry unavailable")

        def mark_failed(self, session_id: str, step_id: str) -> None:
            raise RuntimeError("registry unavailable")

    class Session:
        def __init__(self) -> None:
            self.completed_steps: list[str] = []

    class Runtime:
        def __init__(self) -> None:
            self.sessions = {"session-alpha": Session()}

    class SchedulerLike:
        def __init__(self) -> None:
            self.operator_bridge = Runtime()
            self.step_executor = None

    scheduler = SchedulerLike()

    monkeypatch.setattr(
        scheduler_module,
        "get_operator_registry_service",
        lambda: BrokenRegistry(),
    )

    applied = scheduler_module._zero_scheduler_complete_operator(
        scheduler,
        {"id": "task-alpha", "operator_session_id": "session-alpha"},
        {"ok": True},
        outcome="complete",
    )

    assert applied is True
    assert scheduler.operator_bridge.sessions["session-alpha"].completed_steps == [
        "task-alpha-complete"
    ]
