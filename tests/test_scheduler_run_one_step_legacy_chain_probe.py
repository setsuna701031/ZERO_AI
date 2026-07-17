from __future__ import annotations


def test_scheduler_run_one_step_final_wrapper_is_v16() -> None:
    from core.tasks.scheduler import Scheduler

    assert Scheduler.run_one_step.__name__ == "_zero_scheduler_run_one_step_v16"


def test_scheduler_run_one_step_v16_wraps_v12_chain() -> None:
    import core.tasks.scheduler as scheduler_module

    assert scheduler_module._zero_scheduler_base_run_one_step_v16.__name__ == (
        "_zero_scheduler_run_one_step_v8"
    )




def test_scheduler_operator_completion_pipeline_missing_completion_marks_failed(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    calls: list[tuple[str, str, str | None]] = []

    class FakeRegistry:
        def has_completion(self, session_id: str) -> bool:
            calls.append(("has_completion", session_id, None))
            return False

        def mark_failed(self, session_id: str, step_id: str) -> None:
            calls.append(("mark_failed", session_id, step_id))

        def mark_complete(self, session_id: str, step_id: str) -> None:
            calls.append(("mark_complete", session_id, step_id))

    monkeypatch.setattr(
        scheduler_module,
        "get_operator_registry_service",
        lambda: FakeRegistry(),
    )

    task = {
        "id": "task-alpha",
        "operator_session_id": "session-alpha",
    }
    result = {"ok": True}

    scheduler_module._zero_scheduler_run_operator_completion_pipeline(
        task,
        result,
        mode="missing_completion",
    )

    assert calls == [
        ("has_completion", "session-alpha", None),
        ("mark_failed", "session-alpha", "task-alpha-fail"),
    ]


def test_scheduler_operator_completion_pipeline_existing_completion_does_not_mark_failed(
    monkeypatch,
) -> None:
    import core.tasks.scheduler as scheduler_module

    calls: list[tuple[str, str, str | None]] = []

    class FakeRegistry:
        def has_completion(self, session_id: str) -> bool:
            calls.append(("has_completion", session_id, None))
            return True

        def mark_failed(self, session_id: str, step_id: str) -> None:
            calls.append(("mark_failed", session_id, step_id))

        def mark_complete(self, session_id: str, step_id: str) -> None:
            calls.append(("mark_complete", session_id, step_id))

    monkeypatch.setattr(
        scheduler_module,
        "get_operator_registry_service",
        lambda: FakeRegistry(),
    )

    task = {
        "id": "task-alpha",
        "operator_session_id": "session-alpha",
    }
    result = {"ok": True}

    scheduler_module._zero_scheduler_run_operator_completion_pipeline(
        task,
        result,
        mode="missing_completion",
    )

    assert calls == [
        ("has_completion", "session-alpha", None),
    ]