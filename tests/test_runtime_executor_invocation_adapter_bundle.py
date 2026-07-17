from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_executor_invocation_adapter import (
    build_runtime_executor_invocation_envelope,
)


ROOT = Path(__file__).resolve().parents[1]


def _permit(*, allowed: bool = True, authority: bool = True):
    permit = {
        "schema": "zero.runtime.dispatch_invocation_gate.v1",
        "permit_id": f"runtime-invocation-permit::session-1449::{allowed}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_execution_record_id": "controlled-loop-plan-execution::session-1449",
        "invocation_allowed": allowed,
        "executor_permission": "PERMIT_INVOCATION" if allowed else "DENY_INVOCATION",
        "dispatch_reference": {
            "source_loop_plan_id": "controlled-runtime-loop-plan::session-1449",
            "selected_tick_intent_id": "tick-intent::1",
            "dispatch_allowed": allowed,
        },
        "denial_reason": "none" if allowed else "permit_denied",
        "authority_verified": allowed and authority,
        "executor_called": False,
        "scheduler_called": False,
    }
    if authority:
        permit.update(
            {
                "execution_lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
                "capability_grant_id": "capability-grant::limited-runtime-session::birth-1209::capability-1225",
                "executor_binding_id": "executor-binding::executor-zero::binding-1233",
            }
        )
    return permit


def test_1449_valid_permit_creates_invocation_envelope():
    envelope = build_runtime_executor_invocation_envelope(_permit())

    assert envelope["invocation_authorized"] is True
    assert envelope["result_expected"] is True
    assert envelope["blocked_reason"] == "none"
    assert envelope["executor_target"]["target_mode"] == "invocation_envelope_only"
    assert envelope["source_permit_id"].startswith("runtime-invocation-permit::")


def test_1450_denied_permit_creates_blocked_envelope():
    envelope = build_runtime_executor_invocation_envelope(_permit(allowed=False))

    assert envelope["invocation_authorized"] is False
    assert envelope["result_expected"] is False
    assert envelope["executor_target"] == {}
    assert envelope["blocked_reason"] == "permit_denied"


def test_1451_missing_authority_blocks():
    permit = _permit(authority=False)
    permit["authority_verified"] = True
    envelope = build_runtime_executor_invocation_envelope(permit)

    assert envelope["invocation_authorized"] is False
    assert envelope["blocked_reason"].startswith("missing_authority:")
    assert envelope["missing_authority"] == [
        "execution_lease_id",
        "capability_grant_id",
        "executor_binding_id",
    ]


def test_1452_same_permit_creates_same_envelope():
    permit = _permit()

    first = build_runtime_executor_invocation_envelope(permit)
    second = build_runtime_executor_invocation_envelope(permit)

    assert first == second
    assert first["envelope_id"].startswith("runtime-executor-invocation-envelope::")


def test_1453_executor_called_always_false():
    allowed = build_runtime_executor_invocation_envelope(_permit())
    denied = build_runtime_executor_invocation_envelope(_permit(allowed=False))

    assert allowed["executor_called"] is False
    assert denied["executor_called"] is False
    assert allowed["executor_implementation_imported"] is False


def test_1454_execution_started_always_false():
    allowed = build_runtime_executor_invocation_envelope(_permit())
    denied = build_runtime_executor_invocation_envelope(_permit(allowed=False))

    assert allowed["execution_started"] is False
    assert denied["execution_started"] is False
    assert allowed["command_executed"] is False
    assert allowed["files_mutated"] is False
    assert allowed["progress_mutated"] is False


def test_1455_no_executor_implementation_import():
    source = (ROOT / "core/runtime/runtime_executor_invocation_adapter.py").read_text()

    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert "runtime_executor_invocation_boundary" not in source


def test_1456_no_scheduler_import():
    source = (ROOT / "core/runtime/runtime_executor_invocation_adapter.py").read_text()
    envelope = build_runtime_executor_invocation_envelope(_permit())

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert envelope["scheduler_imported"] is False
    assert envelope["retry_scheduled"] is False
    assert envelope["loop_created"] is False
    assert envelope["thread_created"] is False
