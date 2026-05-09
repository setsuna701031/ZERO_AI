from __future__ import annotations

import json

from core.planning.planner_contract_trace import (
    build_planner_contract_trace_event,
    load_planner_contract_trace,
    summarize_planner_contract_trace,
    trace_planner_contract_payload,
    write_planner_contract_trace_event,
)


def test_build_trace_event_from_valid_payload():
    event = build_planner_contract_trace_event(
        event="planner_contract_checked",
        source="unit_test",
        payload={
            "contract_version": "planner_contract.v1",
            "action": "write_file",
            "raw_action": "write",
            "goal": "write output",
            "target_path": "workspace/shared/out.txt",
            "is_valid": True,
            "adapter_ok": True,
            "runtime_entry_ok": True,
            "planner_gateway_ok": True,
            "metadata": {"attempt": 1, "unsafe": object()},
        },
    )

    assert event["event"] == "planner_contract_checked"
    assert event["ok"] is True
    assert event["source"] == "unit_test"
    assert event["action"] == "write_file"
    assert event["raw_action"] == "write"
    assert event["target_path"] == "workspace/shared/out.txt"
    assert event["contract_version"] == "planner_contract.v1"
    assert event["adapter_ok"] is True
    assert event["runtime_entry_ok"] is True
    assert event["planner_gateway_ok"] is True
    assert event["metadata"] == {"attempt": 1}


def test_build_trace_event_from_invalid_payload():
    event = build_planner_contract_trace_event(
        event="planner_contract_violation",
        payload={
            "action": "write_file",
            "is_valid": False,
            "contract_errors": ["write_file:missing_target_path"],
            "contract_warnings": ["write_file:empty_content"],
        },
    )

    assert event["ok"] is False
    assert event["is_valid"] is False
    assert event["action"] == "write_file"
    assert event["contract_errors"] == ["write_file:missing_target_path"]
    assert event["contract_warnings"] == ["write_file:empty_content"]


def test_write_trace_event_to_jsonl(tmp_path):
    trace_path = tmp_path / "planner_trace.jsonl"
    event = build_planner_contract_trace_event(
        event="planner_contract_checked",
        payload={"action": "noop", "is_valid": True},
    )

    written = write_planner_contract_trace_event(event, trace_path=trace_path)

    assert written == str(trace_path)
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    loaded = json.loads(lines[0])
    assert loaded["event"] == "planner_contract_checked"
    assert loaded["action"] == "noop"


def test_trace_planner_contract_payload_builds_and_writes(tmp_path):
    trace_path = tmp_path / "planner_trace.jsonl"

    event = trace_planner_contract_payload(
        event="planner_gateway_fallback",
        source="scheduler",
        payload={
            "action": "noop",
            "reason": "legacy fallback",
            "scheduler_planner_legacy_fallback_used": True,
            "contract_warnings": ["fallback_used"],
        },
        trace_path=trace_path,
    )

    assert event["event"] == "planner_gateway_fallback"
    assert event["trace_path"] == str(trace_path)
    assert event["scheduler_planner_legacy_fallback_used"] is True

    loaded_events = load_planner_contract_trace(trace_path=trace_path)
    assert len(loaded_events) == 1
    assert loaded_events[0]["event"] == "planner_gateway_fallback"


def test_load_trace_respects_limit(tmp_path):
    trace_path = tmp_path / "planner_trace.jsonl"

    for idx in range(5):
        trace_planner_contract_payload(
            event=f"event_{idx}",
            payload={"action": "noop"},
            trace_path=trace_path,
        )

    loaded = load_planner_contract_trace(trace_path=trace_path, limit=2)

    assert len(loaded) == 2
    assert loaded[0]["event"] == "event_3"
    assert loaded[1]["event"] == "event_4"


def test_summarize_trace_counts_invalid_fallback_noop_errors_warnings():
    summary = summarize_planner_contract_trace(
        [
            {
                "ok": True,
                "is_valid": True,
                "action": "write_file",
                "contract_errors": [],
                "contract_warnings": [],
            },
            {
                "ok": False,
                "is_valid": False,
                "action": "noop",
                "scheduler_planner_legacy_fallback_used": True,
                "contract_errors": ["missing"],
                "contract_warnings": ["fallback"],
            },
            {
                "ok": True,
                "is_valid": True,
                "action": "noop",
                "contract_errors": [],
                "contract_warnings": ["unknown_action"],
            },
        ]
    )

    assert summary["ok"] is True
    assert summary["event_count"] == 3
    assert summary["invalid_count"] == 1
    assert summary["fallback_count"] == 1
    assert summary["noop_count"] == 2
    assert summary["error_count"] == 1
    assert summary["warning_count"] == 2


def test_summarize_rejects_non_list_input():
    summary = summarize_planner_contract_trace({"bad": "input"})

    assert summary["ok"] is False
    assert summary["event_count"] == 0