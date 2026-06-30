from __future__ import annotations

import inspect

from core.runtime.aer_operator_audit_reader import (
    AER_OPERATOR_AUDIT_VIEW_CONTRACT,
    build_audit_summary,
    build_audit_view,
    load_operator_timeline,
    validate_audit_view,
)
import core.runtime.aer_operator_audit_reader as audit_reader_module
from core.runtime.aer_operator_checkpoint import build_operator_checkpoint
from core.runtime.aer_operator_checkpoint_store import save_checkpoint
from core.runtime.aer_operator_event_log import append_operator_event, build_operator_event


def test_load_operator_timeline_returns_events_in_append_order_without_sorting(tmp_path) -> None:
    first = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-87",
        event_type="operator.running",
        phase="running",
        sequence=5,
    )
    second = build_operator_event(
        event_id="event-2",
        operator_session_id="operator-session-1",
        package_id="package-87",
        event_type="operator.checkpointed",
        phase="checkpointed",
        sequence=6,
    )
    append_operator_event(str(tmp_path), first)
    append_operator_event(str(tmp_path), second)

    timeline = load_operator_timeline(str(tmp_path))

    assert [entry["kind"] for entry in timeline] == ["event", "event"]
    assert [entry["event"]["event_id"] for entry in timeline] == ["event-1", "event-2"]


def test_load_operator_timeline_does_not_discover_checkpoints_from_event_payloads(tmp_path) -> None:
    event = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-87",
        event_type="operator.checkpointed",
        phase="checkpointed",
        metadata={"checkpoint_id": "checkpoint-1"},
        sequence=0,
    )
    append_operator_event(str(tmp_path), event)

    timeline = load_operator_timeline(str(tmp_path))

    assert timeline == [{"kind": "event", "event": event}]


def test_load_operator_timeline_filters_events_by_identity(tmp_path) -> None:
    event_a = build_operator_event(
        event_id="event-a",
        operator_session_id="operator-session-1",
        package_id="package-87",
        event_type="operator.checkpointed",
        metadata={"checkpoint_id": "checkpoint-a"},
        sequence=0,
    )
    event_b = build_operator_event(
        event_id="event-b",
        operator_session_id="operator-session-2",
        package_id="package-87",
        event_type="operator.checkpointed",
        metadata={"checkpoint_id": "checkpoint-b"},
        sequence=1,
    )
    append_operator_event(str(tmp_path), event_a)
    append_operator_event(str(tmp_path), event_b)

    timeline = load_operator_timeline(str(tmp_path), operator_session_id="operator-session-1")

    assert timeline == [{"kind": "event", "event": event_a}]


def test_build_audit_summary_uses_only_allowed_fields() -> None:
    first = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-87",
        event_type="operator.running",
        phase="running",
        sequence=2,
    )
    second = build_operator_event(
        event_id="event-2",
        operator_session_id="operator-session-1",
        package_id="package-87",
        event_type="operator.completed",
        phase="completed",
        sequence=8,
    )
    checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-1",
        operator_session_id="operator-session-1",
        package_id="package-87",
    )
    timeline = [
        {"kind": "event", "event": first},
        {"kind": "checkpoint", "checkpoint": checkpoint},
        {"kind": "event", "event": second},
    ]

    summary = build_audit_summary(timeline)

    assert summary == {
        "operator_session_id": "operator-session-1",
        "package_id": "package-87",
        "checkpoint_found": True,
        "checkpoint_count": 1,
        "event_count": 2,
        "first_sequence": 2,
        "last_sequence": 8,
        "first_event": first,
        "last_event": second,
    }
    for forbidden in (
        "failure_reason",
        "approval_status",
        "issue_status",
        "operator_health",
        "risk",
        "severity",
    ):
        assert forbidden not in summary


def test_build_audit_view_returns_required_shape_without_checkpoint_snapshot(tmp_path) -> None:
    event = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-87",
        event_type="operator.checkpointed",
        metadata={"checkpoint_id": "checkpoint-1"},
        sequence=0,
    )
    append_operator_event(str(tmp_path), event)

    audit_view = build_audit_view(str(tmp_path), operator_session_id="operator-session-1")

    assert audit_view["contract"] == AER_OPERATOR_AUDIT_VIEW_CONTRACT
    assert audit_view["checkpoint"] is None
    assert audit_view["events"] == [event]
    assert audit_view["timeline"] == [{"kind": "event", "event": event}]
    assert audit_view["summary"]["checkpoint_found"] is False
    assert audit_view["summary"]["checkpoint_count"] == 0
    assert audit_view["summary"]["event_count"] == 1
    assert validate_audit_view(audit_view)["ok"] is True


def test_build_audit_view_prepends_latest_checkpoint_snapshot_from_store_index(tmp_path) -> None:
    older_checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-a",
        operator_session_id="operator-session-1",
        package_id="package-89",
        phase="running",
    )
    latest_checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-z",
        operator_session_id="operator-session-1",
        package_id="package-89",
        phase="checkpointed",
    )
    other_checkpoint = build_operator_checkpoint(
        checkpoint_id="checkpoint-other",
        operator_session_id="operator-session-2",
        package_id="package-89",
    )
    event = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-89",
        event_type="operator.checkpointed",
        metadata={"checkpoint_id": "not-used-for-discovery"},
        sequence=0,
    )
    save_checkpoint(str(tmp_path), latest_checkpoint)
    save_checkpoint(str(tmp_path), older_checkpoint)
    save_checkpoint(str(tmp_path), other_checkpoint)
    append_operator_event(str(tmp_path), event)

    audit_view = build_audit_view(
        str(tmp_path),
        operator_session_id="operator-session-1",
        package_id="package-89",
    )

    assert audit_view["checkpoint"] == latest_checkpoint
    assert audit_view["events"] == [event]
    assert audit_view["timeline"] == [
        {"kind": "checkpoint", "checkpoint": latest_checkpoint},
        {"kind": "event", "event": event},
    ]
    assert audit_view["summary"]["checkpoint_found"] is True
    assert audit_view["summary"]["checkpoint_count"] == 2
    assert audit_view["summary"]["event_count"] == 1
    assert validate_audit_view(audit_view)["ok"] is True


def test_build_audit_view_does_not_modify_source_payloads(tmp_path) -> None:
    event = build_operator_event(
        event_id="event-1",
        operator_session_id="operator-session-1",
        package_id="package-87",
        event_type="operator.checkpointed",
        metadata={"checkpoint_id": "checkpoint-1", "nested": {"value": "original"}},
        sequence=0,
    )
    append_operator_event(str(tmp_path), event)

    audit_view = build_audit_view(str(tmp_path))
    audit_view["events"][0]["metadata"]["nested"]["value"] = "mutated"
    audit_view["timeline"][0]["event"]["metadata"]["nested"]["value"] = "mutated"

    fresh_view = build_audit_view(str(tmp_path))

    assert fresh_view["checkpoint"] is None
    assert fresh_view["events"] == [event]
    assert fresh_view["timeline"][0]["event"] == event


def test_validate_audit_view_rejects_invalid_shape_and_forbidden_summary_fields() -> None:
    assert "audit_view must be a dict" in validate_audit_view(None)["errors"]

    audit_view = {
        "contract": "wrong.contract",
        "checkpoint": [],
        "events": {},
        "timeline": {},
        "summary": {
            "operator_session_id": "",
            "package_id": "",
            "checkpoint_found": False,
            "checkpoint_count": 0,
            "event_count": 0,
            "first_sequence": None,
            "last_sequence": None,
            "first_event": {},
            "last_event": {},
            "severity": "high",
        },
    }

    result = validate_audit_view(audit_view)

    assert result["ok"] is False
    assert "invalid contract" in result["errors"]
    assert "checkpoint must be a dict or None" in result["errors"]
    assert "events must be a list" in result["errors"]
    assert "timeline must be a list" in result["errors"]
    assert "unexpected summary field: severity" in result["errors"]


def test_audit_reader_uses_only_published_read_apis_for_composition() -> None:
    source = inspect.getsource(audit_reader_module)

    assert "load_operator_events" in source
    assert "load_checkpoints_for_identity" in source
    assert "latest_checkpoint_for_identity" in source

    forbidden = (
        "load_checkpoint(",
        "list_checkpoints(",
        "save_checkpoint(",
        "delete_checkpoint(",
        "append_operator_event(",
        "delete_operator_event(",
        "update_operator_event(",
        "resume_from(",
        "Scheduler(",
        "TaskRunner(",
        "approval",
        "issue_report",
        "operator_loop",
        "transition",
        "sort(",
        "sorted(",
    )
    for token in forbidden:
        assert token not in source
