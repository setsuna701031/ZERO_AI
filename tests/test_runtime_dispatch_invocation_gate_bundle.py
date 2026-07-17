from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_dispatch_invocation_gate import build_runtime_invocation_permit


ROOT = Path(__file__).resolve().parents[1]


def _authority(**overrides):
    record = {
        "execution_lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "capability_grant_id": "capability-grant::limited-runtime-session::birth-1209::capability-1225",
        "executor_binding_id": "executor-binding::executor-zero::binding-1233",
    }
    record.update(overrides)
    return {key: value for key, value in record.items() if value is not None}


def _execution_record(status: str = "ONE_TICK_SELECTED"):
    return {
        "schema": "zero.runtime.controlled_loop_plan_executor.v1",
        "execution_record_id": f"controlled-loop-plan-execution::session-1441::{status}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_loop_plan_id": "controlled-runtime-loop-plan::session-1441",
        "selected_tick_intent_id": "controlled-runtime-loop-plan::session-1441::tick-intent::1",
        "execution_status": status,
        "dispatch_allowed": status == "ONE_TICK_SELECTED",
        "executor_called": False,
        "scheduler_called": False,
        "loop_continued": False,
        "blocked_reason": "none" if status == "ONE_TICK_SELECTED" else "blocked_tick",
    }


def test_1441_one_tick_selected_with_authority_creates_permit():
    permit = build_runtime_invocation_permit(
        _execution_record(),
        authority=_authority(),
    )

    assert permit["invocation_allowed"] is True
    assert permit["executor_permission"] == "PERMIT_INVOCATION"
    assert permit["authority_verified"] is True
    assert permit["denial_reason"] == "none"
    assert permit["dispatch_reference"]["dispatch_allowed"] is True


def test_1442_missing_lease_denies():
    permit = build_runtime_invocation_permit(
        _execution_record(),
        authority=_authority(execution_lease_id=None),
    )

    assert permit["invocation_allowed"] is False
    assert permit["executor_permission"] == "DENY_INVOCATION"
    assert permit["denial_reason"] == "missing_authority:execution_lease_id"
    assert permit["authority_verified"] is False


def test_1443_missing_grant_denies():
    permit = build_runtime_invocation_permit(
        _execution_record(),
        authority=_authority(capability_grant_id=None),
    )

    assert permit["invocation_allowed"] is False
    assert permit["denial_reason"] == "missing_authority:capability_grant_id"


def test_1444_missing_binding_denies():
    permit = build_runtime_invocation_permit(
        _execution_record(),
        authority=_authority(executor_binding_id=None),
    )

    assert permit["invocation_allowed"] is False
    assert permit["denial_reason"] == "missing_authority:executor_binding_id"


def test_1445_blocked_tick_denies():
    permit = build_runtime_invocation_permit(
        _execution_record("BLOCKED"),
        authority=_authority(),
    )

    assert permit["invocation_allowed"] is False
    assert permit["executor_permission"] == "DENY_INVOCATION"
    assert permit["denial_reason"] == "execution_status_not_one_tick_selected"


def test_1446_same_input_same_permit():
    record = _execution_record()
    authority = _authority()

    first = build_runtime_invocation_permit(record, authority=authority)
    second = build_runtime_invocation_permit(record, authority=authority)

    assert first == second
    assert first["permit_id"].startswith("runtime-invocation-permit::")


def test_1447_no_executor_import():
    source = (ROOT / "core/runtime/runtime_dispatch_invocation_gate.py").read_text()
    permit = build_runtime_invocation_permit(_execution_record(), authority=_authority())

    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert permit["executor_imported"] is False
    assert permit["executor_called"] is False


def test_1448_no_scheduler_import():
    source = (ROOT / "core/runtime/runtime_dispatch_invocation_gate.py").read_text()
    permit = build_runtime_invocation_permit(_execution_record(), authority=_authority())

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert permit["scheduler_imported"] is False
    assert permit["scheduler_called"] is False
    assert permit["step_executed"] is False
    assert permit["progress_mutated"] is False
    assert permit["loop_continued"] is False
    assert permit["automatic_retry_performed"] is False
    assert permit["thread_created"] is False
