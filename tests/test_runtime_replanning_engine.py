from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from core.runtime.runtime_event_bus import (
    create_event_bus_state,
    load_event_bus_state,
    publish,
    replay,
    save_event_bus_state,
)
from core.runtime.runtime_replanning_engine import (
    CONTRACT,
    DECISION_CONTRACT,
    build_replanning_decision,
    classify_replanning_event,
    create_replanning_engine_state,
    load_replanning_engine_state,
    request_replanning_engine_action,
    run_replanning_engine_iteration,
    save_replanning_engine_state,
    validate_replanning_decision,
    validate_replanning_engine_state,
)


NOW = datetime(2026, 7, 12, 8, 0, 0, tzinfo=timezone.utc)


def _create_engine(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    event_bus_path = tmp_path / "event-bus.json"
    engine_state_path = tmp_path / "replanning-engine.json"

    bus = create_event_bus_state(
        state_path=event_bus_path,
        bus_name="primary",
        now=NOW,
    )
    save_event_bus_state(bus, event_bus_path)

    engine = create_replanning_engine_state(
        state_path=engine_state_path,
        event_bus_state_path=event_bus_path,
        engine_name="primary",
        now=NOW,
    )
    save_replanning_engine_state(
        engine,
        engine_state_path,
    )
    return event_bus_path, engine_state_path, engine


def _event(
    *,
    topic: str,
    payload: dict[str, Any],
    event_type: str = "worker",
    sequence: int = 1,
) -> dict[str, Any]:
    from core.runtime.runtime_event_bus import seal_event

    return seal_event(
        {
            "contract": "zero.runtime.event.v1",
            "event_id": f"event-{sequence}",
            "sequence": sequence,
            "event_type": event_type,
            "topic": topic,
            "source": "test-suite",
            "payload": deepcopy(payload),
            "idempotency_key": None,
            "correlation_id": payload.get(
                "mission_id"
            ),
            "causation_id": None,
            "created_at": NOW.isoformat(),
        }
    )


def test_create_save_and_load_engine_state(
    tmp_path: Path,
) -> None:
    event_bus_path, engine_state_path, state = (
        _create_engine(tmp_path)
    )

    assert state["contract"] == CONTRACT
    assert state["engine_name"] == "primary"
    assert state["engine_status"] == "created"
    assert state["event_bus_state_path"] == str(
        event_bus_path.resolve(strict=False)
    )
    assert state["last_processed_sequence"] == 0
    assert state["decisions"] == {}
    assert state["decision_order"] == []
    assert validate_replanning_engine_state(state) == []

    loaded = load_replanning_engine_state(
        engine_state_path
    )

    assert loaded == state
    assert loaded["engine_fingerprint"] == (
        state["engine_fingerprint"]
    )


@pytest.mark.parametrize(
    ("topic", "payload", "expected"),
    [
        (
            "mission.completed",
            {"mission_id": "mission-1"},
            "complete",
        ),
        (
            "scheduler.completed",
            {"mission_id": "mission-1"},
            "complete",
        ),
        (
            "dispatch.no_worker_available",
            {
                "mission_id": "mission-1",
                "entry_id": "entry-1",
            },
            "redispatch",
        ),
        (
            "worker.failed",
            {
                "mission_id": "mission-1",
                "reason": "temporary timeout",
            },
            "retry",
        ),
        (
            "worker.blocked",
            {
                "mission_id": "mission-1",
                "reason": "validation_failure",
            },
            "replan",
        ),
        (
            "scheduler.failed",
            {
                "mission_id": "mission-1",
                "reason": "approval_required",
            },
            "manual_review",
        ),
        (
            "dispatch.failed",
            {
                "mission_id": "mission-1",
                "reason": "worker crashed",
            },
            "redispatch",
        ),
        (
            "unknown.topic",
            {"mission_id": "mission-1"},
            "ignore",
        ),
    ],
)
def test_classify_replanning_event(
    topic: str,
    payload: dict[str, Any],
    expected: str,
) -> None:
    result = classify_replanning_event(
        _event(
            topic=topic,
            payload=payload,
            event_type=(
                "mission"
                if topic.startswith("mission.")
                else "scheduler"
                if topic.startswith("scheduler.")
                else "worker"
            ),
        )
    )

    assert result["decision"] == expected
    assert result[
        "autonomous_mutation_allowed"
    ] is False
    assert result[
        "autonomous_plan_confirmation"
    ] is False

    if expected in {"replan", "manual_review"}:
        assert result[
            "operator_confirmation_required"
        ] is True
    else:
        assert result[
            "operator_confirmation_required"
        ] is False


def test_build_replanning_decision_is_valid(
    tmp_path: Path,
) -> None:
    _, _, state = _create_engine(tmp_path)
    event = _event(
        topic="worker.failed",
        payload={
            "mission_id": "mission-1",
            "entry_id": "entry-1",
            "worker_id": "worker-1",
            "session_id": "session-1",
            "reason": "temporary timeout",
        },
    )

    decision = build_replanning_decision(
        event,
        engine_id=state["engine_id"],
        now=NOW,
    )

    assert decision["contract"] == DECISION_CONTRACT
    assert decision["source_event_id"] == (
        event["event_id"]
    )
    assert decision["source_topic"] == "worker.failed"
    assert decision["decision"] == "retry"
    assert decision["mission_id"] == "mission-1"
    assert decision["worker_id"] == "worker-1"
    assert decision["session_id"] == "session-1"
    assert decision["decision_status"] == "advisory"
    assert decision[
        "autonomous_mutation_allowed"
    ] is False
    assert validate_replanning_decision(decision) == []


def test_engine_iteration_processes_supported_event(
    tmp_path: Path,
) -> None:
    event_bus_path, engine_state_path, _ = (
        _create_engine(tmp_path)
    )
    bus = load_event_bus_state(event_bus_path)
    bus, source_event = publish(
        bus,
        event_type="worker",
        topic="worker.failed",
        source="worker-1",
        payload={
            "mission_id": "mission-1",
            "entry_id": "entry-1",
            "worker_id": "worker-1",
            "reason": "temporary timeout",
        },
        now=NOW,
    )
    save_event_bus_state(bus, event_bus_path)

    result = run_replanning_engine_iteration(
        engine_state_path=engine_state_path,
        now=NOW,
    )

    assert result["engine_status"] == "running"
    assert result["processed_event_count"] == 1
    assert result["retry_count"] == 1
    assert result["last_processed_sequence"] == (
        source_event["sequence"]
    )
    assert len(result["decision_order"]) == 1

    decision = result["decisions"][
        result["decision_order"][0]
    ]
    assert decision["decision"] == "retry"
    assert decision["source_event_id"] == (
        source_event["event_id"]
    )
    assert result["last_event_id"] is not None

    loaded_bus = load_event_bus_state(
        event_bus_path
    )
    topics = [
        event["topic"]
        for event in replay(loaded_bus)
    ]
    assert "replanning.retry" in topics


def test_engine_iteration_ignores_unsupported_event(
    tmp_path: Path,
) -> None:
    event_bus_path, engine_state_path, _ = (
        _create_engine(tmp_path)
    )
    bus = load_event_bus_state(event_bus_path)
    bus, source_event = publish(
        bus,
        event_type="audit",
        topic="audit.recorded",
        source="audit-service",
        payload={"record_id": "audit-1"},
        now=NOW,
    )
    save_event_bus_state(bus, event_bus_path)

    result = run_replanning_engine_iteration(
        engine_state_path=engine_state_path,
        now=NOW,
    )

    assert result["processed_event_count"] == 0
    assert result["ignored_event_count"] == 1
    assert result["decision_order"] == []
    assert result["last_processed_sequence"] == (
        source_event["sequence"]
    )


def test_engine_iteration_is_idempotent(
    tmp_path: Path,
) -> None:
    event_bus_path, engine_state_path, _ = (
        _create_engine(tmp_path)
    )
    bus = load_event_bus_state(event_bus_path)
    bus, _ = publish(
        bus,
        event_type="scheduler",
        topic="dispatch.no_worker_available",
        source="dispatch-coordinator-1",
        payload={
            "mission_id": "mission-1",
            "entry_id": "entry-1",
        },
        now=NOW,
    )
    save_event_bus_state(bus, event_bus_path)

    first = run_replanning_engine_iteration(
        engine_state_path=engine_state_path,
        now=NOW,
    )
    second = run_replanning_engine_iteration(
        engine_state_path=engine_state_path,
        now=NOW,
    )

    assert first["processed_event_count"] == 1
    assert first["redispatch_count"] == 1
    assert second["processed_event_count"] == 1
    assert second["redispatch_count"] == 1
    assert second["decision_order"] == (
        first["decision_order"]
    )
    assert second["engine_status"] == "idle"


def test_engine_iteration_processes_multiple_events(
    tmp_path: Path,
) -> None:
    event_bus_path, engine_state_path, _ = (
        _create_engine(tmp_path)
    )
    bus = load_event_bus_state(event_bus_path)

    bus, _ = publish(
        bus,
        event_type="worker",
        topic="worker.failed",
        source="worker-1",
        payload={
            "mission_id": "mission-1",
            "reason": "temporary timeout",
        },
        now=NOW,
    )
    bus, _ = publish(
        bus,
        event_type="scheduler",
        topic="scheduler.failed",
        source="scheduler-1",
        payload={
            "mission_id": "mission-2",
            "reason": "approval_required",
        },
        now=NOW,
    )
    bus, _ = publish(
        bus,
        event_type="mission",
        topic="mission.completed",
        source="mission-runtime",
        payload={
            "mission_id": "mission-3",
        },
        now=NOW,
    )
    save_event_bus_state(bus, event_bus_path)

    result = run_replanning_engine_iteration(
        engine_state_path=engine_state_path,
        max_events=10,
        now=NOW,
    )

    assert result["processed_event_count"] == 3
    assert result["retry_count"] == 1
    assert result["manual_review_count"] == 1
    assert result["complete_count"] == 1
    assert len(result["decision_order"]) == 3


def test_engine_iteration_respects_max_events(
    tmp_path: Path,
) -> None:
    event_bus_path, engine_state_path, _ = (
        _create_engine(tmp_path)
    )
    bus = load_event_bus_state(event_bus_path)

    for index in range(3):
        bus, _ = publish(
            bus,
            event_type="worker",
            topic="worker.failed",
            source=f"worker-{index}",
            payload={
                "mission_id": f"mission-{index}",
                "reason": "temporary timeout",
            },
            now=NOW,
        )
    save_event_bus_state(bus, event_bus_path)

    first = run_replanning_engine_iteration(
        engine_state_path=engine_state_path,
        max_events=2,
        now=NOW,
    )
    second = run_replanning_engine_iteration(
        engine_state_path=engine_state_path,
        max_events=2,
        now=NOW,
    )

    assert first["processed_event_count"] == 2
    assert second["processed_event_count"] == 3
    assert second["retry_count"] == 3


@pytest.mark.parametrize(
    ("action", "expected_status", "pause", "stop"),
    [
        ("pause", "paused", True, False),
        ("resume", "idle", False, False),
        ("stop", "stopped", False, True),
    ],
)
def test_request_replanning_engine_action(
    tmp_path: Path,
    action: str,
    expected_status: str,
    pause: bool,
    stop: bool,
) -> None:
    _, _, state = _create_engine(tmp_path)

    result = request_replanning_engine_action(
        state,
        action,
        now=NOW,
    )

    assert result["engine_status"] == expected_status
    assert result["pause_requested"] is pause
    assert result["stop_requested"] is stop
    assert validate_replanning_engine_state(result) == []


def test_paused_engine_does_not_process_events(
    tmp_path: Path,
) -> None:
    event_bus_path, engine_state_path, state = (
        _create_engine(tmp_path)
    )
    bus = load_event_bus_state(event_bus_path)
    bus, _ = publish(
        bus,
        event_type="worker",
        topic="worker.failed",
        source="worker-1",
        payload={
            "mission_id": "mission-1",
            "reason": "temporary timeout",
        },
        now=NOW,
    )
    save_event_bus_state(bus, event_bus_path)

    state = request_replanning_engine_action(
        state,
        "pause",
        now=NOW,
    )
    save_replanning_engine_state(
        state,
        engine_state_path,
    )

    result = run_replanning_engine_iteration(
        engine_state_path=engine_state_path,
        now=NOW,
    )

    assert result["engine_status"] == "paused"
    assert result["processed_event_count"] == 0
    assert result["last_processed_sequence"] == 0


def test_stopped_engine_does_not_process_events(
    tmp_path: Path,
) -> None:
    event_bus_path, engine_state_path, state = (
        _create_engine(tmp_path)
    )
    bus = load_event_bus_state(event_bus_path)
    bus, _ = publish(
        bus,
        event_type="worker",
        topic="worker.failed",
        source="worker-1",
        payload={
            "mission_id": "mission-1",
            "reason": "temporary timeout",
        },
        now=NOW,
    )
    save_event_bus_state(bus, event_bus_path)

    state = request_replanning_engine_action(
        state,
        "stop",
        now=NOW,
    )
    save_replanning_engine_state(
        state,
        engine_state_path,
    )

    result = run_replanning_engine_iteration(
        engine_state_path=engine_state_path,
        now=NOW,
    )

    assert result["engine_status"] == "stopped"
    assert result["processed_event_count"] == 0
    assert result["last_processed_sequence"] == 0


def test_tampered_decision_is_rejected(
    tmp_path: Path,
) -> None:
    _, _, state = _create_engine(tmp_path)
    decision = build_replanning_decision(
        _event(
            topic="worker.failed",
            payload={
                "mission_id": "mission-1",
                "reason": "temporary timeout",
            },
        ),
        engine_id=state["engine_id"],
        now=NOW,
    )
    decision["decision"] = "manual_review"

    reasons = validate_replanning_decision(
        decision
    )

    assert (
        "replanning_decision_fingerprint_mismatch"
        in reasons
    )


def test_tampered_engine_state_is_rejected(
    tmp_path: Path,
) -> None:
    _, _, state = _create_engine(tmp_path)
    state["processed_event_count"] = 999

    reasons = validate_replanning_engine_state(
        state
    )

    assert (
        "replanning_engine_fingerprint_mismatch"
        in reasons
    )
