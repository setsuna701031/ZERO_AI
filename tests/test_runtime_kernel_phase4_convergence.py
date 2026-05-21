from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engineering.repo_scan import build_impacted_plan
from core.runtime.governed_mutation_runtime import run_governed_mutation_runtime
from core.runtime.mutation_gateway import MutationGatewayRequest
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationScope,
    MutationVerificationRequirement,
)
from core.runtime.mutation_verification import MutationVerificationCheck
from core.runtime.runtime_event_bus import RuntimeEventBus
from core.runtime.runtime_events import (
    EvidenceAttachedEvent,
    MutationAppliedEvent,
    RuntimeStateTransitionEvent,
    TransactionCommittedEvent,
    VerificationCompletedEvent,
)
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_kernel_state import RuntimeKernelStateMachine
from core.runtime.runtime_replay_session import RuntimeReplaySession
from core.runtime.runtime_resource_governance import (
    RuntimeBudgetExceeded,
    RuntimeResourceGovernor,
)
from core.runtime.runtime_scheduler_kernel import (
    RuntimeExecutionQueue,
    RuntimeScheduledOperation,
)
from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator


def _request(
    *,
    workspace: Path,
    sandbox: Path,
    rollback: Path,
    reports: Path,
    verification_passed: bool = True,
) -> MutationGatewayRequest:
    return MutationGatewayRequest(
        intent="Update runtime kernel file",
        initiator="test",
        reason="phase 4 convergence",
        relative_paths=("core/runtime/kernel.py",),
        scope=MutationScope(allowed_paths=("core/runtime",)),
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        verification_checks=(
            MutationVerificationCheck(
                name="pytest",
                passed=verification_passed,
                details="ok" if verification_passed else "boom",
            ),
        ),
    )


def test_runtime_event_bus_accepts_typed_events_with_ordering() -> None:
    bus = RuntimeEventBus()
    first = bus.publish_event(
        RuntimeStateTransitionEvent(
            old_state="PENDING",
            new_state="SCANNING",
            reason="scan",
        )
    )
    second = bus.publish_event(
        MutationAppliedEvent(mutation_id="mutation:1", applied_paths=("a.py",))
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert first.timestamp
    assert first.payload.event_type == "RuntimeStateTransitionEvent"
    assert second.payload.payload["applied_paths"] == ["a.py"]


def test_runtime_journal_restores_from_wal_and_reconstructs_events(tmp_path: Path) -> None:
    path = tmp_path / "runtime.wal.jsonl"
    journal = RuntimeJournal(path)
    journal.append_event(
        RuntimeStateTransitionEvent(
            old_state="PENDING",
            new_state="SCANNING",
            reason="scan",
        )
    )
    journal.append_transaction_boundary("commit", "tx:1")

    restored = RuntimeJournal(path)
    reconstruction = restored.reconstruct()

    assert reconstruction["record_count"] == 2
    assert reconstruction["last_sequence"] == 2
    assert reconstruction["state_transitions"][0]["event_type"] == "RuntimeStateTransitionEvent"
    assert reconstruction["transaction_boundaries"][0]["transaction_id"] == "tx:1"


def test_state_machine_emits_and_journals_every_transition() -> None:
    bus = RuntimeEventBus()
    journal = RuntimeJournal()
    machine = RuntimeKernelStateMachine(event_bus=bus, journal=journal)

    machine.transition("SCANNING", reason="scan")
    machine.transition("PLANNING", reason="plan")

    assert [event.event_type for event in machine.events] == [
        "RuntimeStateTransitionEvent",
        "RuntimeStateTransitionEvent",
    ]
    assert [event.event_type for event in bus.get_events()] == [
        "RuntimeStateTransitionEvent",
        "RuntimeStateTransitionEvent",
    ]
    assert len(journal.reconstruct()["state_transitions"]) == 2


def test_transaction_coordinator_journals_commit_and_rejects_rollback_required_commit() -> None:
    bus = RuntimeEventBus()
    journal = RuntimeJournal()
    coordinator = RuntimeTransactionCoordinator(event_bus=bus, journal=journal)
    coordinator.begin_transaction(transaction_id="tx:phase4")
    coordinator.capture_snapshot(
        "tx:phase4",
        files=({"relative_path": "core/runtime/kernel.py", "existed": True},),
    )
    coordinator.mark_verified("tx:phase4")
    result = coordinator.commit("tx:phase4")

    assert result.committed is True
    assert any(
        event.event_type == "TransactionCommittedEvent"
        for event in bus.get_events()
    )
    assert "transaction_commit" in [
        record.record_type for record in journal.records
    ]

    blocked = RuntimeTransactionCoordinator(journal=RuntimeJournal())
    blocked.begin_transaction(transaction_id="tx:block")
    blocked.mark_rollback_required("tx:block")
    with pytest.raises(RuntimeError):
        blocked.commit("tx:block")


def test_runtime_scheduler_queue_requires_transaction_and_checkpoint() -> None:
    queue = RuntimeExecutionQueue()

    with pytest.raises(ValueError):
        queue.enqueue(
        RuntimeScheduledOperation(
            operation_id="op:1",
            operation_type="mutation",
            transaction_id="tx:1",
            capability_node_id="runtime:governed_mutation",
            intent_id="intent:1",
        )
        )

    queued = queue.enqueue(
        RuntimeScheduledOperation(
            operation_id="op:1",
            operation_type="mutation",
            transaction_id="tx:1",
            checkpoint_id="checkpoint:1",
            capability_node_id="runtime:governed_mutation",
            intent_id="intent:1",
        )
    )
    operation, remaining = queued.dispatch_next()

    assert operation is not None
    assert operation.operation_id == "op:1"
    assert remaining.operations == ()


def test_runtime_resource_governor_blocks_budget_exhaustion() -> None:
    governor = RuntimeResourceGovernor(limits={"recovery": 1})
    governor = governor.consume("recovery")

    with pytest.raises(RuntimeBudgetExceeded):
        governor.consume("recovery")


def test_runtime_replay_session_reconstructs_journal_topology() -> None:
    journal = RuntimeJournal()
    journal.append_event(
        RuntimeStateTransitionEvent(
            old_state="PENDING",
            new_state="SCANNING",
            reason="scan",
        )
    )
    journal.append_event(VerificationCompletedEvent(verification_id="verify:1", passed=True))
    journal.append_event(EvidenceAttachedEvent(evidence_id="evidence:1"))
    journal.append_event(TransactionCommittedEvent(transaction_id="tx:1"))

    artifact = RuntimeReplaySession(journal, replay_id="replay:1").reconstruct()
    payload = artifact.to_dict()

    assert payload["replayable"] is True
    assert payload["session_snapshot"]["state_progression"]
    assert payload["session_snapshot"]["verification_results"]
    assert payload["session_snapshot"]["evidence_bundles"]


def test_governed_runtime_persists_wal_events_and_replay_session(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    target = workspace / "core" / "runtime" / "kernel.py"
    target.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")

    source = sandbox / "core" / "runtime" / "kernel.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    result = run_governed_mutation_runtime(
        _request(
            workspace=workspace,
            sandbox=sandbox,
            rollback=rollback,
            reports=reports,
        )
    )
    payload = result.to_dict()
    wal_path = Path(payload["artifact_paths"]["governed_result"]).parent / "runtime.wal.jsonl"
    wal_records = [
        json.loads(line)
        for line in wal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_types = [
        record["payload"].get("event_type")
        for record in wal_records
        if record["record_type"] == "runtime_event"
    ]

    assert wal_path.exists()
    assert "RuntimeStateTransitionEvent" in event_types
    assert "MutationAppliedEvent" in event_types
    assert "VerificationCompletedEvent" in event_types
    assert "EvidenceAttachedEvent" in event_types
    assert "TransactionCommittedEvent" in event_types
    assert payload["runtime_replay"]["runtime_session_snapshot"]["wal_reconstruction"]["record_count"]
    assert payload["runtime_evidence_bundle"]["metadata"]["runtime_wal"]["record_count"]


def test_repo_understanding_exposes_runtime_phase4_topology_fields(tmp_path: Path) -> None:
    _write(tmp_path / "core" / "runtime" / "alpha.py", "from core.runtime import beta\n")
    _write(tmp_path / "core" / "runtime" / "beta.py", "VALUE = 1\n")
    _write(tmp_path / "tests" / "test_alpha.py", "def test_alpha(): pass\n")

    plan = build_impacted_plan(
        "Update alpha runtime",
        changed_files=("core/runtime/alpha.py",),
        repo_root=tmp_path,
    )
    topology = plan.to_dict()["impacted_runtime_topology"]

    assert topology["runtime_dependency_chains"]
    assert topology["mutation_blast_radius"]["recursive_dependency_impact"]["recursive"] is True
    assert topology["runtime_ownership_surfaces"]["core/runtime"]
    assert topology["verification_topology_mapping"]["requires_targeted_verification"] is True
    assert topology["transaction_risk_score"] >= 1


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
