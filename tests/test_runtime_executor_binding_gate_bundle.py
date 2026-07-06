from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_executor_binding_gate import (
    build_runtime_executor_binding_record,
)


ROOT = Path(__file__).resolve().parents[1]


def _authority(**overrides):
    record = {
        "execution_lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "capability_grant_id": "capability-grant::limited-runtime-session::birth-1209::capability-1225",
        "executor_binding_id": "executor-binding::executor-zero::binding-1233",
    }
    record.update(overrides)
    return {key: value for key, value in record.items() if value is not None}


def _envelope(*, authorized: bool = True):
    return {
        "schema": "zero.runtime.executor_invocation_adapter.v1",
        "envelope_id": f"runtime-executor-invocation-envelope::session-1457::{authorized}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_permit_id": "runtime-invocation-permit::session-1457",
        "executor_target": _authority() if authorized else {},
        "invocation_authorized": authorized,
        "payload_reference": {
            "source_permit_id": "runtime-invocation-permit::session-1457",
            "source_execution_record_id": "controlled-loop-plan-execution::session-1457",
        },
        "execution_started": False,
        "executor_called": False,
        "result_expected": authorized,
        "blocked_reason": "none" if authorized else "permit_denied",
    }


def test_1457_valid_envelope_creates_binding_record():
    record = build_runtime_executor_binding_record(
        _envelope(),
        authority=_authority(),
    )

    assert record["execution_bound"] is True
    assert record["binding_status"] == "bound"
    assert record["result_commit_required"] is True
    assert record["blocked_reason"] == "none"


def test_1458_denied_envelope_blocks():
    record = build_runtime_executor_binding_record(
        _envelope(authorized=False),
        authority=_authority(),
    )

    assert record["execution_bound"] is False
    assert record["binding_status"] == "blocked"
    assert record["blocked_reason"] == "permit_denied"
    assert record["result_commit_required"] is False


def test_1459_missing_lease_grant_binding_blocks():
    envelope = _envelope()
    envelope["executor_target"] = {}
    record = build_runtime_executor_binding_record(envelope, authority={})

    assert record["execution_bound"] is False
    assert record["blocked_reason"] == (
        "missing_authority:execution_lease_id,capability_grant_id,executor_binding_id"
    )
    assert record["missing_authority"] == [
        "execution_lease_id",
        "capability_grant_id",
        "executor_binding_id",
    ]


def test_1460_deterministic_binding_record():
    envelope = _envelope()
    authority = _authority()

    first = build_runtime_executor_binding_record(envelope, authority=authority)
    second = build_runtime_executor_binding_record(envelope, authority=authority)

    assert first == second
    assert first["binding_record_id"].startswith("runtime-executor-binding-record::")


def test_1461_executor_called_false():
    record = build_runtime_executor_binding_record(_envelope(), authority=_authority())

    assert record["executor_called"] is False
    assert record["executor_implementation_imported"] is False
    assert record["command_executed"] is False


def test_1462_execution_started_false():
    record = build_runtime_executor_binding_record(_envelope(), authority=_authority())

    assert record["execution_started"] is False
    assert record["progress_mutated"] is False
    assert record["retry_scheduled"] is False


def test_1463_no_executor_implementation_import():
    source = (ROOT / "core/runtime/runtime_executor_binding_gate.py").read_text()

    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert "runtime_executor_invocation_adapter" not in source


def test_1464_no_scheduler_import():
    source = (ROOT / "core/runtime/runtime_executor_binding_gate.py").read_text()
    record = build_runtime_executor_binding_record(_envelope(), authority=_authority())

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert record["scheduler_imported"] is False
    assert record["loop_created"] is False
    assert record["thread_created"] is False
