from __future__ import annotations

import core.tasks.scheduler as scheduler_module
from core.tasks.scheduler import Scheduler


class AllowGuard:
    def check_step(self, step, task_dir):
        return {"ok": True}


def test_scheduler_llm_step_returns_gateway_runtime_payload(monkeypatch, tmp_path):
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.tasks_root = str(tmp_path / "tasks")
    scheduler.execution_guard = AllowGuard()

    monkeypatch.setattr(
        scheduler_module,
        "prepare_simple_step_guard",
        lambda scheduler, step, step_type, step_scope: (dict(step), dict(step), step_scope),
    )

    monkeypatch.setattr(scheduler_module, "execute_simple_basic_step", lambda **kwargs: None)

    def fake_llm_step(**kwargs):
        return {
            "ok": True,
            "action": "llm",
            "text": "generated answer",
            "step_type": kwargs["step_type"],
        }

    monkeypatch.setattr(scheduler_module, "execute_llm_step", fake_llm_step)
    monkeypatch.setattr(scheduler_module, "execute_command_like_step", lambda **kwargs: None)

    result = scheduler._execute_simple_step(
        task={"task_id": "llm_gateway_task"},
        step={
            "type": "llm",
            "description": "generate answer",
        },
    )

    assert result["ok"] is True
    assert result["action"] == "llm"
    assert result["text"] == "generated answer"
    assert result["scheduler_execution_gateway_returned"] is True
    assert result["scheduler_execution_gateway_source"] == "scheduler_llm_step"
    assert result["scheduler_execution_gateway_used"] is True
    assert result["scheduler_execution_legacy_fallback_used"] is False
    assert result["scheduler_execution_runtime_ok"] is True
    assert result["scheduler_execution_gateway_layer"] == "scheduler_execution_gateway.v1"


def test_scheduler_llm_step_falls_back_to_legacy_when_gateway_raises(monkeypatch, tmp_path):
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.tasks_root = str(tmp_path / "tasks")
    scheduler.execution_guard = AllowGuard()

    monkeypatch.setattr(
        scheduler_module,
        "prepare_simple_step_guard",
        lambda scheduler, step, step_type, step_scope: (dict(step), dict(step), step_scope),
    )

    monkeypatch.setattr(scheduler_module, "execute_simple_basic_step", lambda **kwargs: None)

    legacy_result = {
        "ok": True,
        "action": "llm",
        "text": "legacy llm answer",
    }

    monkeypatch.setattr(scheduler_module, "execute_llm_step", lambda **kwargs: dict(legacy_result))
    monkeypatch.setattr(scheduler_module, "execute_command_like_step", lambda **kwargs: None)
    monkeypatch.setattr(
        scheduler_module,
        "run_scheduler_step_execution_gateway",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("gateway failed")),
    )

    result = scheduler._execute_simple_step(
        task={"task_id": "llm_gateway_fallback_task"},
        step={
            "type": "llm",
            "description": "generate answer",
        },
    )

    assert result == legacy_result
