from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_scheduler_wake_bridge import evaluate_scheduler_wake_bridge


ROOT = Path(__file__).resolve().parents[1]


def _wake_admission(**overrides):
    record = {
        "schema": "zero.runtime.scheduler_wake_admission.v1",
        "wake_admission_record_id": "runtime-wake-admission::session-1545::step-2",
        "runtime_id": "limited-runtime-session::birth-1209",
        "scheduler_wake_authorized": True,
        "source_tick_request_id": "runtime-tick-request::session-1545::step-2",
        "admitted_cursor": {
            "cursor_id": "runtime-cursor::session-1545::step-2",
            "step_index": 2,
            "state": "CONTINUE",
        },
        "wake_reason": "tick_request_authorized",
        "denial_reason": "none",
        "scheduler_invoked": False,
        "executor_invoked": False,
        "runtime_state_mutated": False,
    }
    record.update(overrides)
    return record


def test_1545_valid_wake_admission_without_handler_authorizes_bridge():
    record = evaluate_scheduler_wake_bridge(_wake_admission())

    assert record["scheduler_wake_bridge_authorized"] is True
    assert record["bridge_authorized"] is True
    assert record["source_wake_admission_id"] == (
        "runtime-wake-admission::session-1545::step-2"
    )
    assert record["admitted_cursor"] == _wake_admission()["admitted_cursor"]
    assert record["wake_bridge_reason"] == "wake_admission_authorized"
    assert record["denial_reason"] == "none"
    assert record["scheduler_handler_called"] is False
    assert record["scheduler_dispatch_started"] is False
    assert record["executor_invoked"] is False
    assert record["runtime_state_mutated"] is False


def test_1546_valid_wake_admission_with_handler_calls_once_with_data_only():
    calls = []

    def handler(payload):
        calls.append(payload)

    record = evaluate_scheduler_wake_bridge(
        _wake_admission(),
        scheduler_wake_handler=handler,
    )

    assert record["scheduler_wake_bridge_authorized"] is True
    assert record["scheduler_handler_called"] is True
    assert record["scheduler_dispatch_started"] is False
    assert record["executor_invoked"] is False
    assert len(calls) == 1
    assert calls[0] == {
        "admitted_cursor": _wake_admission()["admitted_cursor"],
        "source_wake_admission_id": (
            "runtime-wake-admission::session-1545::step-2"
        ),
    }


def test_1547_missing_wake_admission_denies():
    record = evaluate_scheduler_wake_bridge(None)

    assert record["scheduler_wake_bridge_authorized"] is False
    assert record["source_wake_admission_id"] is None
    assert record["admitted_cursor"] == {}
    assert record["wake_bridge_reason"] == "wake_bridge_denied"
    assert record["denial_reason"] == "missing_wake_admission_record"
    assert record["scheduler_handler_called"] is False
    assert record["scheduler_dispatch_started"] is False
    assert record["executor_invoked"] is False


def test_1548_wake_admission_not_authorized_denies():
    record = evaluate_scheduler_wake_bridge(
        _wake_admission(
            scheduler_wake_authorized=False,
            admitted_cursor={},
            denial_reason="tick_request_rejected",
        )
    )

    assert record["scheduler_wake_bridge_authorized"] is False
    assert record["admitted_cursor"] == {}
    assert record["denial_reason"] == "tick_request_rejected"


def test_1549_handler_exception_produces_deterministic_denial():
    def handler(_payload):
        raise ValueError("runtime-specific detail")

    first = evaluate_scheduler_wake_bridge(
        _wake_admission(),
        scheduler_wake_handler=handler,
    )
    second = evaluate_scheduler_wake_bridge(
        _wake_admission(),
        scheduler_wake_handler=handler,
    )

    assert first == second
    assert first["scheduler_wake_bridge_authorized"] is False
    assert first["scheduler_handler_called"] is True
    assert first["denial_reason"] == "handler_exception:ValueError"
    assert first["scheduler_dispatch_started"] is False
    assert first["executor_invoked"] is False


def test_1550_boundary_source_does_not_import_or_call_forbidden_surfaces():
    source = (ROOT / "core/runtime/runtime_scheduler_wake_bridge.py").read_text()
    lowered = source.lower()

    assert "executor" not in lowered
    assert "task_runner" not in lowered
    assert "agent_loop" not in lowered
    assert "work_package_operator" not in lowered
    assert "progress_memory" not in lowered
    assert "scheduler.run" not in lowered
    assert "run_one_step" not in lowered


def test_1551_bridge_does_not_dispatch_execute_or_mutate():
    record = evaluate_scheduler_wake_bridge(_wake_admission())

    assert record["scheduler_dispatch_started"] is False
    assert record["executor_invoked"] is False
    assert record["task_executed"] is False
    assert record["runtime_state_mutated"] is False
    assert record["runtime_queue_mutated"] is False
    assert record["cursor_advanced_here"] is False
    assert record["progress_state_modified"] is False


def test_1552_inputs_are_not_mutated():
    admission = _wake_admission()
    before = _wake_admission()

    evaluate_scheduler_wake_bridge(admission)

    assert admission == before
