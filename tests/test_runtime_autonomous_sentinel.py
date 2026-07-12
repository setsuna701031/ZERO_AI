from __future__ import annotations

from core.runtime.runtime_autonomous_operator_bridge import (
    RuntimeAutonomousOperatorBridge,
)
from core.runtime.runtime_autonomous_sentinel import (
    RUNTIME_AUTONOMOUS_SENTINEL_SCHEMA,
    RuntimeAutonomousSentinel,
)


def _success(goal: str) -> dict:
    return {
        "ok": True,
        "repair_loop_status": "completed",
        "operator_result": {
            "controlled_mutation_result": {
                "ok": True,
                "mutation_completed": True,
                "validation_passed": True,
            }
        },
    }


def _failure(goal: str) -> dict:
    return {
        "ok": False,
        "denial_reason": "forced_failure",
        "operator_result": {
            "controlled_mutation_result": {
                "ok": False,
                "mutation_completed": False,
                "validation_passed": False,
            }
        },
    }


def test_sentinel_tick_reports_idle_when_queue_empty() -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_success)
    sentinel = RuntimeAutonomousSentinel(bridge=bridge)

    result = sentinel.tick()

    assert result["schema"] == RUNTIME_AUTONOMOUS_SENTINEL_SCHEMA
    assert result["ok"] is True
    assert result["sentinel_status"] == "idle"
    assert result["cycle"] == 1


def test_sentinel_tick_processes_one_task() -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_success)
    bridge.submit("update zero_probe.txt with sentinel data")
    sentinel = RuntimeAutonomousSentinel(bridge=bridge)

    result = sentinel.tick()

    assert result["ok"] is True
    assert result["sentinel_status"] == "completed"
    assert result["result"]["task"]["status"] == "completed"


def test_sentinel_run_processes_until_idle() -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        return _success(goal)

    bridge = RuntimeAutonomousOperatorBridge(runner=runner)
    bridge.submit("update a.txt with one")
    bridge.submit("update b.txt with two")

    sentinel = RuntimeAutonomousSentinel(bridge=bridge, max_cycles=5)
    result = sentinel.run()

    assert result["schema"] == RUNTIME_AUTONOMOUS_SENTINEL_SCHEMA
    assert result["ok"] is True
    assert result["sentinel_status"] == "idle"
    assert result["completed_count"] == 2
    assert result["idle_count"] == 1
    assert calls == [
        "update a.txt with one",
        "update b.txt with two",
    ]


def test_sentinel_run_records_failed_cycle() -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_failure)
    bridge.submit("update zero_probe.txt with bad data")

    sentinel = RuntimeAutonomousSentinel(bridge=bridge, max_cycles=2)
    result = sentinel.run()

    assert result["ok"] is False
    assert result["failed_count"] == 1
    assert result["cycles"][0]["sentinel_status"] == "failed"


def test_sentinel_calls_on_idle_callback() -> None:
    idle_cycles: list[int] = []

    bridge = RuntimeAutonomousOperatorBridge(runner=_success)
    sentinel = RuntimeAutonomousSentinel(
        bridge=bridge,
        max_cycles=3,
        on_idle=idle_cycles.append,
    )

    result = sentinel.run()

    assert result["sentinel_status"] == "idle"
    assert idle_cycles == [1]
