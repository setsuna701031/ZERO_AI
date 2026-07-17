from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_scheduler_wake_admission import (
    evaluate_scheduler_wake_admission,
)


ROOT = Path(__file__).resolve().parents[1]


def _tick_request(**overrides):
    record = {
        "schema": "zero.runtime.tick_request_gate.v1",
        "tick_request_record_id": "runtime-tick-request::session-1537::step-2",
        "runtime_id": "limited-runtime-session::birth-1209",
        "tick_request_authorized": True,
        "source_cursor_advance_id": "runtime-cursor-advance::session-1537::step-2",
        "current_cursor": {
            "cursor_id": "runtime-cursor::session-1537::step-2",
            "step_index": 2,
            "state": "CONTINUE",
        },
        "requested_tick_reason": "cursor_advance_authorized",
        "denial_reason": "none",
        "scheduler_invoked": False,
        "executor_invoked": False,
        "runtime_state_mutated": False,
    }
    record.update(overrides)
    return record


def test_1537_valid_tick_request_authorizes_wake_admission():
    record = evaluate_scheduler_wake_admission(
        _tick_request(),
        scheduler_mode="limited",
    )

    assert record["scheduler_wake_authorized"] is True
    assert record["source_tick_request_id"] == "runtime-tick-request::session-1537::step-2"
    assert record["admitted_cursor"] == _tick_request()["current_cursor"]
    assert record["wake_reason"] == "tick_request_authorized"
    assert record["denial_reason"] == "none"
    assert record["scheduler_invoked"] is False
    assert record["executor_invoked"] is False
    assert record["runtime_state_mutated"] is False


def test_1538_missing_tick_request_record_denies():
    record = evaluate_scheduler_wake_admission(None)

    assert record["scheduler_wake_authorized"] is False
    assert record["source_tick_request_id"] is None
    assert record["admitted_cursor"] == {}
    assert record["wake_reason"] == "wake_denied"
    assert record["denial_reason"] == "missing_tick_request_record"
    assert record["scheduler_invoked"] is False
    assert record["executor_invoked"] is False
    assert record["runtime_state_mutated"] is False


def test_1539_tick_request_not_authorized_denies():
    record = evaluate_scheduler_wake_admission(
        _tick_request(
            tick_request_authorized=False,
            current_cursor={},
            denial_reason="cursor_advance_rejected",
        )
    )

    assert record["scheduler_wake_authorized"] is False
    assert record["admitted_cursor"] == {}
    assert record["denial_reason"] == "cursor_advance_rejected"


def test_1540_denied_output_is_deterministic():
    tick = _tick_request(
        tick_request_authorized=False,
        current_cursor={},
        denial_reason="missing_cursor_advance_record",
    )

    first = evaluate_scheduler_wake_admission(tick, scheduler_mode="limited")
    second = evaluate_scheduler_wake_admission(tick, scheduler_mode="limited")

    assert first == second
    assert first["scheduler_wake_authorized"] is False
    assert first["wake_admission_record_id"].startswith("runtime-wake-admission::")


def test_1541_boundary_source_does_not_reference_execution_surfaces():
    source = (
        ROOT / "core/runtime/runtime_scheduler_wake_admission.py"
    ).read_text()
    lowered = source.lower()

    assert "scheduler" not in lowered
    assert "executor" not in lowered
    assert "task_runner" not in lowered
    assert "agent_loop" not in lowered
    assert "work_package_operator" not in lowered
    assert "progress_memory" not in lowered


def test_1542_wake_admission_does_not_mutate_or_dispatch():
    record = evaluate_scheduler_wake_admission(_tick_request())

    assert record["runtime_state_mutated"] is False
    assert record["wake_performed"] is False
    assert record["task_executed"] is False
    assert record["runtime_queue_mutated"] is False
    assert record["cursor_advanced_here"] is False
    assert record["progress_state_modified"] is False
    assert record["loop_behavior_created"] is False
    assert record["dispatch_performed"] is False


def test_1543_result_is_record_only_wake_admission_data():
    record = evaluate_scheduler_wake_admission(_tick_request())

    assert record["record_only"] is True
    assert record["wake_admission_only"] is True


def test_1544_inputs_are_not_mutated():
    tick = _tick_request()
    before = _tick_request()

    evaluate_scheduler_wake_admission(tick)

    assert tick == before
