from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "governed_runtime_replay_session.v1"

REPLAY_PREPARED = "prepared"
REPLAY_RUNNING = "running"
REPLAY_CONSISTENT = "consistent"
REPLAY_DIVERGED = "diverged"
REPLAY_REWIND_REQUIRED = "rewind_required"
REPLAY_BLOCKED = "blocked"
REPLAY_FAILED = "failed"

REPLAY_STATES: tuple[str, ...] = (
    REPLAY_PREPARED,
    REPLAY_RUNNING,
    REPLAY_CONSISTENT,
    REPLAY_DIVERGED,
    REPLAY_REWIND_REQUIRED,
    REPLAY_BLOCKED,
    REPLAY_FAILED,
)

REPLAY_REQUIRED_FIELDS: tuple[str, ...] = (
    "replay_session_id",
    "source_execution_session_id",
    "replay_state",
    "timeline_replay_valid",
    "checkpoint_replay_valid",
    "rollback_replay_valid",
    "continuation_replay_valid",
    "forensic_replay_valid",
    "deterministic_resume_ready",
    "replay_events",
    "replay_checkpoints",
    "replay_divergences",
    "rewind_points",
    "blocking_issues",
    "reason_codes",
)


def governed_runtime_replay_session_states() -> List[str]:
    return list(REPLAY_STATES)


def governed_runtime_replay_session_required_fields() -> List[str]:
    return list(REPLAY_REQUIRED_FIELDS)


def build_governed_runtime_replay_event(
    *,
    replay_event_type: str,
    replay_event_state: str,
    source_event_id: str = "",
    sequence: int | None = None,
    payload: Any | None = None,
) -> Dict[str, Any]:
    normalized_sequence = 0 if sequence is None else max(0, int(sequence))
    event = {
        "replay_event_id": "",
        "replay_event_type": _text(replay_event_type),
        "replay_event_state": _text(replay_event_state),
        "source_event_id": _text(source_event_id),
        "sequence": normalized_sequence,
        "payload": copy.deepcopy(payload) if payload is not None else {},
    }
    event["replay_event_id"] = _replay_event_id(event)
    return event


def build_governed_runtime_replay_checkpoint(
    *,
    replay_checkpoint_type: str,
    replay_checkpoint_state: str,
    source_checkpoint_id: str = "",
    sequence: int | None = None,
    payload: Any | None = None,
) -> Dict[str, Any]:
    normalized_sequence = 0 if sequence is None else max(0, int(sequence))
    checkpoint = {
        "replay_checkpoint_id": "",
        "replay_checkpoint_type": _text(replay_checkpoint_type),
        "replay_checkpoint_state": _text(replay_checkpoint_state),
        "source_checkpoint_id": _text(source_checkpoint_id),
        "sequence": normalized_sequence,
        "payload": copy.deepcopy(payload) if payload is not None else {},
    }
    checkpoint["replay_checkpoint_id"] = _replay_checkpoint_id(checkpoint)
    return checkpoint


def build_governed_runtime_replay_session_report(
    *,
    execution_session_report: Any,
    replay_events: Iterable[Any] | None = None,
    replay_checkpoints: Iterable[Any] | None = None,
    expected_event_timeline: Iterable[Any] | None = None,
    expected_checkpoint_snapshots: Iterable[Any] | None = None,
    rollback_replay_report: Any | None = None,
    continuation_replay_report: Any | None = None,
    forensic_replay_report: Any | None = None,
    resume_context: Any | None = None,
) -> Dict[str, Any]:
    """Build a deterministic, data-only replay validation report for an execution session."""

    session = _mapping(execution_session_report)

    expected_events = _normalize_source_events(
        expected_event_timeline
        if expected_event_timeline is not None
        else session.get("event_timeline", [])
    )
    expected_checkpoints = _normalize_source_checkpoints(
        expected_checkpoint_snapshots
        if expected_checkpoint_snapshots is not None
        else session.get("checkpoint_snapshots", [])
    )

    actual_events = _normalize_replay_events(replay_events)
    if not actual_events:
        actual_events = [
            build_governed_runtime_replay_event(
                replay_event_type=_text(event.get("event_type")) or "event",
                replay_event_state=_text(event.get("event_state")) or "unknown",
                source_event_id=_text(event.get("event_id")),
                sequence=_safe_int(event.get("sequence")),
                payload={
                    "source_ref": _text(event.get("source_ref")),
                    "payload_hash": _stable_hash(event.get("payload", {})),
                },
            )
            for event in expected_events
        ]

    actual_checkpoints = _normalize_replay_checkpoints(replay_checkpoints)
    if not actual_checkpoints:
        actual_checkpoints = [
            build_governed_runtime_replay_checkpoint(
                replay_checkpoint_type=_text(checkpoint.get("checkpoint_type")) or "checkpoint",
                replay_checkpoint_state=_text(checkpoint.get("checkpoint_state")) or "unknown",
                source_checkpoint_id=_text(checkpoint.get("checkpoint_id")),
                sequence=_safe_int(checkpoint.get("sequence")),
                payload={
                    "runtime_state_ref": _text(checkpoint.get("runtime_state_ref")),
                    "payload_hash": _stable_hash(checkpoint.get("payload", {})),
                },
            )
            for checkpoint in expected_checkpoints
        ]

    timeline_replay = _validate_timeline_replay(expected_events, actual_events)
    checkpoint_replay = _validate_checkpoint_replay(expected_checkpoints, actual_checkpoints)
    rollback_replay = _validate_rollback_replay(rollback_replay_report, session)
    continuation_replay = _validate_continuation_replay(continuation_replay_report, session)
    forensic_replay = _validate_forensic_replay(forensic_replay_report, session)

    divergences = _dedupe_issues(
        [
            *timeline_replay["divergences"],
            *checkpoint_replay["divergences"],
            *rollback_replay["divergences"],
            *continuation_replay["divergences"],
            *forensic_replay["divergences"],
        ]
    )
    rewind_points = _build_rewind_points(
        expected_events=expected_events,
        expected_checkpoints=expected_checkpoints,
        divergences=divergences,
    )
    deterministic_resume_ready = _deterministic_resume_ready(
        session=session,
        resume_context=resume_context,
        divergences=divergences,
        rewind_points=rewind_points,
    )

    blocking_issues: List[Dict[str, Any]] = []
    if not session:
        blocking_issues.append({"kind": "execution_session_report_missing"})
    if _text(session.get("session_state")) == "blocked":
        blocking_issues.append({"kind": "source_execution_session_blocked"})
    if not timeline_replay["valid"]:
        blocking_issues.append({"kind": "timeline_replay_invalid"})
    if not checkpoint_replay["valid"]:
        blocking_issues.append({"kind": "checkpoint_replay_invalid"})
    if not rollback_replay["valid"]:
        blocking_issues.append({"kind": "rollback_replay_invalid"})
    if not continuation_replay["valid"]:
        blocking_issues.append({"kind": "continuation_replay_invalid"})
    if not forensic_replay["valid"]:
        blocking_issues.append({"kind": "forensic_replay_invalid"})
    if divergences and not rewind_points:
        blocking_issues.append({"kind": "replay_divergence_without_rewind_point"})

    blocking_issues = _dedupe_issues(blocking_issues)

    if blocking_issues:
        replay_state = REPLAY_BLOCKED
    elif divergences and rewind_points:
        replay_state = REPLAY_REWIND_REQUIRED
    elif divergences:
        replay_state = REPLAY_DIVERGED
    elif not actual_events and not actual_checkpoints:
        replay_state = REPLAY_PREPARED
    else:
        replay_state = REPLAY_CONSISTENT

    report = {
        "schema_version": SCHEMA_VERSION,
        "replay_session_id": "",
        "source_execution_session_id": _text(session.get("execution_session_id")),
        "source_execution_id": _text(session.get("source_execution_id")),
        "replay_state": replay_state,
        "timeline_replay_valid": bool(timeline_replay["valid"]),
        "checkpoint_replay_valid": bool(checkpoint_replay["valid"]),
        "rollback_replay_valid": bool(rollback_replay["valid"]),
        "continuation_replay_valid": bool(continuation_replay["valid"]),
        "forensic_replay_valid": bool(forensic_replay["valid"]),
        "deterministic_resume_ready": deterministic_resume_ready,
        "replay_events": actual_events,
        "replay_checkpoints": actual_checkpoints,
        "replay_divergences": divergences,
        "rewind_points": rewind_points,
        "blocking_issues": blocking_issues,
        "reason_codes": _sorted_unique(
            [
                *_string_list(session.get("reason_codes")),
                *_reason_codes_from_issues(divergences),
                *_reason_codes_from_issues(blocking_issues),
            ]
        ),
        "replay_summary": {
            "expected_event_count": len(expected_events),
            "actual_event_count": len(actual_events),
            "expected_checkpoint_count": len(expected_checkpoints),
            "actual_checkpoint_count": len(actual_checkpoints),
            "divergence_count": len(divergences),
            "rewind_point_count": len(rewind_points),
            "replay_state": replay_state,
            "deterministic_resume_ready": deterministic_resume_ready,
        },
    }
    report["replay_session_id"] = _replay_session_id(report)
    return report


def validate_governed_runtime_replay_session_report(value: Any) -> Dict[str, Any]:
    payload = _mapping(value)
    missing = [field for field in REPLAY_REQUIRED_FIELDS if field not in payload]
    invalid_fields: List[Dict[str, Any]] = []

    if _text(payload.get("replay_state")) not in REPLAY_STATES:
        invalid_fields.append({"field": "replay_state", "reason": "invalid_state"})

    for field in (
        "timeline_replay_valid",
        "checkpoint_replay_valid",
        "rollback_replay_valid",
        "continuation_replay_valid",
        "forensic_replay_valid",
        "deterministic_resume_ready",
    ):
        if field in payload and not isinstance(payload.get(field), bool):
            invalid_fields.append({"field": field, "reason": "expected_bool"})

    for field in (
        "replay_events",
        "replay_checkpoints",
        "replay_divergences",
        "rewind_points",
        "blocking_issues",
        "reason_codes",
    ):
        if field in payload and not isinstance(payload.get(field), list):
            invalid_fields.append({"field": field, "reason": "expected_list"})

    for index, event in enumerate(payload.get("replay_events", []) if isinstance(payload.get("replay_events"), list) else []):
        if not isinstance(event, dict):
            invalid_fields.append({"field": "replay_events", "index": index, "reason": "expected_dict"})
            continue
        for field in ("replay_event_id", "replay_event_type", "replay_event_state", "source_event_id", "sequence"):
            if field not in event:
                invalid_fields.append({"field": "replay_events", "index": index, "reason": f"missing_{field}"})

    for index, checkpoint in enumerate(payload.get("replay_checkpoints", []) if isinstance(payload.get("replay_checkpoints"), list) else []):
        if not isinstance(checkpoint, dict):
            invalid_fields.append({"field": "replay_checkpoints", "index": index, "reason": "expected_dict"})
            continue
        for field in ("replay_checkpoint_id", "replay_checkpoint_type", "replay_checkpoint_state", "source_checkpoint_id", "sequence"):
            if field not in checkpoint:
                invalid_fields.append({"field": "replay_checkpoints", "index": index, "reason": f"missing_{field}"})

    return {
        "ok": not missing and not invalid_fields,
        "contract": SCHEMA_VERSION,
        "required_fields": list(REPLAY_REQUIRED_FIELDS),
        "missing_fields": missing,
        "invalid_fields": invalid_fields,
        "unexpected_type": "" if isinstance(value, dict) else type(value).__name__,
    }


def build_governed_runtime_replay_session_summary(replay_report: Any) -> Dict[str, Any]:
    report = _mapping(replay_report)
    return {
        "schema_version": SCHEMA_VERSION,
        "replay_session_id": _text(report.get("replay_session_id")),
        "source_execution_session_id": _text(report.get("source_execution_session_id")),
        "source_execution_id": _text(report.get("source_execution_id")),
        "replay_state": _text(report.get("replay_state")),
        "timeline_replay_valid": bool(report.get("timeline_replay_valid")),
        "checkpoint_replay_valid": bool(report.get("checkpoint_replay_valid")),
        "rollback_replay_valid": bool(report.get("rollback_replay_valid")),
        "continuation_replay_valid": bool(report.get("continuation_replay_valid")),
        "forensic_replay_valid": bool(report.get("forensic_replay_valid")),
        "deterministic_resume_ready": bool(report.get("deterministic_resume_ready")),
        "divergence_count": len(report.get("replay_divergences", []) or []),
        "rewind_point_count": len(report.get("rewind_points", []) or []),
        "blocking_issue_count": len(report.get("blocking_issues", []) or []),
        "reason_codes": copy.deepcopy(report.get("reason_codes", [])),
    }


def _normalize_source_events(events: Iterable[Any] | None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, event in enumerate(events or []):
        if not isinstance(event, dict):
            continue
        payload = copy.deepcopy(event)
        payload["sequence"] = _safe_int(payload.get("sequence"), default=index)
        payload.setdefault("event_id", "source-event-" + _stable_hash(payload)[:16])
        payload.setdefault("event_type", "")
        payload.setdefault("event_state", "")
        normalized.append(payload)
    return sorted(normalized, key=lambda item: item["sequence"])


def _normalize_source_checkpoints(checkpoints: Iterable[Any] | None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, checkpoint in enumerate(checkpoints or []):
        if not isinstance(checkpoint, dict):
            continue
        payload = copy.deepcopy(checkpoint)
        payload["sequence"] = _safe_int(payload.get("sequence"), default=index)
        payload.setdefault("checkpoint_id", "source-checkpoint-" + _stable_hash(payload)[:16])
        payload.setdefault("checkpoint_type", "")
        payload.setdefault("checkpoint_state", "")
        normalized.append(payload)
    return sorted(normalized, key=lambda item: item["sequence"])


def _normalize_replay_events(events: Iterable[Any] | None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, event in enumerate(events or []):
        if not isinstance(event, dict):
            continue
        payload = copy.deepcopy(event)
        payload.setdefault("replay_event_type", "")
        payload.setdefault("replay_event_state", "")
        payload.setdefault("source_event_id", "")
        payload["sequence"] = _safe_int(payload.get("sequence"), default=index)
        payload.setdefault("payload", {})
        payload["replay_event_id"] = _text(payload.get("replay_event_id")) or _replay_event_id(payload)
        normalized.append(payload)
    return sorted(normalized, key=lambda item: item["sequence"])


def _normalize_replay_checkpoints(checkpoints: Iterable[Any] | None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, checkpoint in enumerate(checkpoints or []):
        if not isinstance(checkpoint, dict):
            continue
        payload = copy.deepcopy(checkpoint)
        payload.setdefault("replay_checkpoint_type", "")
        payload.setdefault("replay_checkpoint_state", "")
        payload.setdefault("source_checkpoint_id", "")
        payload["sequence"] = _safe_int(payload.get("sequence"), default=index)
        payload.setdefault("payload", {})
        payload["replay_checkpoint_id"] = _text(payload.get("replay_checkpoint_id")) or _replay_checkpoint_id(payload)
        normalized.append(payload)
    return sorted(normalized, key=lambda item: item["sequence"])


def _validate_timeline_replay(expected_events: List[Dict[str, Any]], replay_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    divergences: List[Dict[str, Any]] = []
    if len(expected_events) != len(replay_events):
        divergences.append(
            {
                "kind": "timeline_event_count_mismatch",
                "expected": len(expected_events),
                "actual": len(replay_events),
            }
        )
    expected_by_sequence = {event["sequence"]: event for event in expected_events}
    actual_by_sequence = {event["sequence"]: event for event in replay_events}
    for sequence, expected in expected_by_sequence.items():
        actual = actual_by_sequence.get(sequence)
        if not actual:
            divergences.append({"kind": "timeline_event_missing", "sequence": sequence})
            continue
        if _text(actual.get("source_event_id")) != _text(expected.get("event_id")):
            divergences.append(
                {
                    "kind": "timeline_event_source_mismatch",
                    "sequence": sequence,
                    "expected_event_id": _text(expected.get("event_id")),
                    "actual_source_event_id": _text(actual.get("source_event_id")),
                }
            )
        expected_state = _text(expected.get("event_state"))
        actual_state = _text(actual.get("replay_event_state"))
        if expected_state and actual_state and expected_state != actual_state:
            divergences.append(
                {
                    "kind": "timeline_event_state_mismatch",
                    "sequence": sequence,
                    "expected_state": expected_state,
                    "actual_state": actual_state,
                }
            )
    return {"valid": not divergences, "divergences": _dedupe_issues(divergences)}


def _validate_checkpoint_replay(expected_checkpoints: List[Dict[str, Any]], replay_checkpoints: List[Dict[str, Any]]) -> Dict[str, Any]:
    divergences: List[Dict[str, Any]] = []
    if len(expected_checkpoints) != len(replay_checkpoints):
        divergences.append(
            {
                "kind": "checkpoint_count_mismatch",
                "expected": len(expected_checkpoints),
                "actual": len(replay_checkpoints),
            }
        )
    expected_by_sequence = {checkpoint["sequence"]: checkpoint for checkpoint in expected_checkpoints}
    actual_by_sequence = {checkpoint["sequence"]: checkpoint for checkpoint in replay_checkpoints}
    for sequence, expected in expected_by_sequence.items():
        actual = actual_by_sequence.get(sequence)
        if not actual:
            divergences.append({"kind": "checkpoint_missing", "sequence": sequence})
            continue
        if _text(actual.get("source_checkpoint_id")) != _text(expected.get("checkpoint_id")):
            divergences.append(
                {
                    "kind": "checkpoint_source_mismatch",
                    "sequence": sequence,
                    "expected_checkpoint_id": _text(expected.get("checkpoint_id")),
                    "actual_source_checkpoint_id": _text(actual.get("source_checkpoint_id")),
                }
            )
        expected_state = _text(expected.get("checkpoint_state"))
        actual_state = _text(actual.get("replay_checkpoint_state"))
        if expected_state and actual_state and expected_state != actual_state:
            divergences.append(
                {
                    "kind": "checkpoint_state_mismatch",
                    "sequence": sequence,
                    "expected_state": expected_state,
                    "actual_state": actual_state,
                }
            )
    return {"valid": not divergences, "divergences": _dedupe_issues(divergences)}


def _validate_rollback_replay(rollback_replay_report: Any | None, session: Mapping[str, Any]) -> Dict[str, Any]:
    rollback = _mapping(rollback_replay_report)
    if not rollback:
        return {"valid": True, "divergences": []}
    expected_eligible = bool(session.get("rollback_eligible"))
    actual_eligible = bool(rollback.get("rollback_replay_valid", rollback.get("rollback_eligible", expected_eligible)))
    if expected_eligible and not actual_eligible:
        return {"valid": False, "divergences": [{"kind": "rollback_replay_mismatch"}]}
    return {"valid": True, "divergences": []}


def _validate_continuation_replay(continuation_replay_report: Any | None, session: Mapping[str, Any]) -> Dict[str, Any]:
    continuation = _mapping(continuation_replay_report)
    if not continuation:
        return {"valid": True, "divergences": []}
    contract = _mapping(session.get("continuation_contract"))
    expected = bool(contract.get("can_continue"))
    actual = bool(continuation.get("continuation_replay_valid", continuation.get("can_continue", expected)))
    if expected and not actual:
        return {"valid": False, "divergences": [{"kind": "continuation_replay_mismatch"}]}
    return {"valid": True, "divergences": []}


def _validate_forensic_replay(forensic_replay_report: Any | None, session: Mapping[str, Any]) -> Dict[str, Any]:
    forensic = _mapping(forensic_replay_report)
    if not forensic:
        return {"valid": True, "divergences": []}
    if forensic.get("forensic_replay_valid") is False:
        return {"valid": False, "divergences": [{"kind": "forensic_replay_mismatch"}]}
    if _text(forensic.get("source_execution_session_id")) and _text(forensic.get("source_execution_session_id")) != _text(session.get("execution_session_id")):
        return {"valid": False, "divergences": [{"kind": "forensic_source_session_mismatch"}]}
    return {"valid": True, "divergences": []}


def _build_rewind_points(
    *,
    expected_events: List[Dict[str, Any]],
    expected_checkpoints: List[Dict[str, Any]],
    divergences: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not divergences:
        return []
    checkpoints_by_sequence = {checkpoint.get("sequence"): checkpoint for checkpoint in expected_checkpoints}
    rewind_points: List[Dict[str, Any]] = []
    for divergence in divergences:
        sequence = _safe_int(divergence.get("sequence"), default=0)
        available_sequences = [value for value in checkpoints_by_sequence if value <= sequence]
        if not available_sequences and expected_checkpoints:
            available_sequences = [min(checkpoints_by_sequence)]
        if not available_sequences:
            continue
        checkpoint = checkpoints_by_sequence[max(available_sequences)]
        rewind_points.append(
            {
                "rewind_point_id": "runtime-replay-rewind-" + _stable_hash(
                    {
                        "divergence": divergence,
                        "checkpoint_id": checkpoint.get("checkpoint_id"),
                    }
                )[:16],
                "source_checkpoint_id": _text(checkpoint.get("checkpoint_id")),
                "sequence": _safe_int(checkpoint.get("sequence")),
                "reason": _text(divergence.get("kind")),
            }
        )
    return _dedupe_issues(rewind_points)


def _deterministic_resume_ready(
    *,
    session: Mapping[str, Any],
    resume_context: Any | None,
    divergences: List[Dict[str, Any]],
    rewind_points: List[Dict[str, Any]],
) -> bool:
    context = _mapping(resume_context)
    if _text(session.get("session_state")) in {"blocked", "failed"}:
        return False
    if divergences:
        return bool(rewind_points)
    if context:
        return context.get("resume_allowed", True) is not False
    return True


def _replay_event_id(event: Mapping[str, Any]) -> str:
    payload = {
        "replay_event_type": _text(event.get("replay_event_type")),
        "replay_event_state": _text(event.get("replay_event_state")),
        "source_event_id": _text(event.get("source_event_id")),
        "sequence": _safe_int(event.get("sequence")),
        "payload": copy.deepcopy(event.get("payload", {})),
    }
    return "governed-runtime-replay-event-" + _stable_hash(payload)[:16]


def _replay_checkpoint_id(checkpoint: Mapping[str, Any]) -> str:
    payload = {
        "replay_checkpoint_type": _text(checkpoint.get("replay_checkpoint_type")),
        "replay_checkpoint_state": _text(checkpoint.get("replay_checkpoint_state")),
        "source_checkpoint_id": _text(checkpoint.get("source_checkpoint_id")),
        "sequence": _safe_int(checkpoint.get("sequence")),
        "payload": copy.deepcopy(checkpoint.get("payload", {})),
    }
    return "governed-runtime-replay-checkpoint-" + _stable_hash(payload)[:16]


def _replay_session_id(report: Mapping[str, Any]) -> str:
    payload = {
        "source_execution_session_id": report.get("source_execution_session_id"),
        "source_execution_id": report.get("source_execution_id"),
        "replay_state": report.get("replay_state"),
        "replay_events": report.get("replay_events", []),
        "replay_checkpoints": report.get("replay_checkpoints", []),
        "replay_divergences": report.get("replay_divergences", []),
        "rewind_points": report.get("rewind_points", []),
        "blocking_issues": report.get("blocking_issues", []),
        "reason_codes": report.get("reason_codes", []),
    }
    return "governed-runtime-replay-session-" + _stable_hash(payload)[:16]


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
