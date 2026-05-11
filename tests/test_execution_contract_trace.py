from __future__ import annotations

import json

from core.tasks.execution_contract_trace import (
    build_execution_contract_trace_event,
    load_execution_contract_trace,
    summarize_execution_contract_trace,
    trace_execution_contract_payload,
    write_execution_contract_trace_event,
)


def test_build_trace_event_from_valid_execution_step():
    event = build_execution_contract_trace_event(
        event="execution_contract_checked",
        source="unit_test",
        step={
            "contract_version": "execution_contract.v1",
            "type": "write_file",
            "path": "workspace/shared/out.txt",
            "target_path": "workspace/shared/out.txt",
            "content": "hello",
            "is_valid": True,
            "execution_adapter_ok": True,
            "execution_runtime_entry_step_ok": True,
            "execution_runtime_entry_invoked": True,
            "execution_runtime_entry_ok": True,
            "metadata": {"attempt": 1, "unsafe": object()},
        },
        result={
            "ok": True,
            "action": "write_file",
        },
    )

    assert event["event"] == "execution_contract_checked"
    assert event["ok"] is True
    assert event["source"] == "unit_test"
    assert event["type"] == "write_file"
    assert event["action"] == "write_file"
    assert event["target_path"] == "workspace/shared/out.txt"
    assert event["contract_version"] == "execution_contract.v1"
    assert event["execution_adapter_ok"] is True
    assert event["execution_runtime_entry_invoked"] is True
    assert event["execution_runtime_entry_ok"] is True
    assert event["metadata"] == {"attempt": 1}


def test_build_trace_event_from_invalid_execution_step():
    event = build_execution_contract_trace_event(
        event="execution_step_rejected",
        step={
            "type": "write_file",
            "is_valid": False,
            "contract_errors": ["write_file:missing_path"],
            "contract_warnings": ["write_file:empty_content"],
            "execution_runtime_entry_invoked": False,
            "execution_runtime_entry_ok": False,
        },
        result={
            "ok": False,
            "action": "execution_step_rejected",
            "error": "write_file:missing_path",
        },
    )

    assert event["ok"] is False
    assert event["is_valid"] is False
    assert event["type"] == "write_file"
    assert event["action"] == "execution_step_rejected"
    assert event["contract_errors"] == ["write_file:missing_path"]
    assert event["contract_warnings"] == ["write_file:empty_content"]
    assert event["result_error"] == "write_file:missing_path"


def test_write_trace_event_to_jsonl(tmp_path):
    trace_path = tmp_path / "execution_trace.jsonl"
    event = build_execution_contract_trace_event(
        event="execution_contract_checked",
        step={"type": "noop", "is_valid": True},
        result={"ok": True, "action": "noop"},
    )

    written = write_execution_contract_trace_event(event, trace_path=trace_path)

    assert written == str(trace_path)
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    loaded = json.loads(lines[0])
    assert loaded["event"] == "execution_contract_checked"
    assert loaded["type"] == "noop"


def test_trace_execution_contract_payload_builds_and_writes(tmp_path):
    trace_path = tmp_path / "execution_trace.jsonl"

    event = trace_execution_contract_payload(
        event="execution_invocation_failed",
        source="scheduler",
        step={
            "type": "read_file",
            "path": "workspace/shared/input.txt",
            "execution_runtime_entry_ok": False,
            "execution_runtime_entry_error": "boom",
        },
        result={
            "ok": False,
            "action": "execution_invocation_failed",
            "error": "boom",
        },
        trace_path=trace_path,
    )

    assert event["event"] == "execution_invocation_failed"
    assert event["trace_path"] == str(trace_path)
    assert event["ok"] is False
    assert event["result_error"] == "boom"

    loaded_events = load_execution_contract_trace(trace_path=trace_path)
    assert len(loaded_events) == 1
    assert loaded_events[0]["event"] == "execution_invocation_failed"


def test_load_trace_respects_limit(tmp_path):
    trace_path = tmp_path / "execution_trace.jsonl"

    for idx in range(5):
        trace_execution_contract_payload(
            event=f"event_{idx}",
            step={"type": "noop"},
            result={"ok": True, "action": "noop"},
            trace_path=trace_path,
        )

    loaded = load_execution_contract_trace(trace_path=trace_path, limit=2)

    assert len(loaded) == 2
    assert loaded[0]["event"] == "event_3"
    assert loaded[1]["event"] == "event_4"


def test_summarize_trace_counts_invalid_rejected_invocation_noop_errors_warnings():
    summary = summarize_execution_contract_trace(
        [
            {
                "ok": True,
                "is_valid": True,
                "type": "write_file",
                "action": "write_file",
                "contract_errors": [],
                "contract_warnings": [],
            },
            {
                "ok": False,
                "is_valid": False,
                "type": "write_file",
                "action": "execution_step_rejected",
                "contract_errors": ["missing"],
                "contract_warnings": ["empty"],
                "result_error": "missing",
            },
            {
                "ok": False,
                "is_valid": True,
                "type": "read_file",
                "action": "execution_invocation_failed",
                "contract_errors": [],
                "contract_warnings": [],
                "result_error": "boom",
            },
            {
                "ok": True,
                "is_valid": True,
                "type": "noop",
                "action": "noop",
                "contract_errors": [],
                "contract_warnings": ["noop"],
            },
        ]
    )

    assert summary["ok"] is True
    assert summary["event_count"] == 4
    assert summary["invalid_count"] == 2
    assert summary["rejected_count"] == 1
    assert summary["invocation_failed_count"] == 1
    assert summary["noop_count"] == 1
    assert summary["error_count"] == 3
    assert summary["warning_count"] == 2


def test_summarize_rejects_non_list_input():
    summary = summarize_execution_contract_trace({"bad": "input"})

    assert summary["ok"] is False
    assert summary["event_count"] == 0