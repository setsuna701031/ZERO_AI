from __future__ import annotations


class FakeScheduler:
    def __init__(self):
        self.calls = []

    def _run_step_via_task_runner(self, *, task, step, context):
        self.calls.append({"task": task, "step": step, "context": context})
        return {"value": "fallback-v4"}


def _task() -> dict:
    return {
        "id": "task-explicit-authority-v4",
        "current_step_index": 0,
        "runtime_mode": "execute",
        "workspace_root": "E:\\zero_ai",
        "operator_session_id": "session-v4",
        "execution_authority": {
            "execution_authority_granted": True,
            "authority_validation": {"ok": True, "reason": "authority_metadata_valid"},
        },
        "steps": [
            {"id": "step-v4", "type": "write_file"},
        ],
    }


def test_v4_explicit_authority_fallback_attaches_authority_and_runs(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    scheduler = FakeScheduler()
    task = _task()
    original = {"ok": False, "error": "authority required"}

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v4",
        lambda self, *args, **kwargs: original,
    )

    result = scheduler_module._zero_scheduler_run_one_step_v4(
        scheduler,
        task=task,
        current_tick=11,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["compatibility_seal"] == "scheduler_explicit_authority_fallback_v4"
    assert result["value"] == "fallback-v4"

    assert len(scheduler.calls) == 1
    call = scheduler.calls[0]
    assert call["task"] is task
    assert call["step"] is task["steps"][0]
    assert call["step"]["execution_authority"] is task["execution_authority"]
    assert call["step"]["runtime_execution_authority"] is task["execution_authority"]
    assert call["step"]["authority_validation"] == {
        "ok": True,
        "reason": "authority_metadata_valid",
    }
    assert call["context"] == {
        "current_tick": 11,
        "runtime_mode": "execute",
        "workspace_root": "E:\\zero_ai",
        "operator_session_id": "session-v4",
    }


def test_v4_explicit_authority_fallback_does_not_run_without_granted_authority(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    scheduler = FakeScheduler()
    task = _task()
    task["execution_authority"]["execution_authority_granted"] = False
    original = {"ok": False, "error": "authority required"}

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v4",
        lambda self, *args, **kwargs: original,
    )

    result = scheduler_module._zero_scheduler_run_one_step_v4(scheduler, task=task)

    assert result is original
    assert scheduler.calls == []


def test_v4_explicit_authority_fallback_does_not_run_when_base_succeeds(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    scheduler = FakeScheduler()
    task = _task()
    original = {"ok": True, "status": "completed"}

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v4",
        lambda self, *args, **kwargs: original,
    )

    result = scheduler_module._zero_scheduler_run_one_step_v4(scheduler, task=task)

    assert result is original
    assert scheduler.calls == []