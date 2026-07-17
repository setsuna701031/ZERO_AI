from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_tick_request_gate import evaluate_runtime_tick_request


ROOT = Path(__file__).resolve().parents[1]


def _cursor_advance(**overrides):
    record = {
        "schema": "zero.runtime.cursor_advance_authority.v1",
        "cursor_advance_record_id": "runtime-cursor-advance::session-1529::step-2",
        "runtime_id": "limited-runtime-session::birth-1209",
        "cursor_advance_authorized": True,
        "previous_cursor": {
            "cursor_id": "runtime-cursor::session-1529::step-1",
            "step_index": 1,
            "state": "CONTINUE",
        },
        "next_cursor": {
            "cursor_id": "runtime-cursor::session-1529::step-2",
            "step_index": 2,
            "state": "CONTINUE",
        },
        "source_progress_id": "runtime-progress-apply::session-1529::read",
        "denial_reason": "none",
        "runtime_state_mutated": False,
        "next_tick_requested": False,
    }
    record.update(overrides)
    return record


def test_1529_valid_cursor_advance_authorizes_tick_request():
    record = evaluate_runtime_tick_request(_cursor_advance(), runtime_mode="limited")

    assert record["tick_request_authorized"] is True
    assert record["source_cursor_advance_id"] == (
        "runtime-cursor-advance::session-1529::step-2"
    )
    assert record["current_cursor"] == _cursor_advance()["next_cursor"]
    assert record["requested_tick_reason"] == "cursor_advance_authorized"
    assert record["denial_reason"] == "none"
    assert record["scheduler_invoked"] is False
    assert record["executor_invoked"] is False
    assert record["runtime_state_mutated"] is False


def test_1530_missing_cursor_advance_record_denies():
    record = evaluate_runtime_tick_request(None)

    assert record["tick_request_authorized"] is False
    assert record["source_cursor_advance_id"] is None
    assert record["current_cursor"] == {}
    assert record["requested_tick_reason"] == "tick_request_denied"
    assert record["denial_reason"] == "missing_cursor_advance_record"
    assert record["scheduler_invoked"] is False
    assert record["executor_invoked"] is False
    assert record["runtime_state_mutated"] is False


def test_1531_cursor_advance_not_authorized_denies():
    record = evaluate_runtime_tick_request(
        _cursor_advance(
            cursor_advance_authorized=False,
            next_cursor={},
            denial_reason="progress_apply_rejected",
        )
    )

    assert record["tick_request_authorized"] is False
    assert record["current_cursor"] == {}
    assert record["denial_reason"] == "progress_apply_rejected"


def test_1532_denied_output_is_deterministic():
    cursor = _cursor_advance(
        cursor_advance_authorized=False,
        next_cursor={},
        denial_reason="commit_not_completed",
    )

    first = evaluate_runtime_tick_request(cursor, runtime_mode="limited")
    second = evaluate_runtime_tick_request(cursor, runtime_mode="limited")

    assert first == second
    assert first["tick_request_authorized"] is False
    assert first["tick_request_record_id"].startswith("runtime-tick-request::")


def test_1533_boundary_source_does_not_reference_execution_surfaces():
    source = (ROOT / "core/runtime/runtime_tick_request_gate.py").read_text()

    assert "scheduler" not in source
    assert "executor" not in source
    assert "task_runner" not in source
    assert "agent_loop" not in source
    assert "work_package_operator" not in source
    assert "progress_memory" not in source


def test_1534_tick_request_does_not_mutate_or_wake():
    record = evaluate_runtime_tick_request(_cursor_advance())

    assert record["runtime_state_mutated"] is False
    assert record["cursor_advanced_here"] is False
    assert record["progress_state_modified"] is False
    assert record["runtime_queue_mutated"] is False
    assert record["wake_performed"] is False
    assert record["loop_continued"] is False


def test_1535_result_is_record_only_gate_data():
    record = evaluate_runtime_tick_request(_cursor_advance())

    assert record["record_only"] is True
    assert record["tick_request_gate_only"] is True


def test_1536_inputs_are_not_mutated():
    cursor = _cursor_advance()
    before = _cursor_advance()

    evaluate_runtime_tick_request(cursor)

    assert cursor == before
