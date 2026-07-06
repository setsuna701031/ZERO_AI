from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_execution_evidence_return_path import (
    build_runtime_execution_evidence_return_record,
)


ROOT = Path(__file__).resolve().parents[1]


def _binding(*, bound: bool = True):
    return {
        "schema": "zero.runtime.executor_binding_gate.v1",
        "binding_record_id": f"runtime-executor-binding-record::session-1465::{bound}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_envelope_id": "runtime-executor-invocation-envelope::session-1465",
        "execution_bound": bound,
        "binding_status": "bound" if bound else "blocked",
        "result_commit_required": bound,
        "execution_started": False,
        "executor_called": False,
    }


def _evidence(
    result_kind: str = "read_result",
    *,
    summary: str = "caller supplied read evidence",
    failure_reason: str = "none",
    recovery_required: bool = False,
):
    return {
        "caller_supplied": True,
        "result_kind": result_kind,
        "summary": summary,
        "failure_reason": failure_reason,
        "recovery_required": recovery_required,
    }


def test_1465_bound_record_success_evidence_commit_ready():
    record = build_runtime_execution_evidence_return_record(
        _binding(),
        _evidence("read_result"),
    )

    assert record["evidence_accepted"] is True
    assert record["commit_ready"] is True
    assert record["result_kind"] == "read_result"
    assert record["summary"] == "caller supplied read evidence"
    assert record["commit_input"]["result_kind"] == "read_result"


def test_1466_failure_evidence_preserves_failure_reason():
    record = build_runtime_execution_evidence_return_record(
        _binding(),
        _evidence(
            "failure_result",
            summary="caller supplied failure evidence",
            failure_reason="executor_reported_failure",
        ),
    )

    assert record["evidence_accepted"] is True
    assert record["commit_ready"] is True
    assert record["result_kind"] == "failure_result"
    assert record["failure_reason"] == "executor_reported_failure"


def test_1467_recovery_evidence_sets_recovery_required():
    record = build_runtime_execution_evidence_return_record(
        _binding(),
        _evidence("recovery_result", summary="caller supplied recovery evidence"),
    )

    assert record["evidence_accepted"] is True
    assert record["recovery_required"] is True
    assert record["commit_ready"] is True


def test_1468_unbound_record_blocks():
    record = build_runtime_execution_evidence_return_record(
        _binding(bound=False),
        _evidence(),
    )

    assert record["evidence_accepted"] is False
    assert record["commit_ready"] is False
    assert record["blocked_reason"] == "execution_not_bound"


def test_1469_missing_evidence_blocks():
    record = build_runtime_execution_evidence_return_record(_binding(), {})

    assert record["evidence_accepted"] is False
    assert record["commit_ready"] is False
    assert record["blocked_reason"] == "missing_caller_supplied_evidence"


def test_1470_deterministic_return_record():
    binding = _binding()
    evidence = _evidence("write_result", summary="caller supplied write evidence")

    first = build_runtime_execution_evidence_return_record(binding, evidence)
    second = build_runtime_execution_evidence_return_record(binding, evidence)

    assert first == second
    assert first["return_record_id"].startswith("runtime-execution-evidence-return::")


def test_1471_executor_called_false():
    record = build_runtime_execution_evidence_return_record(_binding(), _evidence())

    assert record["executor_called"] is False
    assert record["execution_inferred"] is False


def test_1472_no_scheduler_import():
    source = (ROOT / "core/runtime/runtime_execution_evidence_return_path.py").read_text()
    record = build_runtime_execution_evidence_return_record(_binding(), _evidence())

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert record["scheduler_imported"] is False
    assert record["progress_mutated"] is False
    assert record["retry_scheduled"] is False
    assert record["loop_created"] is False
    assert record["thread_created"] is False
