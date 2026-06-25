from __future__ import annotations


class FakeScheduler:
    def __init__(self):
        self.calls = []

    def _run_step_via_task_runner(self, *, task, step, context):
        self.calls.append({"task": task, "step": step, "context": context})
        return {"ok": True, "status": "completed", "value": "fallback"}


def _task() -> dict:
    return {
        "id": "task-runtime-gate",
        "current_step_index": 0,
        "execution_authority": {
            "execution_authority_granted": True,
            "authority_validation": {"ok": True, "reason": "authority_metadata_valid"},
        },
        "steps": [
            {"id": "step-a", "type": "write_file"},
        ],
    }


def test_v1_runtime_gate_fallback_runs_on_empty_soft_gate(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    scheduler = FakeScheduler()
    task = _task()

    monkeypatch.setattr(
        scheduler_module,
        "_zero_prev_scheduler_run_one_step_v1",
        lambda self, *args, **kwargs: {"ok": False, "error": "authority required"},
    )

    result = scheduler_module._zero_scheduler_run_one_step_v1(scheduler, task=task, current_tick=7)

    assert result["ok"] is True
    assert result["compatibility_seal"] == "scheduler_runtime_gate_fallback_v1"
    assert scheduler.calls[0]["task"] is task
    assert scheduler.calls[0]["step"] == task["steps"][0]
    assert scheduler.calls[0]["context"]["current_tick"] == 7


def test_v2_runtime_gate_fallback_requires_dispatch_authority(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    scheduler = FakeScheduler()
    task = _task()

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v2",
        lambda self, *args, **kwargs: {
            "ok": False,
            "error": "runtime_dispatcher_live_capability_required",
        },
    )

    result = scheduler_module._zero_scheduler_run_one_step_v2(scheduler, task=task, current_tick=8)

    assert result["ok"] is True
    assert result["compatibility_seal"] == "scheduler_runtime_gate_fallback_v2"
    assert scheduler.calls[0]["context"]["current_tick"] == 8


def test_v2_runtime_gate_fallback_does_not_run_without_authority(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    scheduler = FakeScheduler()
    task = _task()
    task.pop("execution_authority")

    original = {
        "ok": False,
        "error": "runtime_dispatcher_live_capability_required",
    }

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v2",
        lambda self, *args, **kwargs: original,
    )

    result = scheduler_module._zero_scheduler_run_one_step_v2(scheduler, task=task)

    assert result is original
    assert scheduler.calls == []


def test_v3_runtime_gate_fallback_requires_granted_execution_authority(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    scheduler = FakeScheduler()
    task = _task()

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v3",
        lambda self, *args, **kwargs: {
            "ok": False,
            "error": "runtime_execution_capability_not_validated",
        },
    )

    result = scheduler_module._zero_scheduler_run_one_step_v3(scheduler, task=task, current_tick=9)

    assert result["ok"] is True
    assert result["compatibility_seal"] == "scheduler_runtime_gate_fallback_v3"
    assert scheduler.calls[0]["context"]["current_tick"] == 9


def test_v3_runtime_gate_fallback_does_not_run_for_non_soft_success(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    scheduler = FakeScheduler()
    task = _task()
    original = {"ok": True, "status": "completed"}

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v3",
        lambda self, *args, **kwargs: original,
    )

    result = scheduler_module._zero_scheduler_run_one_step_v3(scheduler, task=task)

    assert result is original
    assert scheduler.calls == []