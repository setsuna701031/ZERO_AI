from __future__ import annotations

from types import SimpleNamespace


def _task() -> dict:
    return {
        "id": "task-explicit-authority-v5",
        "current_step_index": 0,
        "runtime_mode": "execute",
        "workspace_root": "E:\\zero_ai",
        "operator_session_id": "session-v5",
        "execution_authority": {
            "authority_validation": {"ok": True, "reason": "authority_metadata_valid"},
        },
        "steps": [
            {"id": "step-v5", "type": "write_file"},
        ],
    }


class FakeScheduler:
    def __init__(self, handler):
        self.step_executor = SimpleNamespace(handlers={"write_file": handler})


def test_v5_direct_handler_runs_first_supported_signature(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    calls = []

    def handler(step, task, context):
        calls.append({"step": step, "task": task, "context": context})
        return {"value": "direct-v5"}

    scheduler = FakeScheduler(handler)
    task = _task()
    original = {"ok": False, "error": "authority required"}

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v5",
        lambda self, *args, **kwargs: original,
    )

    result = scheduler_module._zero_scheduler_run_one_step_v5(
        scheduler,
        task=task,
        current_tick=12,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["compatibility_seal"] == "scheduler_explicit_authority_direct_handler_v5"
    assert result["value"] == "direct-v5"

    assert len(calls) == 1
    assert calls[0]["step"] is task["steps"][0]
    assert calls[0]["task"] is task
    assert calls[0]["context"] == {
        "current_tick": 12,
        "operator_session_id": "session-v5",
        "runtime_mode": "execute",
        "workspace_root": "E:\\zero_ai",
    }

    authority = task["execution_authority"]
    assert authority["execution_authority_granted"] is True
    assert task["steps"][0]["execution_authority"] is authority
    assert task["steps"][0]["runtime_execution_authority"] is authority
    assert task["steps"][0]["authority_validation"] == {
        "ok": True,
        "reason": "authority_metadata_valid",
    }


def test_v5_direct_handler_falls_back_across_supported_signatures(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    calls = []

    def handler(*args):
        calls.append(len(args))
        if len(args) != 1:
            raise TypeError("try next signature")
        step = args[0]
        return {"value": step["id"]}

    scheduler = FakeScheduler(handler)
    task = _task()

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v5",
        lambda self, *args, **kwargs: {"ok": False, "error": "authority required"},
    )

    result = scheduler_module._zero_scheduler_run_one_step_v5(scheduler, task=task)

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["compatibility_seal"] == "scheduler_explicit_authority_direct_handler_v5"
    assert result["value"] == "step-v5"
    assert calls == [3, 2, 3, 2, 1]


def test_v5_direct_handler_does_not_run_when_base_succeeds(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    def handler(*args):
        raise AssertionError("handler should not run")

    scheduler = FakeScheduler(handler)
    task = _task()
    original = {"ok": True, "status": "completed"}

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v5",
        lambda self, *args, **kwargs: original,
    )

    result = scheduler_module._zero_scheduler_run_one_step_v5(scheduler, task=task)

    assert result is original


def test_v5_direct_handler_does_not_run_without_authority(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    def handler(*args):
        raise AssertionError("handler should not run")

    scheduler = FakeScheduler(handler)
    task = _task()
    task.pop("execution_authority")
    original = {"ok": False, "error": "authority required"}

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v5",
        lambda self, *args, **kwargs: original,
    )

    result = scheduler_module._zero_scheduler_run_one_step_v5(scheduler, task=task)

    assert result is original


def test_v5_direct_handler_returns_original_when_no_handler(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    scheduler = SimpleNamespace(step_executor=SimpleNamespace(handlers={}))
    task = _task()
    original = {"ok": False, "error": "authority required"}

    monkeypatch.setattr(
        scheduler_module,
        "_zero_scheduler_base_run_one_step_v5",
        lambda self, *args, **kwargs: original,
    )

    result = scheduler_module._zero_scheduler_run_one_step_v5(scheduler, task=task)

    assert result is original