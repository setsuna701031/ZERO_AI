from __future__ import annotations

from pathlib import Path

from core.runtime.controlled_autonomous_runtime_loop import (
    build_controlled_runtime_loop_plan,
)


ROOT = Path(__file__).resolve().parents[1]


def _dispatch_request(*, status: str = "dispatch_requested", authority: bool = True):
    request = {
        "schema": "zero.runtime.bounded_executor_dispatch_bridge.v1",
        "dispatch_request_id": f"bounded-executor-dispatch::session-1425::{status}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_tick_id": "runtime-tick-result::session-1425",
        "source_cycle_id": "runtime-cycle-request::session-1425",
        "tick_status": "ALLOW_SINGLE_TICK",
        "requested_action": "REQUEST_NEXT_TICK",
        "dispatch_status": status,
        "execution_requested": status == "dispatch_requested",
        "actual_executor_called": False,
        "blocked_reason": "none" if status == "dispatch_requested" else "upstream_blocked",
    }
    if authority:
        request.update(
            {
                "execution_lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
                "capability_grant_id": "capability-grant::limited-runtime-session::birth-1209::capability-1225",
                "executor_binding_id": "executor-binding::executor-zero::binding-1233",
            }
        )
    return request


def test_1425_valid_dispatch_request_creates_bounded_loop_plan():
    plan = build_controlled_runtime_loop_plan(_dispatch_request(), max_ticks=3)

    assert plan["plan_status"] == "planned"
    assert plan["planned_tick_count"] == 3
    assert len(plan["tick_intents"]) == 3
    assert plan["tick_intents"][0]["tick_number"] == 1
    assert plan["tick_intents"][2]["tick_number"] == 3
    assert plan["ordered_tick_intents_only"] is True


def test_1426_max_ticks_enforced_and_required():
    plan = build_controlled_runtime_loop_plan(_dispatch_request(), max_ticks=2)
    missing = build_controlled_runtime_loop_plan(_dispatch_request())
    zero = build_controlled_runtime_loop_plan(_dispatch_request(), max_ticks=0)

    assert plan["planned_tick_count"] == 2
    assert len(plan["tick_intents"]) == 2
    assert missing["plan_status"] == "blocked"
    assert missing["blocked_reason"] == "max_ticks_required"
    assert zero["plan_status"] == "blocked"


def test_1427_missing_authority_blocks():
    plan = build_controlled_runtime_loop_plan(
        _dispatch_request(authority=False),
        max_ticks=3,
    )

    assert plan["plan_status"] == "blocked"
    assert plan["planned_tick_count"] == 0
    assert plan["tick_intents"] == []
    assert plan["blocked_reason"].startswith("missing_authority:")


def test_1428_blocked_dispatch_stops():
    plan = build_controlled_runtime_loop_plan(
        _dispatch_request(status="blocked"),
        max_ticks=3,
    )

    assert plan["plan_status"] == "stopped"
    assert plan["planned_tick_count"] == 0
    assert plan["tick_intents"] == []
    assert plan["blocked_reason"] == "upstream_blocked"


def test_1429_same_dispatch_request_creates_deterministic_plan():
    request = _dispatch_request()

    first = build_controlled_runtime_loop_plan(request, max_ticks=3)
    second = build_controlled_runtime_loop_plan(request, max_ticks=3)

    assert first == second
    assert first["plan_id"].startswith("controlled-runtime-loop-plan::")


def test_1430_no_executor_import():
    loop_source = (ROOT / "core/runtime/controlled_autonomous_runtime_loop.py").read_text()
    plan = build_controlled_runtime_loop_plan(_dispatch_request(), max_ticks=1)

    assert "import executor" not in loop_source
    assert "from core.runtime.executor" not in loop_source
    assert plan["actual_executor_called"] is False
    assert plan["direct_executor_call_performed"] is False


def test_1431_no_scheduler_import():
    loop_source = (ROOT / "core/runtime/controlled_autonomous_runtime_loop.py").read_text()
    plan = build_controlled_runtime_loop_plan(_dispatch_request(), max_ticks=1)

    assert "import scheduler" not in loop_source
    assert "from core.runtime.runtime_scheduler" not in loop_source
    assert plan["scheduler_imported"] is False
    assert plan["scheduler_mutation_performed"] is False


def test_1432_no_infinite_loop_thread_daemon_flags():
    loop_source = (ROOT / "core/runtime/controlled_autonomous_runtime_loop.py").read_text()
    plan = build_controlled_runtime_loop_plan(_dispatch_request(), max_ticks=2)

    assert "while " not in loop_source
    assert "threading" not in loop_source
    assert plan["infinite_loop_allowed"] is False
    assert plan["loop_executed"] is False
    assert plan["thread_created"] is False
    assert plan["daemon_started"] is False
    assert plan["automatic_retry_performed"] is False
