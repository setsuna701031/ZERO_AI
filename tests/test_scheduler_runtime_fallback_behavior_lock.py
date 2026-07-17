from __future__ import annotations

import core.tasks.scheduler as scheduler_module
from core.tasks.scheduler import Scheduler


def test_scheduler_runtime_fallback_v5_still_uses_current_base_chain() -> None:
    assert scheduler_module._zero_scheduler_base_run_one_step_v5.__name__ == "_zero_scheduler_run_one_step_v4"


def test_scheduler_runtime_fallback_v1_to_v5_wrappers_are_present() -> None:
    for version in range(1, 6):
        name = f"_zero_scheduler_run_one_step_v{version}"
        assert hasattr(scheduler_module, name)
        assert callable(getattr(scheduler_module, name))


def test_scheduler_runtime_fallback_v5_returns_base_success_without_fallback() -> None:
    scheduler = Scheduler.__new__(Scheduler)

    def base_run_one_step(self, *args, **kwargs):
        return {"ok": True, "status": "completed", "source": "base"}

    original_base = scheduler_module._zero_scheduler_base_run_one_step_v5
    try:
        scheduler_module._zero_scheduler_base_run_one_step_v5 = base_run_one_step
        result = scheduler_module._zero_scheduler_run_one_step_v5(
            scheduler,
            task={"id": "fallback-lock-task"},
            current_tick=0,
        )
    finally:
        scheduler_module._zero_scheduler_base_run_one_step_v5 = original_base

    assert result == {"ok": True, "status": "completed", "source": "base"}