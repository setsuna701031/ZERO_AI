from __future__ import annotations

from types import SimpleNamespace

from core.tasks.scheduler import Scheduler


def test_scheduler_dispatch_compatibility_wrappers_exist() -> None:
    scheduler = Scheduler.__new__(Scheduler)

    assert callable(getattr(scheduler, "_handle_dispatch_result"))
    assert callable(getattr(scheduler, "_handle_missing_repo_task"))
    assert callable(getattr(scheduler, "_handle_run_one_step_exception"))
    assert callable(getattr(scheduler, "_finalize_dispatched_task"))


def test_scheduler_handle_dispatch_result_wrapper_preserves_idle_result() -> None:
    scheduler = Scheduler.__new__(Scheduler)
    dispatch_result = SimpleNamespace(dispatched=False, task=None)

    assert scheduler._handle_dispatch_result(dispatch_result, current_tick=1) is None
