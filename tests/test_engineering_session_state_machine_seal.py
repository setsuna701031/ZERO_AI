from __future__ import annotations

from core.session.engineering_session_state import (

    ACTIVE_ENGINEERING_SESSION_STATES,
    BLOCKED_REVIEW_ENGINEERING_SESSION_STATES,
    INITIAL_ENGINEERING_SESSION_STATES,
    TERMINAL_ENGINEERING_SESSION_STATES,
)
from core.session.engineering_session_state_machine import (
    ENGINEERING_SESSION_STATE_MACHINE_SCHEMA,
    EngineeringSessionStateMachine,
)
from core.session.engineering_session_transition import ENGINEERING_SESSION_TRANSITION_SCHEMA
from core.session.engineering_session_validator import EngineeringSessionValidator
import pytest

pytestmark = [pytest.mark.contract]



def _record(from_state: str = "created", to_state: str = "active", **changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema": ENGINEERING_SESSION_TRANSITION_SCHEMA,
        "from_state": from_state,
        "to_state": to_state,
        "action": to_state,
        "reason": "seal transition",
        "trigger": "seal_test",
        "evidence": {"test": "engineering_session_state_machine_seal"},
        "source": "seal_test",
        "session_id": "session-seal",
        "task_id": "task-seal",
        "created_at": "2026-06-11T00:00:00+00:00",
        "timestamp": "2026-06-11T00:00:00+00:00",
    }
    record.update(changes)
    return record


def test_formal_state_model_is_explicit() -> None:
    assert INITIAL_ENGINEERING_SESSION_STATES == {"created"}
    assert "active" in ACTIVE_ENGINEERING_SESSION_STATES
    assert {"blocked", "waiting_user"} <= BLOCKED_REVIEW_ENGINEERING_SESSION_STATES
    assert {"completed", "failed", "archived"} <= TERMINAL_ENGINEERING_SESSION_STATES


def test_initial_state_and_valid_transition_pass() -> None:
    machine = EngineeringSessionStateMachine()
    assert machine.current_state({"session_state": "created"}) == "created"
    assert machine.can_transition("created", "active") is True
    result = machine.transition(_record())
    assert result.accepted is True
    assert result.session_state == "active"
    assert result.terminal is False


def test_invalid_and_unknown_transitions_are_rejected() -> None:
    machine = EngineeringSessionStateMachine()
    assert machine.transition(_record("created", "completed")).accepted is False
    assert machine.transition(_record("unknown", "active")).accepted is False
    assert machine.can_transition("unknown", "active") is False


def test_terminal_state_cannot_return_to_active_or_planning_equivalent() -> None:
    machine = EngineeringSessionStateMachine()
    for terminal in TERMINAL_ENGINEERING_SESSION_STATES:
        assert machine.can_transition(terminal, "active") is False
        result = machine.transition(_record(terminal, "active"))
        assert result.accepted is False
        assert result.terminal is True


def test_blocked_can_move_to_review_or_running_equivalent() -> None:
    machine = EngineeringSessionStateMachine()
    assert machine.can_transition("blocked", "waiting_user") is True
    assert machine.can_transition("blocked", "active") is True


def test_transition_record_preserves_contract_and_identity() -> None:
    machine = EngineeringSessionStateMachine()
    record = machine.build_transition_record(
        from_state="created",
        to_state="active",
        reason="plan accepted",
        trigger="planning_complete",
        evidence={"plan_id": "plan-1"},
        source="planner",
        session_id="session-1",
        task_id="task-1",
        created_at="2026-06-11T00:00:00+00:00",
    )
    assert record["schema"] == ENGINEERING_SESSION_TRANSITION_SCHEMA
    assert record["from_state"] == "created"
    assert record["to_state"] == "active"
    assert record["reason"] == "plan accepted"
    assert record["trigger"] == "planning_complete"
    assert record["evidence"] == {"plan_id": "plan-1"}
    assert record["source"] == "planner"
    assert record["session_id"] == "session-1"
    assert record["task_id"] == "task-1"
    assert record["created_at"] == record["timestamp"]

    result = machine.transition(record)
    assert result.to_dict()["schema"] == ENGINEERING_SESSION_STATE_MACHINE_SCHEMA
    assert result.to_dict()["transition_record"] == record


def test_validator_rejects_missing_contract_fields_and_matches_machine() -> None:
    validator = EngineeringSessionValidator()
    machine = EngineeringSessionStateMachine(validator=validator)
    invalid_records = [
        _record(schema=""),
        _record(reason=""),
        _record(trigger=""),
        _record(evidence=[]),
        _record(source=""),
        _record(created_at="", timestamp=""),
        _record(session_id="", task_id=""),
    ]
    for record in invalid_records:
        validation = validator.validate(record)
        result = machine.transition(record)
        assert validation.accepted is False
        assert result.accepted == validation.accepted
        assert result.blocked_reason == validation.blocked_reason


def test_missing_lifecycle_record_does_not_fake_success() -> None:
    result = EngineeringSessionStateMachine().evaluate_lifecycle({}, from_state="created")
    assert result.accepted is False
    assert result.session_state == "created"
    assert result.reason == "engineering_session_transition_rejected"


def test_session_completion_requires_canonical_attestation() -> None:
    result = EngineeringSessionStateMachine().transition(_record("active", "completed"))
    assert result.accepted is False
    assert result.blocked_reason == "canonical_completion_attestation_required"


def test_lifecycle_transition_preserves_session_identity_and_evidence() -> None:
    result = EngineeringSessionStateMachine().evaluate_lifecycle(
        {
            "lifecycle_state": "continuing",
            "reason": "continue",
            "trigger": "cycle_complete",
            "source": "engineering_lifecycle",
            "evidence": {"cycle": 1},
            "session_id": "session-lifecycle",
            "task_id": "task-lifecycle",
        },
        from_state="created",
    )
    record = result.to_dict()["transition_record"]
    assert result.accepted is True
    assert record["session_id"] == "session-lifecycle"
    assert record["task_id"] == "task-lifecycle"
    assert record["evidence"] == {"cycle": 1}
