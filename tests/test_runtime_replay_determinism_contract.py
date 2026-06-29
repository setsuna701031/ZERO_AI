from __future__ import annotations

from core.runtime.runtime_replay_freeze import (

    ReplayMode,
    assert_replay_is_deterministic,
    create_replay_run,
    normalize_replay_input,
    replay_read_only,
    replay_verify_only,
)
from core.runtime.runtime_transaction_registry import (
    create_transaction,
    list_transactions,
)
import pytest

pytestmark = [pytest.mark.contract]



def test_same_input_log_produces_same_normalized_digest() -> None:
    first = create_replay_run(event_log=_events(), mode=ReplayMode.READ_ONLY)
    second = create_replay_run(event_log=_events(), mode=ReplayMode.READ_ONLY)

    assert first.normalized_digest == second.normalized_digest
    assert assert_replay_is_deterministic(first, second) is True


def test_event_ordering_is_normalized() -> None:
    ordered = normalize_replay_input(_events(order=(1, 2)))["events"]
    reversed_order = normalize_replay_input(_events(order=(2, 1)))["events"]

    assert ordered == reversed_order


def test_timestamps_are_normalized_out_of_deterministic_digest() -> None:
    first = create_replay_run(event_log=_events(timestamp="2026-01-01T00:00:00Z"))
    second = create_replay_run(event_log=_events(timestamp="2026-05-26T00:00:00Z"))

    assert first.normalized_digest == second.normalized_digest


def test_audit_refs_are_preserved_but_not_fresh_authority() -> None:
    run = create_replay_run(event_log=_events(audit_refs=["audit:original-authority"]))

    assert run.audit_refs == ("audit:original-authority",)
    assert run.authority_required is False
    assert run.mutation_allowed is False


def test_source_transaction_ids_are_preserved() -> None:
    run = create_replay_run(
        event_log=_events(transaction_id="runtime_tx:source"),
        source_trace_id="trace-source",
    )

    assert run.source_transaction_ids == ("runtime_tx:source",)
    assert run.source_trace_id == "trace-source"


def test_replay_created_transaction_ids_differ_from_source_ids() -> None:
    from tests.authority_test_support import owned_step_executor

    source = create_transaction(
        task_id="task-source-replay",
        step_id="step-source-replay",
        trace_id="trace-source-replay",
        authority_source="execution_gateway",
        surface="write_file",
        affected_files=["workspace/shared/source-replay.txt"],
    )
    result = owned_step_executor().execute_step(
        {
            "type": "replay_mutation",
            "target_path": "workspace/shared/replay-created.txt",
            "replay_source": "replay:created",
            "original_transaction_id": source.transaction_id,
            "original_trace_id": source.trace_id,
        },
        context={"execution_authority": _authority()},
    )

    assert result["runtime_transaction"]["transaction_id"] != source.transaction_id
    assert result["runtime_transaction"]["original_transaction_id"] == source.transaction_id


def test_verify_only_replay_cannot_commit_mutation() -> None:
    result = replay_verify_only(
        [
            {
                "event_id": "mutation",
                "sequence": 1,
                "surface": "replay_mutation",
                "event_type": "replay_mutation",
            }
        ]
    )

    assert result["mode"] == "verify_only"
    assert result["result_state"] == "failed"
    assert result["mutation_allowed"] is False


def test_read_only_replay_cannot_change_transaction_registry() -> None:
    before = len(list_transactions())
    replay_read_only(_events())

    assert len(list_transactions()) == before


def test_replay_failure_records_deterministic_failure_reason() -> None:
    first = create_replay_run(
        event_log=[{"event_id": "m", "sequence": 1, "surface": "replay_mutation"}],
        mode=ReplayMode.READ_ONLY,
    )
    second = create_replay_run(
        event_log=[{"event_id": "m", "sequence": 1, "surface": "replay_mutation"}],
        mode=ReplayMode.READ_ONLY,
    )

    assert first.result_state == "failed"
    assert first.failure_reason == "mutation_intent_not_allowed_in_read_only_replay"
    assert first.failure_reason == second.failure_reason
    assert first.normalized_digest == second.normalized_digest


def _events(
    *,
    order: tuple[int, int] = (1, 2),
    timestamp: str = "2026-05-26T00:00:00Z",
    audit_refs: list[str] | None = None,
    transaction_id: str = "",
) -> list[dict]:
    events = {
        1: {
            "event_id": "event-a",
            "sequence": 1,
            "event_type": "replay_read",
            "surface": "replay_read",
            "timestamp": timestamp,
            "audit_refs": audit_refs or ["audit:original"],
            "transaction_id": transaction_id,
        },
        2: {
            "event_id": "event-b",
            "sequence": 2,
            "event_type": "audit_read",
            "surface": "audit_read",
            "timestamp": timestamp,
        },
    }
    return [events[index] for index in order]


def _authority() -> dict:
    return {
        "task_id": "task-replay-created",
        "step_id": "step-replay-created",
        "authority_source": "execution_gateway",
        "runtime_session": "session-replay-created",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": "trace-replay-created",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "mutation",
    }
