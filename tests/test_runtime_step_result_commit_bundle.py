from __future__ import annotations

from core.runtime.runtime_step_result_commit import (
    build_runtime_step_result_commit_audit_projection,
    build_runtime_step_result_commit_record,
    build_runtime_step_result_commit_request,
    can_runtime_step_result_commit_complete_task,
    validate_runtime_step_result_commit_request,
)


def _session_id():
    return "limited-runtime-session::birth-1209"


def _lease_id():
    return "execution-lease::limited-runtime-session::birth-1209::lease-1217"


def _grant_id():
    return (
        "capability-grant::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-1225"
    )


def _binding_id():
    return "executor-binding::executor-zero::binding-1233"


def _work_cycle_id():
    return (
        "runtime-work-cycle::limited-runtime-session::birth-1209::"
        "runtime-loop-controller::limited-runtime-session::birth-1209::loop-1353::abcd"
    )


def _tick_id():
    return "runtime-execution-tick::limited-runtime-session::birth-1209::tick-1345"


def _bridge(status="bridged", step_request_type="noop_step"):
    return {
        "step_bridge_id": (
            "runtime-step-bridge::limited-runtime-session::birth-1209::"
            "runtime-work-cycle::limited-runtime-session::birth-1209::abcd::ef01"
        ),
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease_id(),
        "capability_grant_id": _grant_id(),
        "executor_binding_id": _binding_id(),
        "work_cycle_id": _work_cycle_id(),
        "execution_tick_id": _tick_id(),
        "step_request_id": (
            "runtime-step-request::limited-runtime-session::birth-1209::"
            "runtime-execution-tick::limited-runtime-session::birth-1209::tick-1345::"
            f"{step_request_type}::1234"
        ),
        "step_request_type": step_request_type,
        "bridge_status": status,
        "record_only": True,
        "bridge_only": True,
        "step_executed": False,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def _request(**overrides):
    request = build_runtime_step_result_commit_request(
        step_result_commit_request_id="runtime-step-result-commit-1377",
        runtime_session_id=_session_id(),
        execution_lease_id=_lease_id(),
        capability_grant_id=_grant_id(),
        executor_binding_id=_binding_id(),
        work_cycle_id=_work_cycle_id(),
        execution_tick_id=_tick_id(),
        step_bridge=_bridge(),
        result_kind="noop",
        result_summary="caller supplied noop evidence",
        failure_reason="none",
        progress_delta={"steps_recorded": 1},
        commit_time="deterministic-time::1377",
    )
    request.update(overrides)
    return request


def test_1377_no_step_bridge_blocks_commit():
    validation = validate_runtime_step_result_commit_request(_request(step_bridge={}))

    assert validation["result_status"] == "blocked"
    assert "missing_step_bridge" in validation["problems"]


def test_1378_denied_bridge_blocks_commit():
    record = build_runtime_step_result_commit_record(
        _request(step_bridge=_bridge("denied"))
    )

    assert record["result_status"] == "denied"
    assert "denied_step_bridge" in record["denial_reason"]


def test_1378_blocked_bridge_blocks_commit():
    record = build_runtime_step_result_commit_record(
        _request(step_bridge=_bridge("blocked"))
    )

    assert record["result_status"] == "blocked"
    assert "blocked_step_bridge" in record["denial_reason"]


def test_1379_expired_or_revoked_bridge_blocks_commit():
    expired = build_runtime_step_result_commit_record(
        _request(step_bridge=_bridge("expired"))
    )
    revoked = build_runtime_step_result_commit_record(
        _request(step_bridge=_bridge("revoked"))
    )

    assert expired["result_status"] == "blocked"
    assert "expired_step_bridge" in expired["denial_reason"]
    assert revoked["result_status"] == "blocked"
    assert "revoked_step_bridge" in revoked["denial_reason"]


def test_1380_bridged_noop_result_creates_commit_record():
    record = build_runtime_step_result_commit_record(_request())

    assert record["step_result_commit_id"].startswith("runtime-step-result-commit::")
    assert record["step_bridge_id"] == _bridge()["step_bridge_id"]
    assert record["step_request_id"] == _bridge()["step_request_id"]
    assert record["result_status"] == "committed"
    assert record["result_kind"] == "noop"
    assert record["result_evidence_only"] is True


def test_1381_bridged_result_kinds_are_accepted_as_evidence_only():
    kinds = ("read_result", "write_result", "mutation_result", "recovery_result")
    records = [
        build_runtime_step_result_commit_record(
            _request(
                step_bridge=_bridge("bridged", kind.replace("_result", "_step")),
                result_kind=kind,
                result_summary=f"caller supplied {kind} evidence",
            )
        )
        for kind in kinds
    ]

    assert [record["result_kind"] for record in records] == list(kinds)
    assert [record["result_evidence_only"] for record in records] == [True] * 4
    assert records[0]["result_status"] == "committed"
    assert records[1]["result_status"] == "committed"
    assert records[2]["result_status"] == "committed"
    assert records[3]["result_status"] == "recovery_required"


def test_1381_failure_result_preserves_failure_reason():
    record = build_runtime_step_result_commit_record(
        _request(
            result_kind="failure_result",
            result_summary="caller supplied failure evidence",
            failure_reason="step_evidence_reported_failure",
        )
    )

    assert record["result_status"] == "failed"
    assert record["failure_reason"] == "step_evidence_reported_failure"


def test_1382_recovery_required_result_sets_recovery_required_true():
    record = build_runtime_step_result_commit_record(
        _request(result_kind="recovery_result", recovery_required=True)
    )

    assert record["result_status"] == "recovery_required"
    assert record["recovery_required"] is True


def test_1382_commit_does_not_execute_step():
    record = build_runtime_step_result_commit_record(_request())
    completion = can_runtime_step_result_commit_complete_task(record)

    assert record["step_executed"] is False
    assert completion["can_execute_step"] is False
    assert completion["can_run_executor"] is False


def test_1383_commit_does_not_invoke_tools():
    record = build_runtime_step_result_commit_record(_request())
    completion = can_runtime_step_result_commit_complete_task(record)

    assert record["tool_invoked"] is False
    assert completion["can_invoke_tools"] is False


def test_1383_commit_does_not_mutate_filesystem():
    record = build_runtime_step_result_commit_record(_request())
    completion = can_runtime_step_result_commit_complete_task(record)

    assert record["filesystem_mutation_performed"] is False
    assert record["filesystem_write_performed"] is False
    assert completion["can_mutate_filesystem"] is False


def test_1384_commit_does_not_mark_task_complete_directly():
    record = build_runtime_step_result_commit_record(
        _request(task_completion_candidate=True)
    )
    completion = can_runtime_step_result_commit_complete_task(record)

    assert record["task_completion_candidate"] is True
    assert record["task_completed"] is False
    assert record["task_marked_complete"] is False
    assert completion["can_complete_task"] is False
    assert completion["can_mark_task_complete"] is False


def test_1384_audit_projection_deterministic():
    first = build_runtime_step_result_commit_audit_projection(
        build_runtime_step_result_commit_record(_request())
    )
    second = build_runtime_step_result_commit_audit_projection(
        build_runtime_step_result_commit_record(_request())
    )

    assert first == second
    assert first["projection_only"] is True
    assert first["committed_evidence_only"] is True
    assert first["step_executed"] is False
    assert first["task_marked_complete"] is False
