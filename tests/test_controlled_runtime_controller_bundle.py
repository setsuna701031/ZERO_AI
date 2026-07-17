from __future__ import annotations

from pathlib import Path

from core.runtime.controlled_runtime_controller import build_runtime_cycle_request


ROOT = Path(__file__).resolve().parents[1]


def _decision(action: str = "CONTINUE_EXECUTION"):
    return {
        "schema": "zero.runtime.loop_resume_policy.v1",
        "decision_id": f"runtime-loop-resume-decision::session-1401::{action}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "progress_snapshot_id": "runtime-progress-snapshot::session-1401",
        "cursor_id": "runtime-resume-cursor::session-1401",
        "action": action,
        "next_step": {
            "next_step_index": 3,
            "last_committed_step": {
                "step_result_commit_id": "commit-3",
                "step_id": "step::2",
            },
        },
        "recovery_required": action == "ENTER_RECOVERY",
        "reason": f"test_{action.lower()}",
        "record_only": True,
        "decision_only": True,
    }


def test_1401_continue_execution_creates_next_tick_request():
    request = build_runtime_cycle_request(_decision("CONTINUE_EXECUTION"))

    assert request["requested_action"] == "REQUEST_NEXT_TICK"
    assert request["authorization_required"] is True
    assert request["execution_requested"] is True
    assert request["next_step_reference"]["next_step_index"] == 3


def test_1402_recovery_creates_recovery_request():
    request = build_runtime_cycle_request(_decision("ENTER_RECOVERY"))

    assert request["requested_action"] == "REQUEST_RECOVERY_FLOW"
    assert request["authorization_required"] is True
    assert request["execution_requested"] is False


def test_1403_complete_closes_runtime():
    request = build_runtime_cycle_request(_decision("MARK_COMPLETE"))

    assert request["requested_action"] == "CLOSE_RUNTIME"
    assert request["execution_requested"] is False


def test_1404_wait_pauses_runtime():
    request = build_runtime_cycle_request(_decision("WAIT_FOR_INPUT"))

    assert request["requested_action"] == "PAUSE_RUNTIME"
    assert request["execution_requested"] is False


def test_1405_blocked_stops_runtime():
    request = build_runtime_cycle_request(_decision("BLOCKED"))

    assert request["requested_action"] == "STOP_RUNTIME"
    assert request["execution_requested"] is False


def test_1406_same_decision_creates_deterministic_request():
    decision = _decision("CONTINUE_EXECUTION")

    first = build_runtime_cycle_request(decision)
    second = build_runtime_cycle_request(decision)

    assert first == second
    assert first["cycle_id"].startswith("runtime-cycle-request::")
    assert first["source_decision_id"] == decision["decision_id"]


def test_1407_no_executor_import():
    controller_source = (ROOT / "core/runtime/controlled_runtime_controller.py").read_text()

    assert "import executor" not in controller_source
    assert "from core.runtime.executor" not in controller_source
    assert "executor_run_performed" in controller_source


def test_1408_no_scheduler_import():
    controller_source = (ROOT / "core/runtime/controlled_runtime_controller.py").read_text()
    request = build_runtime_cycle_request(_decision("CONTINUE_EXECUTION"))

    assert "import scheduler" not in controller_source
    assert "from core.runtime.runtime_scheduler" not in controller_source
    assert request["scheduler_mutation_performed"] is False
    assert request["progress_memory_mutated"] is False
    assert request["while_loop_started"] is False
    assert request["thread_created"] is False
    assert request["automatic_retry_performed"] is False
