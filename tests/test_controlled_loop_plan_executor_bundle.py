from __future__ import annotations

from pathlib import Path

from core.runtime.controlled_loop_plan_executor import (
    build_controlled_loop_plan_execution_record,
)


ROOT = Path(__file__).resolve().parents[1]


def _authority():
    return {
        "execution_lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "capability_grant_id": "capability-grant::limited-runtime-session::birth-1209::capability-1225",
        "executor_binding_id": "executor-binding::executor-zero::binding-1233",
    }


def _plan(*, status: str = "planned", count: int = 2):
    plan_id = "controlled-runtime-loop-plan::session-1433::abc"
    intents = [
        {
            "intent_id": f"{plan_id}::tick-intent::{index + 1}",
            "tick_number": index + 1,
            "requested_action": "ALLOW_SINGLE_TICK",
            "execution_requested": True,
            "actual_executor_called": False,
        }
        for index in range(count)
    ]
    return {
        "schema": "zero.runtime.controlled_autonomous_runtime_loop.v1",
        "plan_id": plan_id,
        "runtime_id": "limited-runtime-session::birth-1209",
        "plan_status": status,
        "max_ticks": count,
        "planned_tick_count": count,
        "tick_intents": intents if status == "planned" else [],
        "blocked_reason": "none" if status == "planned" else "upstream_stopped",
        "ordered_tick_intents_only": True,
    }


def test_1433_valid_plan_selects_exactly_one_tick_intent():
    plan = _plan(count=3)
    selected = plan["tick_intents"][1]["intent_id"]
    record = build_controlled_loop_plan_execution_record(
        plan,
        selected_tick_intent_id=selected,
        authority=_authority(),
    )

    assert record["execution_status"] == "ONE_TICK_SELECTED"
    assert record["dispatch_allowed"] is True
    assert record["selected_tick_intent_id"] == selected
    assert record["selected_tick_intent"]["tick_number"] == 2
    assert record["executor_called"] is False
    assert record["scheduler_called"] is False
    assert record["loop_continued"] is False


def test_1434_missing_authority_blocks():
    plan = _plan()
    selected = plan["tick_intents"][0]["intent_id"]
    record = build_controlled_loop_plan_execution_record(
        plan,
        selected_tick_intent_id=selected,
        authority={},
    )

    assert record["execution_status"] == "BLOCKED"
    assert record["dispatch_allowed"] is False
    assert record["blocked_reason"].startswith("missing_authority:")


def test_1435_invalid_selected_tick_blocks():
    record = build_controlled_loop_plan_execution_record(
        _plan(),
        selected_tick_intent_id="missing-intent",
        authority=_authority(),
    )

    assert record["execution_status"] == "BLOCKED"
    assert record["dispatch_allowed"] is False
    assert record["blocked_reason"] == "invalid_tick_intent_id"


def test_1436_empty_plan_blocks():
    record = build_controlled_loop_plan_execution_record(
        _plan(count=0),
        selected_tick_intent_id="missing-intent",
        authority=_authority(),
    )

    assert record["execution_status"] == "BLOCKED"
    assert record["dispatch_allowed"] is False
    assert record["blocked_reason"] == "empty_plan"


def test_1437_deterministic_execution_record():
    plan = _plan()
    selected = plan["tick_intents"][0]["intent_id"]

    first = build_controlled_loop_plan_execution_record(
        plan,
        selected_tick_intent_id=selected,
        authority=_authority(),
    )
    second = build_controlled_loop_plan_execution_record(
        plan,
        selected_tick_intent_id=selected,
        authority=_authority(),
    )

    assert first == second
    assert first["execution_record_id"].startswith("controlled-loop-plan-execution::")


def test_1438_no_executor_import():
    source = (ROOT / "core/runtime/controlled_loop_plan_executor.py").read_text()
    plan = _plan()
    record = build_controlled_loop_plan_execution_record(
        plan,
        selected_tick_intent_id=plan["tick_intents"][0]["intent_id"],
        authority=_authority(),
    )

    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert record["executor_called"] is False
    assert record["direct_executor_call_performed"] is False


def test_1439_no_scheduler_import():
    source = (ROOT / "core/runtime/controlled_loop_plan_executor.py").read_text()
    plan = _plan()
    record = build_controlled_loop_plan_execution_record(
        plan,
        selected_tick_intent_id=plan["tick_intents"][0]["intent_id"],
        authority=_authority(),
    )

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert record["scheduler_called"] is False
    assert record["direct_scheduler_call_performed"] is False


def test_1440_no_loop_thread_daemon_retry_flags():
    source = (ROOT / "core/runtime/controlled_loop_plan_executor.py").read_text()
    plan = _plan()
    record = build_controlled_loop_plan_execution_record(
        plan,
        selected_tick_intent_id=plan["tick_intents"][0]["intent_id"],
        authority=_authority(),
    )

    assert "while " not in source
    assert "threading" not in source
    assert record["infinite_loop_allowed"] is False
    assert record["loop_executed"] is False
    assert record["thread_created"] is False
    assert record["daemon_started"] is False
    assert record["automatic_retry_performed"] is False
    assert record["loop_continued"] is False
