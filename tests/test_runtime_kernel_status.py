from __future__ import annotations

from core.planning.planner_contract_trace import trace_planner_contract_payload
from core.tasks.execution_contract_trace import trace_execution_contract_payload
from core.tasks.runtime_kernel_status import (
    RUNTIME_KERNEL_STATUS_VERSION,
    build_runtime_kernel_status,
    build_task_runtime_kernel_status,
    format_runtime_kernel_status,
    format_task_runtime_kernel_status,
)


def test_runtime_kernel_status_reports_no_trace_when_empty(tmp_path):
    planner_trace = tmp_path / "planner.jsonl"
    execution_trace = tmp_path / "execution.jsonl"

    status = build_runtime_kernel_status(
        planner_trace_path=planner_trace,
        execution_trace_path=execution_trace,
    )

    assert status["ok"] is True
    assert status["version"] == RUNTIME_KERNEL_STATUS_VERSION
    assert status["kernel"]["status"] == "no_trace"
    assert status["kernel"]["total_events"] == 0
    assert status["planner"]["event_count"] == 0
    assert status["execution"]["event_count"] == 0
    assert status["events"]["event_count"] == 0
    assert status["timeline"]["event_count"] == 0


def test_runtime_kernel_status_reports_healthy_when_traces_are_clean(tmp_path):
    planner_trace = tmp_path / "planner.jsonl"
    execution_trace = tmp_path / "execution.jsonl"

    trace_planner_contract_payload(
        event="planner_contract_checked",
        payload={
            "action": "write_file",
            "is_valid": True,
            "planner_gateway_ok": True,
            "contract_errors": [],
            "contract_warnings": [],
        },
        trace_path=planner_trace,
    )
    trace_execution_contract_payload(
        event="execution_gateway_completed",
        step={
            "type": "write_file",
            "is_valid": True,
            "execution_gateway_ok": True,
            "contract_errors": [],
            "contract_warnings": [],
        },
        result={
            "ok": True,
            "action": "write_file",
        },
        trace_path=execution_trace,
    )

    status = build_runtime_kernel_status(
        planner_trace_path=planner_trace,
        execution_trace_path=execution_trace,
    )

    assert status["ok"] is True
    assert status["kernel"]["status"] == "healthy"
    assert status["kernel"]["total_events"] == 2
    assert status["kernel"]["total_invalid"] == 0
    assert status["kernel"]["total_errors"] == 0
    assert status["kernel"]["planner_event_count"] == 1
    assert status["kernel"]["execution_event_count"] == 1
    assert status["events"]["event_count"] == 2
    assert status["events"]["by_source"]["planner"] == 1
    assert status["events"]["by_source"]["execution"] == 1
    assert status["timeline"]["event_count"] == 2
    assert status["timeline"]["first_event"]["source"] == "planner"
    assert status["timeline"]["latest_event"]["source"] == "execution"


def test_runtime_kernel_status_reports_attention_required_for_invalid_events(tmp_path):
    planner_trace = tmp_path / "planner.jsonl"
    execution_trace = tmp_path / "execution.jsonl"

    trace_planner_contract_payload(
        event="planner_contract_violation",
        payload={
            "action": "write_file",
            "is_valid": False,
            "contract_errors": ["write_file:missing_target_path"],
            "contract_warnings": [],
        },
        trace_path=planner_trace,
    )
    trace_execution_contract_payload(
        event="execution_step_rejected",
        step={
            "type": "write_file",
            "is_valid": False,
            "contract_errors": ["write_file:missing_path"],
            "contract_warnings": [],
        },
        result={
            "ok": False,
            "action": "execution_step_rejected",
            "error": "write_file:missing_path",
        },
        trace_path=execution_trace,
    )

    status = build_runtime_kernel_status(
        planner_trace_path=planner_trace,
        execution_trace_path=execution_trace,
    )

    assert status["ok"] is True
    assert status["kernel"]["status"] == "attention_required"
    assert status["kernel"]["total_events"] == 2
    assert status["kernel"]["total_invalid"] == 2
    assert status["kernel"]["total_errors"] >= 2


def test_format_runtime_kernel_status_outputs_readable_summary(tmp_path):
    planner_trace = tmp_path / "planner.jsonl"
    execution_trace = tmp_path / "execution.jsonl"

    trace_planner_contract_payload(
        event="planner_contract_checked",
        payload={
            "action": "noop",
            "is_valid": True,
            "contract_errors": [],
            "contract_warnings": ["noop"],
        },
        trace_path=planner_trace,
    )

    status = build_runtime_kernel_status(
        planner_trace_path=planner_trace,
        execution_trace_path=execution_trace,
    )

    text = format_runtime_kernel_status(status)

    assert "Runtime Kernel Status:" in text
    assert "planner events:" in text
    assert "execution events:" in text
    assert "total warnings:" in text


def test_task_runtime_kernel_status_formats_safe_no_trace_fallback(tmp_path):
    task = {
        "task_id": "task-no-trace",
        "status": "running",
        "current_step_index": 0,
        "steps": [{"type": "write_file", "description": "write report"}],
    }

    status = build_task_runtime_kernel_status(
        task,
        planner_trace_path=tmp_path / "missing_planner.jsonl",
        execution_trace_path=tmp_path / "missing_execution.jsonl",
    )
    text = format_task_runtime_kernel_status(status)

    assert status["kernel"]["status"] == "no_trace"
    assert status["task"]["latest_runtime_step"] == "write report"
    assert "Runtime Kernel Status: no_trace" in text
    assert "unresolved blockers: 0" in text
    assert "blocked reason: none" in text
    assert "latest runtime step: write report" in text


def test_task_runtime_kernel_status_keeps_blocked_reason_and_blockers(tmp_path):
    task = {
        "task_id": "task-blocked",
        "status": "blocked",
        "blocked_reason": "waiting for review",
        "unresolved_blockers": [{"reason": "dependency unmet"}],
        "current_step": {"title": "apply patch"},
    }

    status = build_task_runtime_kernel_status(
        task,
        planner_trace_path=tmp_path / "planner.jsonl",
        execution_trace_path=tmp_path / "execution.jsonl",
    )
    text = format_task_runtime_kernel_status(status)

    assert status["task"]["blocked_reason"] == "waiting for review"
    assert status["task"]["unresolved_blockers"] == ["dependency unmet", "waiting for review"]
    assert "unresolved blockers: 2" in text
    assert "blocked reason: waiting for review" in text
    assert "latest runtime step: apply patch" in text


def test_task_runtime_kernel_status_is_stable_for_terminal_statuses(tmp_path):
    cases = [
        (
            "failed",
            {
                "status": "failed",
                "last_step_result": {"step": {"description": "verify output"}, "error": "boom"},
            },
            "verify output",
        ),
        (
            "finished",
            {
                "status": "finished",
                "current_step_index": 99,
                "steps": [{"description": "prepare"}, {"description": "finalize"}],
            },
            "finalize",
        ),
        (
            "running",
            {
                "status": "running",
                "execution_trace": [{"event_type": "step_started", "step": {"type": "run_command"}}],
            },
            "run_command",
        ),
    ]

    for name, task, expected_step in cases:
        status = build_task_runtime_kernel_status(
            task,
            planner_trace_path=tmp_path / f"{name}_planner.jsonl",
            execution_trace_path=tmp_path / f"{name}_execution.jsonl",
        )
        text = format_task_runtime_kernel_status(status)

        assert status["task"]["status"] == name
        assert status["task"]["latest_runtime_step"] == expected_step
        assert f"latest runtime step: {expected_step}" in text
