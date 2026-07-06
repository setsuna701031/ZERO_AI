from __future__ import annotations

from pathlib import Path

from core.runtime.bounded_executor_dispatch_bridge import (
    build_bounded_executor_dispatch_request,
)


ROOT = Path(__file__).resolve().parents[1]


def _tick_result(tick_status: str = "ALLOW_SINGLE_TICK", *, authority: bool = True):
    tick = {
        "schema": "zero.runtime.tick_runner.v1",
        "tick_id": f"runtime-tick-result::session-1417::{tick_status}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_cycle_id": "runtime-cycle-request::session-1417",
        "tick_status": tick_status,
        "requested_action": "REQUEST_NEXT_TICK",
        "dispatched": tick_status == "ALLOW_SINGLE_TICK",
        "completed": tick_status in {"CLOSED", "STOPPED"},
        "blocked_reason": "none",
        "single_tick_only": True,
        "dispatch_intent_only": tick_status == "ALLOW_SINGLE_TICK",
        "executor_called": False,
    }
    if authority:
        tick.update(
            {
                "execution_lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
                "capability_grant_id": "capability-grant::limited-runtime-session::birth-1209::capability-1225",
                "executor_binding_id": "executor-binding::executor-zero::binding-1233",
            }
        )
    return tick


def test_1417_allow_single_tick_creates_dispatch_request():
    request = build_bounded_executor_dispatch_request(_tick_result())

    assert request["dispatch_status"] == "dispatch_requested"
    assert request["execution_requested"] is True
    assert request["actual_executor_called"] is False
    assert request["blocked_reason"] == "none"
    assert request["source_tick_id"].startswith("runtime-tick-result::")


def test_1418_recovery_paused_closed_stopped_do_not_dispatch():
    for status in ("ENTER_RECOVERY_GATE", "PAUSED", "CLOSED", "STOPPED"):
        request = build_bounded_executor_dispatch_request(_tick_result(status))

        assert request["dispatch_status"] == "blocked"
        assert request["execution_requested"] is False
        assert request["actual_executor_called"] is False
        assert request["blocked_reason"] == "tick_status_not_dispatchable"


def test_1419_missing_authority_blocks_dispatch():
    request = build_bounded_executor_dispatch_request(
        _tick_result("ALLOW_SINGLE_TICK", authority=False)
    )

    assert request["dispatch_status"] == "blocked"
    assert request["execution_requested"] is False
    assert request["blocked_reason"].startswith("missing_authority:")
    assert request["missing_authority"] == [
        "execution_lease_id",
        "capability_grant_id",
        "executor_binding_id",
    ]


def test_1420_same_tick_result_creates_deterministic_request():
    tick = _tick_result()

    first = build_bounded_executor_dispatch_request(tick)
    second = build_bounded_executor_dispatch_request(tick)

    assert first == second
    assert first["dispatch_request_id"].startswith("bounded-executor-dispatch::")


def test_1421_no_executor_import():
    bridge_source = (ROOT / "core/runtime/bounded_executor_dispatch_bridge.py").read_text()
    request = build_bounded_executor_dispatch_request(_tick_result())

    assert "import executor" not in bridge_source
    assert "from core.runtime.executor" not in bridge_source
    assert request["actual_executor_called"] is False
    assert request["direct_executor_call_performed"] is False


def test_1422_no_scheduler_import():
    bridge_source = (ROOT / "core/runtime/bounded_executor_dispatch_bridge.py").read_text()
    request = build_bounded_executor_dispatch_request(_tick_result())

    assert "import scheduler" not in bridge_source
    assert "from core.runtime.runtime_scheduler" not in bridge_source
    assert request["scheduler_imported"] is False
    assert request["scheduler_mutation_performed"] is False


def test_1423_no_loop_thread_retry_flags():
    request = build_bounded_executor_dispatch_request(_tick_result())

    assert request["loop_started"] is False
    assert request["thread_created"] is False
    assert request["automatic_retry_performed"] is False
    assert request["single_dispatch_request_only"] is True


def test_1424_authority_can_be_nested():
    tick = _tick_result(authority=False)
    tick["authority"] = {
        "execution_lease_id": "execution-lease::nested",
        "capability_grant_id": "capability-grant::nested",
        "executor_binding_id": "executor-binding::nested",
    }

    request = build_bounded_executor_dispatch_request(tick)

    assert request["dispatch_status"] == "dispatch_requested"
    assert request["execution_lease_id"] == "execution-lease::nested"
