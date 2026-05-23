from __future__ import annotations

import copy

from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_recovery_chain import RuntimeRecoveryChainBuilder
from core.runtime.runtime_recovery_executor import RuntimeRecoveryExecutor
from core.runtime.runtime_recovery_policy import RuntimeRecoveryPolicy
from core.runtime.runtime_recovery_state import (
    RECOVERY_CONTINUATION_READY,
    RECOVERY_CONTINUATION_REQUIRES_ROLLBACK,
    RECOVERY_EXECUTION_STATUS_BLOCKED,
    RECOVERY_EXECUTION_STATUS_COMPLETED,
)


class FakeReplaySession:
    replay_id = "recovery-exec-replay"
    source_session_id = "session-exec"
    verified = True
    records = [{"phase": "failed"}]


class FakeReplayEngine:
    def replay_session(self, replay_id, source_session_id, payload=None, metadata=None):
        replay = FakeReplaySession()
        replay.replay_id = replay_id
        replay.source_session_id = source_session_id
        return replay


def build_verified_chain():
    builder = RuntimeRecoveryChainBuilder(replay_engine=FakeReplayEngine(), journal=RuntimeJournal())
    return builder.build_chain(
        recovery_id="recovery-exec-1",
        source_session_id="session-exec-1",
        source_failure={"failure_type": "tool_error", "message": "tool failed", "task_id": "task-exec-1"},
    )


def build_rollback_required_chain():
    builder = RuntimeRecoveryChainBuilder(journal=RuntimeJournal())
    return builder.build_chain(
        recovery_id="recovery-exec-rollback",
        source_session_id="session-exec-rollback",
        source_failure={"failure_type": "mutation_failed", "message": "patch partially applied"},
    )


def test_verified_recovery_chain_executes_safe_recovery_actions():
    chain = build_verified_chain()
    executor = RuntimeRecoveryExecutor(journal=RuntimeJournal())
    source_state = {"status": "failed", "last_error": "tool failed"}

    result = executor.execute_recovery(chain, source_state=source_state)
    payload = result.to_dict()

    assert payload["status"] == RECOVERY_EXECUTION_STATUS_COMPLETED
    assert payload["continuation_decision"] == RECOVERY_CONTINUATION_READY
    assert payload["source_state_mutated"] is False
    assert payload["source_state_before"] == source_state
    assert payload["source_state_after"] == source_state
    assert any(item["action_type"] == "execute_replay_candidate" for item in payload["action_results"])
    assert any(item["action_type"] == "verify_recovery" for item in payload["action_results"])


def test_rollback_required_chain_prepares_but_does_not_blindly_execute_rollback():
    chain = build_rollback_required_chain()
    executor = RuntimeRecoveryExecutor(journal=RuntimeJournal())

    result = executor.execute_recovery(chain, source_state={"status": "failed"})
    payload = result.to_dict()

    assert payload["status"] == RECOVERY_EXECUTION_STATUS_BLOCKED
    assert payload["continuation_decision"] == RECOVERY_CONTINUATION_REQUIRES_ROLLBACK
    assert payload["source_state_mutated"] is False
    assert payload["source_state_before"] == {"status": "failed"}
    assert payload["source_state_after"] == {"status": "failed"}
    prepare = next(item for item in payload["action_results"] if item["action_type"] == "prepare_rollback")
    assert prepare["status"] == RECOVERY_EXECUTION_STATUS_COMPLETED
    assert prepare["result"]["mode"] == "rollback_prepared_not_executed"
    rollback = next(item for item in payload["action_results"] if item["action_type"] == "execute_rollback")
    assert rollback["status"] == RECOVERY_EXECUTION_STATUS_BLOCKED
    assert rollback["result"]["policy_decision"]["requires_approval"] is True
    assert rollback["result"]["policy_decision"]["allowed"] is False


def test_high_risk_rollback_can_only_run_with_explicit_approval_and_handler():
    chain = build_rollback_required_chain()
    calls = []

    def rollback_handler(action, context):
        calls.append(action["action_type"])
        state = copy.deepcopy(context["source_state"])
        state["status"] = "rollback_applied"
        return {"ok": True, "mode": "test_rollback_handler", "source_state": state}

    policy = RuntimeRecoveryPolicy(allow_high_risk_execution=True)
    executor = RuntimeRecoveryExecutor(
        policy=policy,
        journal=RuntimeJournal(),
        handlers={"execute_rollback": rollback_handler},
    )

    result = executor.execute_recovery(
        chain,
        source_state={"status": "failed"},
        approval={"approved": True, "approval_id": "approval-1"},
    )
    payload = result.to_dict()

    assert "execute_rollback" in calls
    assert payload["source_state_mutated"] is True
    assert payload["source_state_after"]["status"] == "rollback_applied"
    rollback = next(item for item in payload["action_results"] if item["action_type"] == "execute_rollback")
    assert rollback["status"] == RECOVERY_EXECUTION_STATUS_COMPLETED


def test_unrecoverable_chain_blocks_runtime_continuation():
    builder = RuntimeRecoveryChainBuilder(journal=RuntimeJournal())
    chain = builder.build_chain(
        recovery_id="recovery-exec-unrecoverable",
        source_session_id="session-exec-unrecoverable",
        source_failure={"failure_type": "approval_denied", "message": "user denied approval"},
    )
    executor = RuntimeRecoveryExecutor(journal=RuntimeJournal())

    result = executor.execute_recovery(chain, source_state={"status": "failed"})
    payload = result.to_dict()

    assert payload["status"] == RECOVERY_EXECUTION_STATUS_BLOCKED
    assert payload["continuation_decision"] == "unrecoverable"
    assert any(item["status"] == RECOVERY_EXECUTION_STATUS_BLOCKED for item in payload["action_results"])


def test_recovery_execution_emits_audit_events_and_journal_records():
    chain = build_verified_chain()
    journal = RuntimeJournal()
    executor = RuntimeRecoveryExecutor(journal=journal)

    result = executor.execute_recovery(chain, source_state={"status": "failed"})
    payload = result.to_dict()

    event_types = [event["event_type"] for event in payload["audit_events"]]
    assert "recovery_execution_started" in event_types
    assert "recovery_execution_finished" in event_types
    assert "recovery_action_completed" in event_types
    reconstruction = journal.reconstruct()
    record_types = [record["record_type"] for record in reconstruction["records"]]
    assert "runtime_recovery_execution_audit_event" in record_types
    assert "runtime_recovery_execution_result" in record_types


def test_execution_result_can_be_read_back_from_store():
    chain = build_verified_chain()
    executor = RuntimeRecoveryExecutor(journal=RuntimeJournal())

    result = executor.execute_recovery(chain, source_state={"status": "failed"})
    stored = executor.store.get(result.execution_id)

    assert stored is not None
    assert stored.to_dict()["execution_id"] == result.execution_id
    assert len(executor.store.list_results()) == 1
