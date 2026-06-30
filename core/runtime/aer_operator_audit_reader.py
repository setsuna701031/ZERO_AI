from __future__ import annotations

import copy
from typing import Any, Dict, List

from core.runtime.aer_operator_event_log import load_operator_events

AER_OPERATOR_AUDIT_VIEW_CONTRACT = "aer.operator_audit_view.v2"

AUDIT_VIEW_REQUIRED_FIELDS = (
    "contract",
    "checkpoint",
    "events",
    "timeline",
    "summary",
)

SUMMARY_ALLOWED_FIELDS = (
    "operator_session_id",
    "package_id",
    "checkpoint_count",
    "event_count",
    "first_sequence",
    "last_sequence",
    "first_event",
    "last_event",
)


def load_operator_timeline(
    workspace_root: str,
    operator_session_id: str | None = None,
    package_id: str | None = None,
) -> List[dict]:
    events = load_operator_events(
        workspace_root,
        operator_session_id=operator_session_id,
        package_id=package_id,
    )
    timeline: List[dict] = []

    for event in events:
        event_copy = copy.deepcopy(dict(event))
        timeline.append(
            {
                "kind": "event",
                "event": event_copy,
            }
        )

    return timeline


def build_audit_summary(timeline: List[dict]) -> Dict[str, Any]:
    events = [
        copy.deepcopy(dict(entry.get("event") or {}))
        for entry in timeline
        if isinstance(entry, dict) and entry.get("kind") == "event"
    ]
    checkpoints = [
        copy.deepcopy(dict(entry.get("checkpoint") or {}))
        for entry in timeline
        if isinstance(entry, dict) and entry.get("kind") == "checkpoint"
    ]

    first_event = events[0] if events else {}
    last_event = events[-1] if events else {}

    return {
        "operator_session_id": str(first_event.get("operator_session_id") or ""),
        "package_id": str(first_event.get("package_id") or ""),
        "checkpoint_count": len(checkpoints),
        "event_count": len(events),
        "first_sequence": first_event.get("sequence") if events else None,
        "last_sequence": last_event.get("sequence") if events else None,
        "first_event": copy.deepcopy(first_event),
        "last_event": copy.deepcopy(last_event),
    }


def build_audit_view(
    workspace_root: str,
    operator_session_id: str | None = None,
    package_id: str | None = None,
) -> Dict[str, Any]:
    timeline = load_operator_timeline(
        workspace_root,
        operator_session_id=operator_session_id,
        package_id=package_id,
    )
    events = [
        copy.deepcopy(dict(entry.get("event") or {}))
        for entry in timeline
        if isinstance(entry, dict) and entry.get("kind") == "event"
    ]
    checkpoints = [
        copy.deepcopy(dict(entry.get("checkpoint") or {}))
        for entry in timeline
        if isinstance(entry, dict) and entry.get("kind") == "checkpoint"
    ]
    checkpoint = checkpoints[-1] if checkpoints else {}
    summary = build_audit_summary(timeline)

    return {
        "contract": AER_OPERATOR_AUDIT_VIEW_CONTRACT,
        "checkpoint": copy.deepcopy(checkpoint),
        "events": copy.deepcopy(events),
        "timeline": copy.deepcopy(timeline),
        "summary": copy.deepcopy(summary),
    }


def validate_audit_view(audit_view: Any) -> Dict[str, Any]:
    errors = []

    if not isinstance(audit_view, dict):
        return {
            "ok": False,
            "contract": AER_OPERATOR_AUDIT_VIEW_CONTRACT,
            "errors": ["audit_view must be a dict"],
        }

    for field in AUDIT_VIEW_REQUIRED_FIELDS:
        if field not in audit_view:
            errors.append(f"missing required field: {field}")

    if audit_view.get("contract") != AER_OPERATOR_AUDIT_VIEW_CONTRACT:
        errors.append("invalid contract")

    if not isinstance(audit_view.get("checkpoint"), dict):
        errors.append("checkpoint must be a dict")

    if not isinstance(audit_view.get("events"), list):
        errors.append("events must be a list")

    if not isinstance(audit_view.get("timeline"), list):
        errors.append("timeline must be a list")

    summary = audit_view.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be a dict")
    else:
        for field in SUMMARY_ALLOWED_FIELDS:
            if field not in summary:
                errors.append(f"missing summary field: {field}")
        for field in summary:
            if field not in SUMMARY_ALLOWED_FIELDS:
                errors.append(f"unexpected summary field: {field}")

    return {
        "ok": not errors,
        "contract": AER_OPERATOR_AUDIT_VIEW_CONTRACT,
        "errors": errors,
    }
