from __future__ import annotations

import builtins
from pathlib import Path

from core.runtime.operator_registry_service import (

    OPERATOR_COMPLETION_REGISTRY_KEY,
    OPERATOR_FAILURE_REGISTRY_KEY,
    get_operator_registry_service,
)
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_fast]



def _clear_legacy_registries() -> None:
    for key in (OPERATOR_COMPLETION_REGISTRY_KEY, OPERATOR_FAILURE_REGISTRY_KEY):
        if hasattr(builtins, key):
            delattr(builtins, key)


def test_operator_registry_service_preserves_legacy_readback_shape() -> None:
    _clear_legacy_registries()
    registry = get_operator_registry_service()

    registry.mark_complete("session-a", "task-1-complete")
    registry.mark_failed("session-a", "task-2-fail")

    assert registry.completed_steps("session-a") == {"task-1-complete"}
    assert registry.failed_step("session-a") == "task-2-fail"
    assert getattr(builtins, OPERATOR_COMPLETION_REGISTRY_KEY)["session-a"] == {"task-1-complete"}
    assert getattr(builtins, OPERATOR_FAILURE_REGISTRY_KEY)["session-a"] == "task-2-fail"


def test_operator_registry_completion_clears_stale_failure_for_same_session() -> None:
    _clear_legacy_registries()
    registry = get_operator_registry_service()

    registry.mark_failed("session-a", "task-1-fail")
    assert registry.failed_step("session-a") == "task-1-fail"

    registry.mark_complete("session-a", "task-1-complete")
    assert registry.completed_steps("session-a") == {"task-1-complete"}
    assert registry.failed_step("session-a") is None


def test_operator_registry_service_keeps_sessions_isolated() -> None:
    _clear_legacy_registries()
    registry = get_operator_registry_service()

    registry.mark_complete("session-a", "a-complete")
    registry.mark_failed("session-b", "b-fail")

    assert registry.completed_steps("session-a") == {"a-complete"}
    assert registry.completed_steps("session-b") == set()
    assert registry.failed_step("session-a") is None
    assert registry.failed_step("session-b") == "b-fail"


def test_operator_registry_callers_do_not_reference_legacy_builtins_directly() -> None:
    root = Path(__file__).resolve().parents[1]
    target_files = [
        root / "core" / "tasks" / "scheduler.py",
        root / "core" / "runtime" / "task_runner.py",
        root / "core" / "runtime" / "persistent_operator.py",
        root / "core" / "runtime" / "operator_integration_bridge.py",
        root / "core" / "runtime" / "runtime_replay_engine.py",
        root / "core" / "runtime" / "runtime_recovery_executor.py",
    ]
    forbidden = (OPERATOR_COMPLETION_REGISTRY_KEY, OPERATOR_FAILURE_REGISTRY_KEY)

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                offenders.append(f"{path.relative_to(root)} contains {marker}")

    assert offenders == []
