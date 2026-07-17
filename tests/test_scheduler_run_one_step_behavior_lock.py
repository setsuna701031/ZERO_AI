from __future__ import annotations

from core.runtime.operator_registry_service import get_operator_registry_service
from core.tasks.scheduler import Scheduler


def test_scheduler_run_one_step_endpoint_is_current_v16() -> None:
    assert Scheduler.run_one_step.__name__ == "_zero_scheduler_run_one_step_v16"


def test_scheduler_run_one_step_preserves_success_when_completion_exists() -> None:
    scheduler = Scheduler.__new__(Scheduler)

    session_id = "behavior-lock-session"
    task = {
        "id": "behavior-lock-task",
        "operator_session_id": session_id,
    }

    registry = get_operator_registry_service()
    registry.mark_complete(session_id, "behavior-lock-task-complete")

    def base_run_one_step(self, *args, **kwargs):
        return {"ok": True, "status": "completed"}

    import core.tasks.scheduler as scheduler_module

    original_base = scheduler_module._zero_scheduler_base_run_one_step_v16
    try:
        scheduler_module._zero_scheduler_base_run_one_step_v16 = base_run_one_step
        result = scheduler.run_one_step(task=task, current_tick=0)
    finally:
        scheduler_module._zero_scheduler_base_run_one_step_v16 = original_base

    assert result == {"ok": True, "status": "completed"}
    assert registry.has_completion(session_id) is True