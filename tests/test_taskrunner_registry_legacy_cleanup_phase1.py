from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"
REPORT = ROOT / "taskrunner_registry_legacy_cleanup_phase1_report.txt"


def test_taskrunner_registry_legacy_cleanup_phase1_import_safe() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")
    ast.parse(source)

    import core.runtime.task_runner as module

    assert module is not None


def test_taskrunner_registry_legacy_cleanup_phase1_marker_once() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")

    assert source.count("ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_BEGIN") == 1
    assert source.count("ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_END") == 1


def test_taskrunner_registry_legacy_cleanup_phase1_report_exists() -> None:
    assert REPORT.exists()


def test_taskrunner_registry_legacy_cleanup_phase1_report_has_required_sections() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "TaskRunner Registry Legacy Cleanup Phase1 Report" in text
    assert "Cleanup Guard" in text
    assert "Remaining direct registry calls" in text
    assert "Preserved specialized paths" in text
    assert "Non-mainline issue reporting" in text


def test_taskrunner_registry_legacy_cleanup_phase1_guard_rejects_bypass_when_helper_missing() -> None:
    import core.runtime.task_runner as module

    class Host:
        pass

    result = module._zero_taskrunner_registry_legacy_cleanup_guard_v28(
        Host(),
        "execute_owned_step",
        {"step_id": "s28"},
    )

    assert result["ok"] is False
    assert result["reason"] == "aer_registry_admit_unavailable"


def test_taskrunner_registry_legacy_cleanup_phase1_guard_uses_helper() -> None:
    import core.runtime.task_runner as module

    calls = []

    class Host:
        def _aer_registry_admit(self, event, payload=None):
            calls.append((event, payload))
            return {"ok": True, "status": "admitted"}

    result = module._zero_taskrunner_registry_legacy_cleanup_guard_v28(
        Host(),
        "tick",
        {"current_tick": 28},
    )

    assert result["ok"] is True
    assert calls == [("tick", {"current_tick": 28})]


def test_taskrunner_registry_legacy_cleanup_phase1_execute_tick_wrappers_still_installed() -> None:
    import core.runtime.task_runner as module

    assert hasattr(module, "_zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26")
    assert hasattr(module, "_zero_taskrunner_registry_callsite_wrap_tick_v26")
    assert hasattr(module, "_zero_taskrunner_registry_legacy_cleanup_guard_v28")


def test_taskrunner_registry_legacy_cleanup_phase1_taskrunner_binding_if_class_exists() -> None:
    import core.runtime.task_runner as module

    cls = getattr(module, "TaskRunner", None)
    if isinstance(cls, type):
        assert getattr(cls, "_zero_package28_registry_legacy_cleanup_phase1_installed", False) is True
