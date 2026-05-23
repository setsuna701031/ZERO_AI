from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "governed_runtime_execution_session.v1"

SESSION_CREATED = "created"
SESSION_PREPARED = "prepared"
SESSION_RUNNING = "running"
SESSION_CHECKPOINTED = "checkpointed"
SESSION_REVIEW_REQUIRED = "review_required"
SESSION_BLOCKED = "blocked"
SESSION_SEALED = "sealed"
SESSION_ROLLED_BACK = "rolled_back"
SESSION_FAILED = "failed"

SESSION_STATES: tuple[str, ...] = (
    SESSION_CREATED,
    SESSION_PREPARED,
    SESSION_RUNNING,
    SESSION_CHECKPOINTED,
    SESSION_REVIEW_REQUIRED,
    SESSION_BLOCKED,
    SESSION_SEALED,
    SESSION_ROLLED_BACK,
    SESSION_FAILED,
)

TERMINAL_SESSION_STATES: tuple[str, ...] = (
    SESSION_BLOCKED,
    SESSION_SEALED,
    SESSION_ROLLED_BACK,
    SESSION_FAILED,
)

SESSION_REQUIRED_FIELDS: tuple[str, ...] = (
    "execution_session_id",
    "session_state",
    "source_execution_id",
    "source_gateway_id",
    "source_boundary_id",
    "event_timeline",
    "checkpoint_snapshots",
    "replay_order_valid",
    "rollback_eligible",
    "seal_handoff_ready",
    "continuation_contract",
    "blocking_issues",
    "reason_codes",
)

ALLOWED_SESSION_TRANSITIONS: dict[str, set[str]] = {
    "": {SESSION_CREATED},
    SESSION_CREATED: {SESSION_PREPARED, SESSION_BLOCKED},
    SESSION_PREPARED: {SESSION_RUNNING, SESSION_REVIEW_REQUIRED, SESSION_BLOCKED},
    SESSION_RUNNING: {SESSION_CHECKPOINTED, SESSION_REVIEW_REQUIRED, SESSION_FAILED, SESSION_BLOCKED},
    SESSION_CHECKPOINTED: {SESSION_RUNNING, SESSION_SEALED, SESSION_ROLLED_BACK, SESSION_FAILED, SESSION_BLOCKED},
    SESSION_REVIEW_REQUIRED: {SESSION_RUNNING, SESSION_BLOCKED, SESSION_ROLLED_BACK},
    SESSION_BLOCKED: set(),
    SESSION_SEALED: set(),
    SESSION_ROLLED_BACK: set(),
    SESSION_FAILED: set(),
}


def governed_runtime_execution_session_states() -> List[str]:
    return list(SESSION_STATES)


def governed_runtime_execution_session_required_fields() -> List[str]:
    return list(SESSION_REQUIRED_FIELDS)


def build_governed_runtime_execution_event(
    *,
    event_type: str,
    event_state: str,
    source_ref: str = "",
    payload: Any | None = None,
    sequence: int | None = None,
) -> Dict[str, Any]:
    normalized_sequence = 0 if sequence is None else max(0, int(sequence))
    event = {
        "event_id": "",
        "event_type": _text(event_type),
        "event_state": _text(event_state),
        "source_ref": _text(source_ref),
        "sequence": normalized_sequence,
        "payload": copy.deepcopy(payload) if payload is not None else {},
    }
    event["event_id"] = _event_id(event)
    return event


def build_governed_runtime_execution_checkpoint(
    *,
    checkpoint_type: str,
    checkpoint_state: str,
    source_event_id: str = "",
    runtime_state_ref: str = "",
    sequence: int | None = None,
    payload: Any | None = None,
) -> Dict[str, Any]:
    normalized_sequence = 0 if sequence is None else max(0, int(sequence))
    checkpoint = {
        "checkpoint_id": "",
        "checkpoint_type": _text(checkpoint_type),
        "checkpoint_state": _text(checkpoint_state),
        "source_event_id": _text(source_event_id),
        "runtime_state_ref": _text(runtime_state_ref),
        "sequence": normalized_sequence,
        "payload": copy.deepcopy(payload) if payload is not None else {},
    }
    checkpoint["checkpoint_id"] = _checkpoint_id(checkpoint)
    return checkpoint


def build_governed_runtime_execution_session_report(
    *,
    action_execution_report: Any | None = None,
    boundary_report: Any | None = None,
    gateway_report: Any | None = None,
    previous_session_state: str | None = None,
    event_timeline: Iterable[Any] | None = None,
    checkpoint_snapshots: Iterable[Any] | None = None,
    rollback_report: Any | None = None,
    seal_handoff: Any | None = None,
    continuation_context: Any | None = None,
) -> Dict[str, Any]:
    """Build a deterministic, data-only governed runtime execution session report."""

    action_execution = _mapping(action_execution_report)
    boundary = _mapping(boundary_report)
    gateway = _mapping(gateway_report)

    events = _normalize_events(event_timeline)
    checkpoints = _normalize_checkpoints(checkpoint_snapshots)

    if not events:
        events = _events_from_action_execution(action_execution)

    if not checkpoints and events:
        checkpoints = [
            build_governed_runtime_execution_checkpoint(
                checkpoint_type="execution_start",
                checkpoint_state="captured",
                source_event_id=events[0]["event_id"],
                runtime_state_ref=_text(action_execution.get("governed_action_execution_id")),
                sequence=0,
                payload={
                    "source_execution_id": _text(action_execution.get("governed_action_execution_id")),
                    "source_gateway_id": _text(action_execution.get("source_gateway_id")),
                    "source_boundary_id": _text(action_execution.get("source_boundary_id")),
                },
            )
        ]

    previous = _text(previous_session_state)
    session_state = _derive_session_state(
        action_execution=action_execution,
        boundary=boundary,
        events=events,
        checkpoints=checkpoints,
        rollback_report=rollback_report,
        seal_handoff=seal_handoff,
    )
    transition_valid = _session_transition_valid(previous, session_state)
    replay_order_valid = _replay_order_valid(events, checkpoints)
    rollback_eligible = _rollback_eligible(
        action_execution=action_execution,
        rollback_report=rollback_report,
        checkpoints=checkpoints,
    )
    seal_handoff_ready = _seal_handoff_ready(
        session_state=session_state,
        seal_handoff=seal_handoff,
        checkpoints=checkpoints,
    )
    continuation_contract = _build_continuation_contract(
        session_state=session_state,
        continuation_context=continuation_context,
        events=events,
        checkpoints=checkpoints,
    )

    blocking_issues: List[Dict[str, Any]] = []
    if action_execution_report is None:
        blocking_issues.append({"kind": "action_execution_report_missing"})
    if not transition_valid:
        blocking_issues.append({"kind": "invalid_session_state_transition", "from": previous, "to": session_state})
    if not replay_order_valid:
        blocking_issues.append({"kind": "session_replay_order_invalid"})
    if session_state == SESSION_SEALED and not seal_handoff_ready:
        blocking_issues.append({"kind": "seal_handoff_not_ready"})
    if session_state == SESSION_ROLLED_BACK and not rollback_eligible:
        blocking_issues.append({"kind": "rollback_not_eligible"})
    if _text(boundary.get("boundary_state")) == "blocked":
        blocking_issues.append({"kind": "source_boundary_blocked"})
    if _text(gateway.get("gateway_state")) == "blocked":
        blocking_issues.append({"kind": "source_gateway_blocked"})

    blocking_issues = _dedupe_issues(blocking_issues)

    report = {
        "schema_version": SCHEMA_VERSION,
        "execution_session_id": "",
        "session_state": SESSION_BLOCKED if blocking_issues and session_state not in TERMINAL_SESSION_STATES else session_state,
        "previous_session_state": previous,
        "transition_valid": transition_valid,
        "source_execution_id": _text(action_execution.get("governed_action_execution_id")),
        "source_gateway_id": _text(action_execution.get("source_gateway_id") or gateway.get("gateway_id")),
        "source_boundary_id": _text(action_execution.get("source_boundary_id") or boundary.get("boundary_id")),
        "event_timeline": events,
        "checkpoint_snapshots": checkpoints,
        "replay_order_valid": replay_order_valid,
        "rollback_eligible": rollback_eligible,
        "seal_handoff_ready": seal_handoff_ready,
        "continuation_contract": continuation_contract,
        "blocking_issues": blocking_issues,
        "reason_codes": _sorted_unique(
            [
                *_string_list(action_execution.get("reason_codes")),
                *_string_list(boundary.get("reason_codes")),
                *_string_list(gateway.get("reason_codes")),
                *_reason_codes_from_issues(blocking_issues),
            ]
        ),
        "session_summary": {
            "event_count": len(events),
            "checkpoint_count": len(checkpoints),
            "session_state": SESSION_BLOCKED if blocking_issues and session_state not in TERMINAL_SESSION_STATES else session_state,
            "source_execution_state": _text(action_execution.get("execution_state")),
            "replay_order_valid": replay_order_valid,
            "rollback_eligible": rollback_eligible,
            "seal_handoff_ready": seal_handoff_ready,
        },
    }
    report["execution_session_id"] = _session_id(report)
    return report


def validate_governed_runtime_execution_session_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in SESSION_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []

    if _text(payload.get("session_state")) not in SESSION_STATES:
        invalid_fields.append({"field": "session_state", "reason": "invalid_state"})

    for field in ("event_timeline", "checkpoint_snapshots", "blocking_issues", "reason_codes"):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})

    for field in ("replay_order_valid", "rollback_eligible", "seal_handoff_ready"):
        if field in payload and not isinstance(payload.get(field), bool):
            invalid_fields.append({"field": field, "reason": "expected_bool"})

    if "continuation_contract" in payload and not isinstance(payload.get("continuation_contract"), dict):
        invalid_fields.append({"field": "continuation_contract", "reason": "expected_dict"})

    for index, event in enumerate(payload.get("event_timeline", []) if isinstance(payload.get("event_timeline"), list) else []):
        if not isinstance(event, dict):
            invalid_fields.append({"field": "event_timeline", "index": index, "reason": "expected_dict"})
            continue
        for field in ("event_id", "event_type", "event_state", "sequence"):
            if field not in event:
                invalid_fields.append({"field": "event_timeline", "index": index, "reason": f"missing_{field}"})
        if "sequence" in event and not isinstance(event.get("sequence"), int):
            invalid_fields.append({"field": "event_timeline", "index": index, "reason": "sequence_expected_int"})

    for index, checkpoint in enumerate(payload.get("checkpoint_snapshots", []) if isinstance(payload.get("checkpoint_snapshots"), list) else []):
        if not isinstance(checkpoint, dict):
            invalid_fields.append({"field": "checkpoint_snapshots", "index": index, "reason": "expected_dict"})
            continue
        for field in ("checkpoint_id", "checkpoint_type", "checkpoint_state", "sequence"):
            if field not in checkpoint:
                invalid_fields.append({"field": "checkpoint_snapshots", "index": index, "reason": f"missing_{field}"})
        if "sequence" in checkpoint and not isinstance(checkpoint.get("sequence"), int):
            invalid_fields.append({"field": "checkpoint_snapshots", "index": index, "reason": "sequence_expected_int"})

    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(SESSION_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def build_governed_runtime_execution_session_summary(session_report: Any) -> Dict[str, Any]:
    report = _mapping(session_report)
    return {
        "schema_version": SCHEMA_VERSION,
        "execution_session_id": _text(report.get("execution_session_id")),
        "session_state": _text(report.get("session_state")),
        "source_execution_id": _text(report.get("source_execution_id")),
        "source_gateway_id": _text(report.get("source_gateway_id")),
        "source_boundary_id": _text(report.get("source_boundary_id")),
        "event_count": len(report.get("event_timeline", []) or []),
        "checkpoint_count": len(report.get("checkpoint_snapshots", []) or []),
        "replay_order_valid": bool(report.get("replay_order_valid")),
        "rollback_eligible": bool(report.get("rollback_eligible")),
        "seal_handoff_ready": bool(report.get("seal_handoff_ready")),
        "blocking_issue_count": len(report.get("blocking_issues", []) or []),
        "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
    }


def _derive_session_state(
    *,
    action_execution: Mapping[str, Any],
    boundary: Mapping[str, Any],
    events: List[Dict[str, Any]],
    checkpoints: List[Dict[str, Any]],
    rollback_report: Any | None,
    seal_handoff: Any | None,
) -> str:
    execution_state = _text(action_execution.get("execution_state"))
    if _text(boundary.get("boundary_state")) == "blocked":
        return SESSION_BLOCKED
    if execution_state == "blocked":
        return SESSION_BLOCKED
    if execution_state == "review_required":
        return SESSION_REVIEW_REQUIRED
    if _mapping(rollback_report).get("rollback_performed") is True:
        return SESSION_ROLLED_BACK
    if _seal_handoff_ready(session_state=SESSION_CHECKPOINTED, seal_handoff=seal_handoff, checkpoints=checkpoints):
        return SESSION_SEALED
    if checkpoints:
        return SESSION_CHECKPOINTED
    if events:
        return SESSION_RUNNING
    if action_execution:
        return SESSION_PREPARED
    return SESSION_CREATED


def _events_from_action_execution(action_execution: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if not action_execution:
        return []
    source_execution_id = _text(action_execution.get("governed_action_execution_id"))
    events = [
        build_governed_runtime_execution_event(
            event_type="execution_report_received",
            event_state=_text(action_execution.get("execution_state")) or "unknown",
            source_ref=source_execution_id,
            sequence=0,
            payload={
                "execution_allowed": bool(action_execution.get("execution_allowed")),
                "dry_run_only": bool(action_execution.get("dry_run_only")),
                "approval_required": bool(action_execution.get("approval_required")),
            },
        )
    ]
    for index, action in enumerate(action_execution.get("action_results", []) if isinstance(action_execution.get("action_results"), list) else []):
        if isinstance(action, dict):
            events.append(
                build_governed_runtime_execution_event(
                    event_type="action_result",
                    event_state=_text(action.get("action_state")),
                    source_ref=_text(action.get("request_id")),
                    sequence=index + 1,
                    payload=copy.deepcopy(action),
                )
            )
    return events


def _normalize_events(events: Iterable[Any] | None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, event in enumerate(events or []):
        if not isinstance(event, dict):
            continue
        payload = copy.deepcopy(event)
        payload.setdefault("event_type", "")
        payload.setdefault("event_state", "")
        payload.setdefault("source_ref", "")
        payload["sequence"] = _safe_int(payload.get("sequence"), default=index)
        payload.setdefault("payload", {})
        payload["event_id"] = _text(payload.get("event_id")) or _event_id(payload)
        normalized.append(payload)
    return sorted(normalized, key=lambda item: item["sequence"])


def _normalize_checkpoints(checkpoints: Iterable[Any] | None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, checkpoint in enumerate(checkpoints or []):
        if not isinstance(checkpoint, dict):
            continue
        payload = copy.deepcopy(checkpoint)
        payload.setdefault("checkpoint_type", "")
        payload.setdefault("checkpoint_state", "")
        payload.setdefault("source_event_id", "")
        payload.setdefault("runtime_state_ref", "")
        payload["sequence"] = _safe_int(payload.get("sequence"), default=index)
        payload.setdefault("payload", {})
        payload["checkpoint_id"] = _text(payload.get("checkpoint_id")) or _checkpoint_id(payload)
        normalized.append(payload)
    return sorted(normalized, key=lambda item: item["sequence"])


def _session_transition_valid(previous: str, current: str) -> bool:
    current = _text(current)
    previous = _text(previous)
    if current not in SESSION_STATES:
        return False
    if not previous:
        return current in {SESSION_CREATED, SESSION_PREPARED, SESSION_RUNNING, SESSION_CHECKPOINTED, SESSION_REVIEW_REQUIRED, SESSION_BLOCKED}
    return current in ALLOWED_SESSION_TRANSITIONS.get(previous, set())


def _replay_order_valid(events: List[Dict[str, Any]], checkpoints: List[Dict[str, Any]]) -> bool:
    event_sequences = [item.get("sequence") for item in events]
    checkpoint_sequences = [item.get("sequence") for item in checkpoints]
    if event_sequences != sorted(event_sequences):
        return False
    if checkpoint_sequences != sorted(checkpoint_sequences):
        return False
    event_ids = {_text(item.get("event_id")) for item in events}
    for checkpoint in checkpoints:
        source_event_id = _text(checkpoint.get("source_event_id"))
        if source_event_id and source_event_id not in event_ids:
            return False
    return True


def _rollback_eligible(
    *,
    action_execution: Mapping[str, Any],
    rollback_report: Any | None,
    checkpoints: List[Dict[str, Any]],
) -> bool:
    rollback = _mapping(rollback_report)
    if rollback.get("rollback_performed") is True:
        return True
    if rollback.get("rollback_available") is True:
        return True
    if _text(action_execution.get("execution_state")) in {"blocked", "review_required"}:
        return False
    return bool(checkpoints)


def _seal_handoff_ready(
    *,
    session_state: str,
    seal_handoff: Any | None,
    checkpoints: List[Dict[str, Any]],
) -> bool:
    seal = _mapping(seal_handoff)
    if not seal:
        return False
    if seal.get("seal_ready") is True:
        return True
    if _text(seal.get("seal_state")) in {"seal_ready", "ready", "sealed"} and checkpoints:
        return True
    return False


def _build_continuation_contract(
    *,
    session_state: str,
    continuation_context: Any | None,
    events: List[Dict[str, Any]],
    checkpoints: List[Dict[str, Any]],
) -> Dict[str, Any]:
    context = _mapping(continuation_context)
    can_continue = _text(session_state) not in TERMINAL_SESSION_STATES and bool(events)
    return {
        "continuation_id": "runtime-execution-continuation-" + _stable_hash(
            {
                "session_state": session_state,
                "event_count": len(events),
                "checkpoint_count": len(checkpoints),
                "context": context,
            }
        )[:16],
        "can_continue": can_continue,
        "continuation_state": "available" if can_continue else "closed",
        "next_event_sequence": (max([event.get("sequence", 0) for event in events]) + 1) if events else 0,
        "latest_checkpoint_id": _text(checkpoints[-1].get("checkpoint_id")) if checkpoints else "",
        "context": context,
    }


def _event_id(event: Mapping[str, Any]) -> str:
    payload = {
        "event_type": _text(event.get("event_type")),
        "event_state": _text(event.get("event_state")),
        "source_ref": _text(event.get("source_ref")),
        "sequence": _safe_int(event.get("sequence")),
        "payload": copy.deepcopy(event.get("payload", {})),
    }
    return "governed-runtime-execution-event-" + _stable_hash(payload)[:16]


def _checkpoint_id(checkpoint: Mapping[str, Any]) -> str:
    payload = {
        "checkpoint_type": _text(checkpoint.get("checkpoint_type")),
        "checkpoint_state": _text(checkpoint.get("checkpoint_state")),
        "source_event_id": _text(checkpoint.get("source_event_id")),
        "runtime_state_ref": _text(checkpoint.get("runtime_state_ref")),
        "sequence": _safe_int(checkpoint.get("sequence")),
        "payload": copy.deepcopy(checkpoint.get("payload", {})),
    }
    return "governed-runtime-execution-checkpoint-" + _stable_hash(payload)[:16]


def _session_id(report: Mapping[str, Any]) -> str:
    payload = {
        "session_state": report.get("session_state"),
        "source_execution_id": report.get("source_execution_id"),
        "source_gateway_id": report.get("source_gateway_id"),
        "source_boundary_id": report.get("source_boundary_id"),
        "event_timeline": report.get("event_timeline", []),
        "checkpoint_snapshots": report.get("checkpoint_snapshots", []),
        "blocking_issues": report.get("blocking_issues", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "governed-runtime-execution-session-" + _stable_hash(payload)[:16]


def _mapping(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        values = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (dict, bytes)):
        values = list(value)
    else:
        values = []
    return [_text(item) for item in values if _text(item)]


def _sorted_unique(values: Iterable[Any]) -> List[str]:
    if values is None:
        return []
    return sorted({_text(value) for value in values if _text(value)})


def _reason_codes_from_issues(issues: Iterable[Any]) -> List[str]:
    return _sorted_unique(item.get("kind") for item in issues if isinstance(item, dict))


def _dedupe_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for issue in issues or []:
        if isinstance(issue, dict):
            payload = copy.deepcopy(issue)
            deduped[_stable_hash(payload)] = payload
    return [copy.deepcopy(deduped[key]) for key in sorted(deduped)]


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_governed_runtime_lockdown_session_report(
    *,
    freeze_decision: Any | None = None,
    freeze_state: Any | None = None,
    previous_session_state: str | None = None,
    source_execution_id: str = "",
    source_gateway_id: str = "",
    source_boundary_id: str = "",
    reason: str = "",
    metadata: Any | None = None,
) -> Dict[str, Any]:
    """Escalate a runtime freeze into a terminal governed execution session.

    This is the persistence bridge between execution-level freeze denial and
    runtime-wide lockdown state.  A frozen runtime must become SESSION_BLOCKED
    and its continuation contract must be closed.
    """

    freeze_payload = _mapping(freeze_decision) or _mapping(freeze_state)
    frozen = bool(
        freeze_payload.get("runtime_frozen")
        or freeze_payload.get("denied")
        or freeze_payload.get("frozen")
        or freeze_payload.get("is_frozen")
    )

    resolved_reason = (
        _text(reason)
        or _text(freeze_payload.get("reason"))
        or "runtime freeze escalated to governed session lockdown"
    )

    event = build_governed_runtime_execution_event(
        event_type="runtime_freeze_escalated",
        event_state=SESSION_BLOCKED if frozen else SESSION_RUNNING,
        source_ref=_text(source_execution_id) or _text(freeze_payload.get("freeze_id")),
        sequence=0,
        payload={
            "runtime_frozen": frozen,
            "freeze_decision": copy.deepcopy(freeze_payload),
            "reason": resolved_reason,
            "metadata": copy.deepcopy(metadata) if metadata is not None else {},
        },
    )

    checkpoint = build_governed_runtime_execution_checkpoint(
        checkpoint_type="runtime_lockdown",
        checkpoint_state="blocked" if frozen else "open",
        source_event_id=event["event_id"],
        runtime_state_ref=_text(freeze_payload.get("freeze_id")),
        sequence=0,
        payload={
            "runtime_frozen": frozen,
            "reason": resolved_reason,
        },
    )

    blocking_issues: List[Dict[str, Any]] = []
    if frozen:
        blocking_issues.append(
            {
                "kind": "runtime_freeze_lockdown",
                "reason": resolved_reason,
                "freeze_id": _text(freeze_payload.get("freeze_id")),
            }
        )

    session_state = SESSION_BLOCKED if frozen else SESSION_RUNNING
    continuation_contract = {
        "continuation_id": "runtime-execution-continuation-" + _stable_hash(
            {
                "session_state": session_state,
                "runtime_frozen": frozen,
                "freeze_payload": freeze_payload,
                "reason": resolved_reason,
            }
        )[:16],
        "can_continue": not frozen,
        "continuation_state": "closed" if frozen else "available",
        "next_event_sequence": 1,
        "latest_checkpoint_id": checkpoint["checkpoint_id"],
        "context": {
            "runtime_frozen": frozen,
            "freeze_id": _text(freeze_payload.get("freeze_id")),
            "reason": resolved_reason,
            "metadata": copy.deepcopy(metadata) if metadata is not None else {},
        },
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "execution_session_id": "",
        "session_state": session_state,
        "previous_session_state": _text(previous_session_state),
        "transition_valid": _session_transition_valid(_text(previous_session_state), session_state),
        "source_execution_id": _text(source_execution_id),
        "source_gateway_id": _text(source_gateway_id),
        "source_boundary_id": _text(source_boundary_id),
        "event_timeline": [event],
        "checkpoint_snapshots": [checkpoint],
        "replay_order_valid": True,
        "rollback_eligible": False,
        "seal_handoff_ready": False,
        "continuation_contract": continuation_contract,
        "blocking_issues": blocking_issues,
        "reason_codes": _sorted_unique(
            [
                "runtime_freeze_lockdown" if frozen else "",
                *_reason_codes_from_issues(blocking_issues),
            ]
        ),
        "session_summary": {
            "event_count": 1,
            "checkpoint_count": 1,
            "session_state": session_state,
            "source_execution_state": "blocked" if frozen else "running",
            "replay_order_valid": True,
            "rollback_eligible": False,
            "seal_handoff_ready": False,
            "runtime_frozen": frozen,
        },
    }
    report["execution_session_id"] = _session_id(report)
    return report


def escalate_runtime_freeze_to_governed_session(
    *,
    freeze_decision: Any | None = None,
    freeze_state: Any | None = None,
    previous_session_state: str | None = None,
    source_execution_id: str = "",
    source_gateway_id: str = "",
    source_boundary_id: str = "",
    reason: str = "",
    metadata: Any | None = None,
) -> Dict[str, Any]:
    return build_governed_runtime_lockdown_session_report(
        freeze_decision=freeze_decision,
        freeze_state=freeze_state,
        previous_session_state=previous_session_state,
        source_execution_id=source_execution_id,
        source_gateway_id=source_gateway_id,
        source_boundary_id=source_boundary_id,
        reason=reason,
        metadata=metadata,
    )

