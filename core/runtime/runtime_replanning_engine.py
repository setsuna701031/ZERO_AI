from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.runtime.runtime_event_bus import (
    load_event_bus_state,
    publish,
    replay,
    save_event_bus_state,
)
from core.runtime.runtime_operator_session import (
    fingerprint,
    time_text,
)

CONTRACT = "zero.runtime.replanning_engine.v1"
DECISION_CONTRACT = "zero.runtime.replanning_decision.v1"

SUPPORTED_TOPICS = {
    "worker.blocked",
    "worker.failed",
    "dispatch.failed",
    "dispatch.no_worker_available",
    "scheduler.blocked",
    "scheduler.failed",
    "mission.completed",
    "scheduler.completed",
}

VALID_ENGINE_STATUSES = {
    "created",
    "running",
    "idle",
    "paused",
    "stopped",
    "blocked",
    "failed",
}

VALID_DECISIONS = {
    "retry",
    "redispatch",
    "replan",
    "manual_review",
    "complete",
    "ignore",
}

SAFETY_REASONS = {
    "path_safety_failure",
    "approval_required",
    "authorization_required",
    "transaction_boundary_required",
    "session_identity_mismatch",
    "goal_execution_registry_fingerprint_mismatch",
    "goal_execution_request_fingerprint_mismatch",
}

RETRYABLE_TOKENS = {
    "timeout",
    "temporary",
    "transient",
    "lease_expired",
    "stale",
    "worker_unavailable",
    "no_worker_available",
    "adapter_unavailable",
}

REPLAN_TOKENS = {
    "validation_failure",
    "goal_not_achieved",
    "acceptance_criteria",
    "planner",
    "scope",
    "dependency",
}


def _mapping(value: Any) -> dict[str, Any]:
    return (
        deepcopy(dict(value))
        if isinstance(value, Mapping)
        else {}
    )


def _unsafe(path: Path) -> bool:
    try:
        attributes = getattr(
            path.lstat(),
            "st_file_attributes",
            0,
        )
        reparse = getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
        )
        return path.is_symlink() or bool(
            attributes & reparse
        )
    except OSError:
        return False


def _atomic_write_json(
    value: Mapping[str, Any],
    destination: Path,
) -> None:
    if destination.exists() and _unsafe(destination):
        raise ValueError(
            "unsafe_replanning_engine_state_path"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if _unsafe(destination.parent):
        raise ValueError(
            "unsafe_replanning_engine_state_directory"
        )

    temporary = destination.with_name(
        f".{destination.name}.tmp"
    )
    with temporary.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temporary, destination)


def _unsigned(
    value: Mapping[str, Any],
    fingerprint_field: str,
) -> dict[str, Any]:
    result = _mapping(value)
    result.pop(fingerprint_field, None)
    return result


def seal_replanning_decision(
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned(
        decision,
        "decision_fingerprint",
    )
    value["decision_fingerprint"] = fingerprint(value)
    return value


def validate_replanning_decision(
    decision: Mapping[str, Any],
) -> list[str]:
    value = _mapping(decision)
    reasons: list[str] = []

    if value.get("contract") != DECISION_CONTRACT:
        reasons.append(
            "invalid_replanning_decision_contract"
        )

    if value.get(
        "decision_fingerprint"
    ) != fingerprint(
        _unsigned(
            value,
            "decision_fingerprint",
        )
    ):
        reasons.append(
            "replanning_decision_fingerprint_mismatch"
        )

    for field in (
        "decision_id",
        "source_event_id",
        "source_topic",
        "decision",
        "created_at",
    ):
        if not str(value.get(field) or "").strip():
            reasons.append(f"{field}_required")

    if value.get("decision") not in VALID_DECISIONS:
        reasons.append("invalid_replanning_decision")

    if not isinstance(value.get("evidence"), Mapping):
        reasons.append("replanning_evidence_required")

    if not isinstance(
        value.get("recommended_actions"),
        list,
    ):
        reasons.append(
            "recommended_actions_required"
        )

    return reasons


def seal_replanning_engine_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned(
        state,
        "engine_fingerprint",
    )
    value["engine_fingerprint"] = fingerprint(value)
    return value


def validate_replanning_engine_state(
    state: Mapping[str, Any],
) -> list[str]:
    value = _mapping(state)
    reasons: list[str] = []

    if value.get("contract") != CONTRACT:
        reasons.append(
            "invalid_replanning_engine_contract"
        )

    if value.get(
        "engine_fingerprint"
    ) != fingerprint(
        _unsigned(
            value,
            "engine_fingerprint",
        )
    ):
        reasons.append(
            "replanning_engine_fingerprint_mismatch"
        )

    for field in (
        "engine_id",
        "engine_name",
        "state_path",
        "event_bus_state_path",
    ):
        if not str(value.get(field) or "").strip():
            reasons.append(f"{field}_required")

    if value.get("engine_status") not in (
        VALID_ENGINE_STATUSES
    ):
        reasons.append(
            "invalid_replanning_engine_status"
        )

    cursor = value.get("last_processed_sequence")
    if (
        isinstance(cursor, bool)
        or not isinstance(cursor, int)
        or cursor < 0
    ):
        reasons.append(
            "invalid_replanning_event_cursor"
        )

    decisions = value.get("decisions")
    order = value.get("decision_order")
    if not isinstance(decisions, Mapping):
        reasons.append(
            "replanning_decisions_required"
        )
        decisions = {}
    if not isinstance(order, list):
        reasons.append(
            "replanning_decision_order_required"
        )
        order = []

    if set(order) != set(decisions):
        reasons.append(
            "replanning_decision_order_mismatch"
        )

    for decision_id in order:
        decision = _mapping(
            decisions.get(decision_id)
        )
        if decision.get("decision_id") != decision_id:
            reasons.append(
                f"replanning_decision_identity_mismatch:{decision_id}"
            )
            continue
        for reason in validate_replanning_decision(
            decision
        ):
            reasons.append(
                f"{decision_id}:{reason}"
            )

    return reasons


def create_replanning_engine_state(
    *,
    state_path: Any,
    event_bus_state_path: Any,
    engine_name: str = "default",
    now: Any = None,
) -> dict[str, Any]:
    name = str(engine_name or "").strip()
    if not name:
        raise ValueError(
            "replanning_engine_name_required"
        )

    destination = Path(state_path)
    bus_path = Path(event_bus_state_path)
    at = time_text(now)
    identity = {
        "engine_name": name,
        "state_path": str(
            destination.resolve(strict=False)
        ).replace("\\", "/").casefold(),
        "event_bus_state_path": str(
            bus_path.resolve(strict=False)
        ).replace("\\", "/").casefold(),
    }

    return seal_replanning_engine_state(
        {
            "contract": CONTRACT,
            "engine_id": (
                "replanning-engine-"
                f"{fingerprint(identity)[:20]}"
            ),
            "engine_name": name,
            "engine_status": "created",
            "state_path": str(
                destination.resolve(strict=False)
            ),
            "event_bus_state_path": str(
                bus_path.resolve(strict=False)
            ),
            "last_processed_sequence": 0,
            "decisions": {},
            "decision_order": [],
            "processed_event_count": 0,
            "ignored_event_count": 0,
            "retry_count": 0,
            "redispatch_count": 0,
            "replan_count": 0,
            "manual_review_count": 0,
            "complete_count": 0,
            "created_at": at,
            "updated_at": at,
            "last_event_id": None,
            "failure": None,
            "pause_requested": False,
            "stop_requested": False,
        }
    )


def save_replanning_engine_state(
    state: Mapping[str, Any],
    path: Any,
) -> dict[str, Any]:
    destination = Path(path)
    value = seal_replanning_engine_state(state)
    reasons = validate_replanning_engine_state(
        value
    )
    if reasons:
        raise ValueError(";".join(reasons))
    _atomic_write_json(value, destination)
    return value


def load_replanning_engine_state(
    path: Any,
) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source):
        raise ValueError(
            "unsafe_replanning_engine_state_path"
        )

    try:
        value = json.loads(
            source.read_text(
                encoding="utf-8-sig"
            )
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "invalid_replanning_engine_json"
        ) from exc

    reasons = validate_replanning_engine_state(
        value
    )
    if reasons:
        raise ValueError(";".join(reasons))
    return value


def request_replanning_engine_action(
    state: Mapping[str, Any],
    action: str,
    *,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(state)

    if action == "pause":
        value["pause_requested"] = True
        value["engine_status"] = "paused"
    elif action == "resume":
        value["pause_requested"] = False
        value["stop_requested"] = False
        value["engine_status"] = "idle"
    elif action == "stop":
        value["stop_requested"] = True
        value["engine_status"] = "stopped"
    else:
        raise ValueError(
            "invalid_replanning_engine_action"
        )

    value["updated_at"] = time_text(now)
    return seal_replanning_engine_state(value)


def _reason_text(
    event: Mapping[str, Any],
) -> str:
    payload = _mapping(event.get("payload"))
    candidates = [
        payload.get("reason"),
        _mapping(payload.get("failure")).get(
            "reason"
        ),
        ";".join(
            str(item)
            for item in (
                _mapping(
                    payload.get("failure")
                ).get("reasons")
                or []
            )
        ),
        _mapping(payload.get("result")).get(
            "reason"
        ),
    ]
    return " ".join(
        str(item).strip()
        for item in candidates
        if str(item or "").strip()
    ).casefold()


def _contains_any(
    text: str,
    tokens: set[str],
) -> bool:
    return any(token in text for token in tokens)


def classify_replanning_event(
    event: Mapping[str, Any],
) -> dict[str, Any]:
    value = _mapping(event)
    topic = str(value.get("topic") or "").strip()
    payload = _mapping(value.get("payload"))
    reason = _reason_text(value)

    if topic not in SUPPORTED_TOPICS:
        decision = "ignore"
        confidence = 1.0
        rationale = "unsupported_topic"
        actions: list[str] = []
    elif topic in {
        "mission.completed",
        "scheduler.completed",
    }:
        decision = "complete"
        confidence = 1.0
        rationale = "terminal_success_event"
        actions = [
            "record_success_evidence",
            "close_replanning_cycle",
        ]
    elif _contains_any(reason, SAFETY_REASONS):
        decision = "manual_review"
        confidence = 1.0
        rationale = "safety_or_authority_boundary"
        actions = [
            "preserve_current_state",
            "request_operator_review",
        ]
    elif topic == "dispatch.no_worker_available":
        decision = "redispatch"
        confidence = 0.95
        rationale = "worker_capacity_unavailable"
        actions = [
            "wait_for_worker_capacity",
            "retry_dispatch_with_backoff",
        ]
    elif _contains_any(reason, RETRYABLE_TOKENS):
        decision = "retry"
        confidence = 0.85
        rationale = "transient_runtime_failure"
        actions = [
            "apply_bounded_retry_policy",
            "preserve_original_scope",
        ]
    elif _contains_any(reason, REPLAN_TOKENS):
        decision = "replan"
        confidence = 0.8
        rationale = "goal_or_plan_mismatch"
        actions = [
            "build_replanning_request",
            "require_operator_confirmation",
        ]
    elif topic in {
        "worker.failed",
        "dispatch.failed",
    }:
        decision = "redispatch"
        confidence = 0.7
        rationale = "worker_or_dispatch_failure"
        actions = [
            "release_failed_worker_lease",
            "redispatch_to_available_worker",
        ]
    else:
        decision = "manual_review"
        confidence = 0.6
        rationale = "insufficient_failure_evidence"
        actions = [
            "preserve_current_state",
            "request_operator_review",
        ]

    return {
        "decision": decision,
        "confidence": confidence,
        "rationale": rationale,
        "recommended_actions": actions,
        "evidence": {
            "topic": topic,
            "reason_text": reason,
            "mission_id": payload.get(
                "mission_id"
            ),
            "entry_id": payload.get("entry_id"),
            "worker_id": payload.get(
                "worker_id"
            ),
            "session_id": payload.get(
                "session_id"
            ),
        },
        "autonomous_mutation_allowed": False,
        "autonomous_plan_confirmation": False,
        "operator_confirmation_required": (
            decision in {
                "replan",
                "manual_review",
            }
        ),
    }


def build_replanning_decision(
    event: Mapping[str, Any],
    *,
    engine_id: str,
    now: Any = None,
) -> dict[str, Any]:
    classification = classify_replanning_event(
        event
    )
    source_event_id = str(
        event.get("event_id") or ""
    ).strip()
    if not source_event_id:
        raise ValueError("source_event_id_required")

    identity = {
        "engine_id": engine_id,
        "source_event_id": source_event_id,
        "decision": classification["decision"],
    }
    decision_id = (
        "replanning-decision-"
        f"{fingerprint(identity)[:20]}"
    )

    return seal_replanning_decision(
        {
            "contract": DECISION_CONTRACT,
            "decision_id": decision_id,
            "engine_id": engine_id,
            "source_event_id": source_event_id,
            "source_sequence": event.get(
                "sequence"
            ),
            "source_topic": event.get("topic"),
            "mission_id": _mapping(
                event.get("payload")
            ).get("mission_id"),
            "entry_id": _mapping(
                event.get("payload")
            ).get("entry_id"),
            "worker_id": _mapping(
                event.get("payload")
            ).get("worker_id"),
            "session_id": _mapping(
                event.get("payload")
            ).get("session_id"),
            "decision": classification["decision"],
            "confidence": classification[
                "confidence"
            ],
            "rationale": classification[
                "rationale"
            ],
            "recommended_actions": deepcopy(
                classification[
                    "recommended_actions"
                ]
            ),
            "evidence": deepcopy(
                classification["evidence"]
            ),
            "autonomous_mutation_allowed": False,
            "autonomous_plan_confirmation": False,
            "operator_confirmation_required": (
                classification[
                    "operator_confirmation_required"
                ]
            ),
            "decision_status": "advisory",
            "created_at": time_text(now),
        }
    )


def _publish_decision_event(
    bus: Mapping[str, Any],
    decision: Mapping[str, Any],
    *,
    engine_id: str,
    now: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    topic = (
        f"replanning."
        f"{decision['decision']}"
    )
    return publish(
        bus,
        event_type="mission",
        topic=topic,
        source=engine_id,
        payload={
            "decision_id": decision[
                "decision_id"
            ],
            "mission_id": decision.get(
                "mission_id"
            ),
            "entry_id": decision.get(
                "entry_id"
            ),
            "worker_id": decision.get(
                "worker_id"
            ),
            "session_id": decision.get(
                "session_id"
            ),
            "decision": decision[
                "decision"
            ],
            "confidence": decision[
                "confidence"
            ],
            "rationale": decision[
                "rationale"
            ],
            "recommended_actions": deepcopy(
                decision["recommended_actions"]
            ),
            "operator_confirmation_required": (
                decision[
                    "operator_confirmation_required"
                ]
            ),
            "source_event_id": decision[
                "source_event_id"
            ],
        },
        idempotency_key=(
            f"{engine_id}:"
            f"{decision['decision_id']}"
        ),
        correlation_id=str(
            decision.get("mission_id")
            or decision["decision_id"]
        ),
        causation_id=decision[
            "source_event_id"
        ],
        now=now,
    )


def run_replanning_engine_iteration(
    *,
    engine_state_path: Any,
    max_events: int = 100,
    now: Any = None,
) -> dict[str, Any]:
    if (
        isinstance(max_events, bool)
        or not isinstance(max_events, int)
        or max_events < 1
    ):
        raise ValueError(
            "invalid_replanning_max_events"
        )

    state = load_replanning_engine_state(
        engine_state_path
    )

    if state.get("stop_requested"):
        state["engine_status"] = "stopped"
        state["updated_at"] = time_text(now)
        return save_replanning_engine_state(
            state,
            engine_state_path,
        )

    if state.get("pause_requested"):
        state["engine_status"] = "paused"
        state["updated_at"] = time_text(now)
        return save_replanning_engine_state(
            state,
            engine_state_path,
        )

    bus_path = Path(
        state["event_bus_state_path"]
    )
    bus = load_event_bus_state(bus_path)
    events = replay(
        bus,
        after_sequence=state[
            "last_processed_sequence"
        ],
        limit=max_events,
    )

    if not events:
        state["engine_status"] = "idle"
        state["updated_at"] = time_text(now)
        return save_replanning_engine_state(
            state,
            engine_state_path,
        )

    decisions = _mapping(state.get("decisions"))
    decision_order = list(
        state.get("decision_order") or []
    )
    last_sequence = state[
        "last_processed_sequence"
    ]
    new_decision_created = False

    for event in events:
        last_sequence = max(
            last_sequence,
            int(event.get("sequence") or 0),
        )

        if event.get("topic") not in SUPPORTED_TOPICS:
            state["ignored_event_count"] = int(
                state.get(
                    "ignored_event_count"
                )
                or 0
            ) + 1
            continue

        decision = build_replanning_decision(
            event,
            engine_id=state["engine_id"],
            now=now,
        )
        decision_id = decision["decision_id"]

        if decision_id not in decisions:
            decisions[decision_id] = decision
            decision_order.append(decision_id)
            new_decision_created = True
            state["processed_event_count"] = int(
                state.get(
                    "processed_event_count"
                )
                or 0
            ) + 1

            counter_field = {
                "retry": "retry_count",
                "redispatch": "redispatch_count",
                "replan": "replan_count",
                "manual_review": (
                    "manual_review_count"
                ),
                "complete": "complete_count",
            }.get(decision["decision"])

            if counter_field:
                state[counter_field] = int(
                    state.get(counter_field) or 0
                ) + 1

        bus, published = _publish_decision_event(
            bus,
            decision,
            engine_id=state["engine_id"],
            now=now,
        )
        state["last_event_id"] = published.get(
            "event_id"
        )

    state["decisions"] = decisions
    state["decision_order"] = decision_order
    state["last_processed_sequence"] = (
        last_sequence
    )
    state["engine_status"] = (
        "running"
        if new_decision_created
        else "idle"
    )
    state["updated_at"] = time_text(now)
    state["failure"] = None

    save_event_bus_state(bus, bus_path)
    return save_replanning_engine_state(
        state,
        engine_state_path,
    )


__all__ = [
    "CONTRACT",
    "DECISION_CONTRACT",
    "REPLAN_TOKENS",
    "RETRYABLE_TOKENS",
    "SAFETY_REASONS",
    "SUPPORTED_TOPICS",
    "VALID_DECISIONS",
    "VALID_ENGINE_STATUSES",
    "build_replanning_decision",
    "classify_replanning_event",
    "create_replanning_engine_state",
    "load_replanning_engine_state",
    "request_replanning_engine_action",
    "run_replanning_engine_iteration",
    "save_replanning_engine_state",
    "seal_replanning_decision",
    "seal_replanning_engine_state",
    "validate_replanning_decision",
    "validate_replanning_engine_state",
]
