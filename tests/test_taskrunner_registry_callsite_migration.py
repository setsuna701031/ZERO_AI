from __future__ import annotations

import ast
from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




ROOT = Path(__file__).resolve().parents[1]
TASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"


def test_taskrunner_registry_callsite_migration_import_safe() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")
    ast.parse(source)

    import core.runtime.task_runner as module

    assert module is not None


def test_taskrunner_registry_callsite_migration_marker_once() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")

    assert source.count("ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_BEGIN") == 1
    assert source.count("ZERO_PACKAGE26_TASKRUNNER_REGISTRY_CALLSITE_MIGRATION_END") == 1


def test_taskrunner_registry_callsite_migration_helpers_exist() -> None:
    import core.runtime.task_runner as module

    assert hasattr(module, "_zero_taskrunner_registry_callsite_payload_v26")
    assert hasattr(module, "_zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26")
    assert hasattr(module, "_zero_taskrunner_registry_callsite_wrap_tick_v26")


def test_taskrunner_registry_callsite_migration_payload_extracts_step_id() -> None:
    import core.runtime.task_runner as module

    payload = module._zero_taskrunner_registry_callsite_payload_v26(
        "execute_owned_step",
        ({"step_id": "s26", "type": "noop"},),
        {"current_tick": 9},
    )

    assert payload["event"] == "execute_owned_step"
    assert payload["step_id"] == "s26"
    assert payload["current_tick"] == 9


def test_taskrunner_registry_callsite_migration_class_binding_if_taskrunner_exists() -> None:
    import core.runtime.task_runner as module

    cls = getattr(module, "TaskRunner", None)
    if isinstance(cls, type):
        assert getattr(cls, "_zero_package26_registry_callsite_migration_installed", False) is True


def test_taskrunner_registry_callsite_migration_wrapper_calls_unified_helper() -> None:
    import core.runtime.task_runner as module

    calls = []

    class Host:
        def _aer_registry_admit(self, event, payload=None):
            calls.append((event, payload))
            return {"ok": True, "status": "admitted"}

    def base(self, step, **kwargs):
        return {"ok": True, "step": step, "kwargs": kwargs}

    wrapped = module._zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26(base)
    result = wrapped(Host(), {"step_id": "owned-26"}, current_tick=26)

    assert result["ok"] is True
    assert calls
    assert calls[0][0] == "execute_owned_step"
    assert calls[0][1]["step_id"] == "owned-26"


def test_taskrunner_registry_callsite_migration_tick_wrapper_calls_unified_helper() -> None:
    import core.runtime.task_runner as module

    calls = []

    class Host:
        def _aer_registry_admit(self, event, payload=None):
            calls.append((event, payload))
            return {"ok": True, "status": "admitted"}

    def base(self, **kwargs):
        return {"ok": True, "kwargs": kwargs}

    wrapped = module._zero_taskrunner_registry_callsite_wrap_tick_v26(base)
    result = wrapped(Host(), current_tick=27)

    assert result["ok"] is True
    assert calls
    assert calls[0][0] == "tick"
    assert calls[0][1]["current_tick"] == 27
