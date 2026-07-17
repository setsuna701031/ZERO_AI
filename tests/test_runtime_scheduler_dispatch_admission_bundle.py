from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_scheduler_dispatch_admission import (
    RuntimeSchedulerDispatchAdmissionRecord,
    evaluate_scheduler_dispatch_admission,
)


def _authorized_wake_bridge_record() -> dict[str, object]:
    return {
        "scheduler_wake_bridge_authorized": True,
        "source_wake_admission_id": "wake-admission-001",
        "admitted_cursor": "cursor-B",
        "wake_bridge_reason": "wake_admission_authorized",
        "denial_reason": "",
        "scheduler_handler_called": False,
        "scheduler_dispatch_started": False,
        "executor_invoked": False,
        "runtime_state_mutated": False,
    }


def test_valid_wake_bridge_admits_dispatch_without_starting_dispatch() -> None:
    record = evaluate_scheduler_dispatch_admission(_authorized_wake_bridge_record())

    assert isinstance(record, RuntimeSchedulerDispatchAdmissionRecord)
    assert record.scheduler_dispatch_admitted is True
    assert record.source_wake_bridge_id == "wake-admission-001"
    assert record.admitted_cursor == "cursor-B"
    assert record.dispatch_reason == "wake_bridge_authorized"
    assert record.denial_reason == ""
    assert record.scheduler_dispatch_started is False
    assert record.executor_invoked is False
    assert record.runtime_state_mutated is False


def test_dispatch_mode_is_reported_without_creating_side_effects() -> None:
    record = evaluate_scheduler_dispatch_admission(
        _authorized_wake_bridge_record(),
        dispatch_mode="controlled",
    )

    assert record.scheduler_dispatch_admitted is True
    assert record.dispatch_reason == "wake_bridge_authorized:controlled"
    assert record.scheduler_dispatch_started is False
    assert record.executor_invoked is False
    assert record.runtime_state_mutated is False


def test_missing_wake_bridge_record_denies_deterministically() -> None:
    first = evaluate_scheduler_dispatch_admission(None)
    second = evaluate_scheduler_dispatch_admission(None)

    assert first == second
    assert first.scheduler_dispatch_admitted is False
    assert first.denial_reason == "missing_wake_bridge_record"
    assert first.scheduler_dispatch_started is False
    assert first.executor_invoked is False
    assert first.runtime_state_mutated is False


def test_rejected_wake_bridge_record_denies_deterministically() -> None:
    denied_bridge = _authorized_wake_bridge_record()
    denied_bridge["scheduler_wake_bridge_authorized"] = False
    denied_bridge["denial_reason"] = "wake_admission_not_authorized"

    first = evaluate_scheduler_dispatch_admission(denied_bridge)
    second = evaluate_scheduler_dispatch_admission(denied_bridge)

    assert first == second
    assert first.scheduler_dispatch_admitted is False
    assert first.source_wake_bridge_id == "wake-admission-001"
    assert first.admitted_cursor == "cursor-B"
    assert first.denial_reason == "wake_bridge_not_authorized"
    assert first.scheduler_dispatch_started is False
    assert first.executor_invoked is False


def test_missing_source_wake_bridge_id_denies() -> None:
    bridge = _authorized_wake_bridge_record()
    bridge["source_wake_admission_id"] = ""

    record = evaluate_scheduler_dispatch_admission(bridge)

    assert record.scheduler_dispatch_admitted is False
    assert record.denial_reason == "missing_source_wake_bridge_id"
    assert record.scheduler_dispatch_started is False


def test_missing_admitted_cursor_denies() -> None:
    bridge = _authorized_wake_bridge_record()
    bridge["admitted_cursor"] = ""

    record = evaluate_scheduler_dispatch_admission(bridge)

    assert record.scheduler_dispatch_admitted is False
    assert record.denial_reason == "missing_admitted_cursor"
    assert record.executor_invoked is False


def test_record_to_dict_is_stable() -> None:
    record = evaluate_scheduler_dispatch_admission(_authorized_wake_bridge_record())

    assert record.to_dict() == {
        "scheduler_dispatch_admitted": True,
        "source_wake_bridge_id": "wake-admission-001",
        "admitted_cursor": "cursor-B",
        "dispatch_reason": "wake_bridge_authorized",
        "denial_reason": "",
        "scheduler_dispatch_started": False,
        "executor_invoked": False,
        "runtime_state_mutated": False,
    }


def test_source_boundary_has_no_forbidden_runtime_surface_imports_or_calls() -> None:
    source = Path("core/runtime/runtime_scheduler_dispatch_admission.py").read_text(encoding="utf-8")
    lowered = source.lower()

    forbidden = [
        "import scheduler",
        "from scheduler",
        "import executor",
        "from executor",
        "task_runner",
        "agent_loop",
        "work_package_operator",
        "progress_memory",
        "run_one_step",
        ".run(",
    ]

    for token in forbidden:
        assert token not in lowered
