from __future__ import annotations

import copy

from core.runtime.runtime_incident_reconstruction import reconstruct_runtime_incident
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_recovery_chain import RuntimeRecoveryChainBuilder
from core.runtime.runtime_recovery_plan import build_runtime_recovery_plan
from core.runtime.runtime_recovery_verifier import verify_runtime_recovery_chain


class FakeReplaySession:
    replay_id = "recovery-1-replay"
    source_session_id = "session-1"
    verified = True
    records = [{"phase": "failed"}]


class FakeReplayEngine:
    def replay_session(self, replay_id, source_session_id, payload=None, metadata=None):
        replay = FakeReplaySession()
        replay.replay_id = replay_id
        replay.source_session_id = source_session_id
        return replay


def test_failed_runtime_session_can_create_recovery_chain():
    builder = RuntimeRecoveryChainBuilder(replay_engine=FakeReplayEngine(), journal=RuntimeJournal())
    chain = builder.build_chain(
        recovery_id="recovery-1",
        source_session_id="session-1",
        source_failure={"failure_type": "tool_error", "message": "tool exploded", "task_id": "task-1"},
    )

    payload = chain.to_dict()

    assert payload["recovery_id"] == "recovery-1"
    assert payload["source_session_id"] == "session-1"
    assert payload["source_failure"]["failure_type"] == "tool_error"
    assert payload["status"] == "verified"
    assert payload["verification_result"]["verified"] is True


def test_recovery_plan_contains_failure_source_and_replay_reference():
    plan = build_runtime_recovery_plan(
        recovery_id="recovery-2",
        source_session_id="session-2",
        source_failure={"failure_type": "validation_error", "message": "bad output"},
        replay_reference={"replay_id": "replay-2", "status": "reference_only"},
    )

    payload = plan.to_dict()

    assert payload["source_session_id"] == "session-2"
    assert payload["source_failure"]["failure_type"] == "validation_error"
    assert payload["replay_reference"]["replay_id"] == "replay-2"
    assert any(action["action_type"] == "attach_replay_evidence" for action in payload["actions"])


def test_rollback_needed_case_is_represented_but_not_blindly_executed():
    builder = RuntimeRecoveryChainBuilder(journal=RuntimeJournal())
    chain = builder.build_chain(
        recovery_id="recovery-3",
        source_session_id="session-3",
        source_failure={"failure_type": "mutation_failed", "message": "patch partially applied"},
    )
    payload = chain.to_dict()

    assert payload["status"] == "rollback_required"
    assert payload["recovery_plan"]["rollback_required"] is True
    assert payload["rollback_reference"]["status"] == "required_not_executed"
    assert "does not blindly execute" in payload["rollback_reference"]["reason"]


def test_verification_result_is_attached_to_recovery_chain():
    builder = RuntimeRecoveryChainBuilder(replay_engine=FakeReplayEngine(), journal=RuntimeJournal())
    chain = builder.build_chain(
        recovery_id="recovery-4",
        source_session_id="session-4",
        source_failure={"failure_type": "transient_error", "message": "temporary failure"},
    )

    verification = chain.to_dict()["verification_result"]

    assert verification["status"] == "verified"
    assert verification["checks"]["source_failure_present"] is True
    assert verification["checks"]["recovery_plan_present"] is True
    assert verification["checks"]["audit_events_present"] is True


def test_incident_reconstruction_returns_readable_summary():
    incident = reconstruct_runtime_incident(
        recovery_id="recovery-5",
        source_failure={"failure_type": "timeout", "message": "command timed out", "source_session_id": "session-5"},
        recovery_plan={"plan_id": "plan-5", "status": "planned", "rollback_required": False},
        replay_reference={"replay_id": "replay-5", "status": "reference_only"},
        verification_result={"status": "verified", "verified": True, "reason": "ok"},
        audit_events=[{"event_type": "failure_detected"}],
    )

    assert incident["runtime_phase"] == "runtime_incident_reconstruction"
    assert incident["source_session_id"] == "session-5"
    assert "Runtime recovery recovery-5 handled timeout" in incident["summary"]
    assert incident["timeline"]


def test_audit_events_are_emitted():
    builder = RuntimeRecoveryChainBuilder(journal=RuntimeJournal())
    chain = builder.build_chain(
        recovery_id="recovery-6",
        source_session_id="session-6",
        source_failure={"failure_type": "tool_error", "message": "bad tool"},
    )

    event_types = [event["event_type"] for event in chain.to_dict()["audit_events"]]

    assert "failure_detected" in event_types
    assert "replay_reference_attached" in event_types
    assert "recovery_plan_built" in event_types
    assert "recovery_verified" in event_types


def test_recovery_chain_does_not_mutate_source_session_unexpectedly():
    before = {"status": "failed", "step": {"id": "s1"}, "results": [{"ok": False}]}
    after = copy.deepcopy(before)
    builder = RuntimeRecoveryChainBuilder(replay_engine=FakeReplayEngine(), journal=RuntimeJournal())

    chain = builder.build_chain(
        recovery_id="recovery-7",
        source_session_id="session-7",
        source_failure={"failure_type": "tool_error", "message": "tool failed"},
        source_state_before=before,
        source_state_after=after,
    )

    verification = chain.to_dict()["verification_result"]

    assert before == after
    assert verification["checks"]["source_state_not_mutated"] is True
    assert verification["verified"] is True


def test_verifier_fails_when_source_state_is_mutated():
    plan = build_runtime_recovery_plan(
        recovery_id="recovery-8",
        source_session_id="session-8",
        source_failure={"failure_type": "tool_error", "message": "tool failed"},
        replay_reference={"replay_id": "replay-8"},
    )
    result = verify_runtime_recovery_chain(
        recovery_id="recovery-8",
        plan=plan,
        replay_reference={"replay_id": "replay-8"},
        audit_events=[{"event_type": "failure_detected"}],
        incident_summary={"incident_id": "incident-8"},
        source_state_before={"status": "failed"},
        source_state_after={"status": "running"},
    )

    assert result.verified is False
    assert result.status == "verification_failed"
    assert "source_state_not_mutated" in result.findings
