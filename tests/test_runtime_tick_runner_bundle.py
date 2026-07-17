from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_tick_runner import build_runtime_tick_result


ROOT = Path(__file__).resolve().parents[1]


def _cycle_request(requested_action: str = "REQUEST_NEXT_TICK"):
    return {
        "schema": "zero.runtime.controlled_runtime_controller.v1",
        "cycle_id": f"runtime-cycle-request::session-1409::{requested_action}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_decision_id": "runtime-loop-resume-decision::session-1409",
        "requested_action": requested_action,
        "next_step_reference": {
            "next_step_index": 4,
            "last_committed_step": {
                "step_result_commit_id": "commit-4",
                "step_id": "step::3",
            },
        },
        "authorization_required": True,
        "execution_requested": requested_action == "REQUEST_NEXT_TICK",
        "record_only": True,
        "cycle_request_only": True,
    }


def test_1409_request_next_tick_produces_single_tick():
    result = build_runtime_tick_result(_cycle_request("REQUEST_NEXT_TICK"))

    assert result["tick_status"] == "ALLOW_SINGLE_TICK"
    assert result["dispatched"] is True
    assert result["completed"] is False
    assert result["single_tick_only"] is True
    assert result["dispatch_intent_only"] is True
    assert result["executor_called"] is False


def test_1410_recovery_request_enters_recovery_gate():
    result = build_runtime_tick_result(_cycle_request("REQUEST_RECOVERY_FLOW"))

    assert result["tick_status"] == "ENTER_RECOVERY_GATE"
    assert result["dispatched"] is False
    assert result["completed"] is False


def test_1411_pause_request_pauses():
    result = build_runtime_tick_result(_cycle_request("PAUSE_RUNTIME"))

    assert result["tick_status"] == "PAUSED"
    assert result["dispatched"] is False
    assert result["blocked_reason"] == "none"


def test_1412_close_request_closes():
    result = build_runtime_tick_result(_cycle_request("CLOSE_RUNTIME"))

    assert result["tick_status"] == "CLOSED"
    assert result["completed"] is True
    assert result["dispatched"] is False


def test_1413_blocked_request_stops():
    result = build_runtime_tick_result(_cycle_request("STOP_RUNTIME"))

    assert result["tick_status"] == "STOPPED"
    assert result["completed"] is True
    assert result["dispatched"] is False


def test_1414_same_cycle_request_creates_deterministic_tick_result():
    cycle_request = _cycle_request("REQUEST_NEXT_TICK")

    first = build_runtime_tick_result(cycle_request)
    second = build_runtime_tick_result(cycle_request)

    assert first == second
    assert first["tick_id"].startswith("runtime-tick-result::")
    assert first["source_cycle_id"] == cycle_request["cycle_id"]


def test_1415_does_not_loop():
    result = build_runtime_tick_result(_cycle_request("REQUEST_NEXT_TICK"))
    runner_source = (ROOT / "core/runtime/runtime_tick_runner.py").read_text()

    assert "while " not in runner_source
    assert "threading" not in runner_source
    assert result["loop_started"] is False
    assert result["background_thread_created"] is False
    assert result["automatic_retry_performed"] is False
    assert result["controller_bypassed"] is False
    assert result["progress_memory_mutated"] is False


def test_1416_does_not_import_scheduler_directly():
    runner_source = (ROOT / "core/runtime/runtime_tick_runner.py").read_text()
    result = build_runtime_tick_result(_cycle_request("REQUEST_NEXT_TICK"))

    assert "import scheduler" not in runner_source
    assert "from core.runtime.runtime_scheduler" not in runner_source
    assert result["scheduler_imported"] is False
    assert result["scheduler_mutation_performed"] is False
