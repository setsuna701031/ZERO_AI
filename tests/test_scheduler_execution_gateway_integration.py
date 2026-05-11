from __future__ import annotations

from core.tasks.scheduler import Scheduler


def test_scheduler_execution_gateway_side_check_valid_step_uses_gateway():
    scheduler = Scheduler.__new__(Scheduler)

    result = scheduler._record_execution_gateway_side_check(
        step={
            "type": "write_file",
            "path": "workspace/shared/out.txt",
            "content": "hello",
        },
        legacy_result={
            "ok": True,
            "action": "write_file",
            "target_path": "workspace/shared/out.txt",
        },
        source="unit_test",
        trace=False,
    )

    assert result is not None
    assert result["ok"] is True
    assert result["source"] == "unit_test"
    assert result["used_gateway"] is True
    assert result["used_legacy_fallback"] is False
    assert result["runtime_error"] is None
    assert result["result_action"] == "write_file"


def test_scheduler_execution_gateway_side_check_invalid_step_uses_legacy_fallback():
    scheduler = Scheduler.__new__(Scheduler)

    result = scheduler._record_execution_gateway_side_check(
        step={
            "type": "write_file",
            "content": "missing path",
        },
        legacy_result={
            "ok": True,
            "action": "legacy_write_result",
            "reason": "legacy fallback should preserve behavior",
        },
        source="unit_test",
        trace=False,
    )

    assert result is not None
    assert result["ok"] is True
    assert result["used_gateway"] is False
    assert result["used_legacy_fallback"] is True
    assert "write_file:missing_path" in result["errors"]
    assert result["result_action"] == "legacy_write_result"


def test_scheduler_execution_gateway_side_check_handles_non_mapping_legacy_result():
    scheduler = Scheduler.__new__(Scheduler)

    result = scheduler._record_execution_gateway_side_check(
        step={
            "type": "noop",
        },
        legacy_result="done",
        source="unit_test",
        trace=False,
    )

    assert result is not None
    assert result["ok"] is True
    assert result["used_gateway"] is True
    assert result["runtime_error"] is None
    assert result["result_action"] == "legacy_execution_result"
