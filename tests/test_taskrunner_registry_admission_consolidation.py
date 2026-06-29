from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
TASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"


def test_taskrunner_registry_admission_consolidation_import_safe() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")
    ast.parse(source)

    import core.runtime.task_runner as module

    assert module is not None


def test_taskrunner_registry_admission_consolidation_single_helper_marker() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")

    assert source.count("ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_BEGIN") == 1
    assert source.count("ZERO_PACKAGE24_TASKRUNNER_REGISTRY_ADMISSION_CONSOLIDATION_END") == 1
    assert source.count("def _zero_taskrunner_registry_admit_aer_closure_v24") == 1


def test_taskrunner_registry_admission_consolidation_helper_calls_run_observer() -> None:
    import core.runtime.task_runner as module

    calls = []

    class FakeRegistry:
        def run_observer(self, **kwargs):
            calls.append(kwargs)
            return {"ok": True, "status": "admitted"}

    host = SimpleNamespace(runtime_route_registry=FakeRegistry())

    result = module._zero_taskrunner_registry_admit_aer_closure_v24(
        host,
        "execute_owned_step",
        {"step_id": "s1"},
    )

    assert result["ok"] is True
    assert calls
    assert calls[0]["event"] == "execute_owned_step"
    assert calls[0]["payload"]["step_id"] == "s1"


def test_taskrunner_registry_admission_consolidation_helper_supports_admit() -> None:
    import core.runtime.task_runner as module

    calls = []

    class FakeRegistry:
        def admit(self, event, payload):
            calls.append((event, payload))
            return {"ok": True, "admitted": True}

    host = SimpleNamespace(registry=FakeRegistry())

    result = module._zero_taskrunner_registry_admit_aer_closure_v24(
        host,
        "tick",
        {"tick": 1},
    )

    assert result["ok"] is True
    assert calls == [("tick", {"tick": 1})]


def test_taskrunner_registry_admission_consolidation_class_binding_if_taskrunner_exists() -> None:
    import core.runtime.task_runner as module

    cls = getattr(module, "TaskRunner", None)
    if isinstance(cls, type):
        assert hasattr(cls, "_aer_registry_admit")
        assert hasattr(cls, "_registry_admit_owned_step")
        assert hasattr(cls, "_registry_admit_tick")
