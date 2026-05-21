from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.governed_mutation_runtime import run_governed_mutation_runtime
from core.runtime.mutation_gateway import MutationGatewayRequest
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationRiskLevel,
    MutationScope,
    MutationVerificationRequirement,
)
from core.runtime.mutation_verification import MutationVerificationCheck
from core.runtime.runtime_capability_graph import (
    build_mutation_capability_graph,
)
from core.runtime.runtime_distributed import (
    RuntimeDistributedEventEnvelope,
    RuntimeDistributedReplayArtifact,
    RuntimeExecutionShard,
    RuntimeWorkerDescriptor,
)
from core.runtime.runtime_events import RuntimeStateTransitionEvent
from core.runtime.runtime_intent_governance import (
    RuntimeIntentPolicy,
    classify_runtime_intent,
)
from core.runtime.runtime_isolation_boundary import RuntimeIsolationBoundary
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_memory_model import build_runtime_memory_snapshot
from core.runtime.runtime_replay_session import RuntimeReplaySession


def test_runtime_memory_snapshot_is_immutable_and_deterministic() -> None:
    source = {"status": "running", "items": ["a"]}
    snapshot = build_runtime_memory_snapshot(
        checkpoint_id="checkpoint:1",
        state=source,
        transactions={"tx:1": {"status": "active"}},
    )
    same = build_runtime_memory_snapshot(
        checkpoint_id="checkpoint:1",
        state={"items": ["a"], "status": "running"},
        transactions={"tx:1": {"status": "active"}},
    )
    source["status"] = "mutated"

    assert snapshot.fingerprint == same.fingerprint
    assert snapshot.view().state.get("status") == "running"
    with pytest.raises(TypeError):
        snapshot.state["status"] = "hidden-mutation"  # type: ignore[index]


def test_runtime_isolation_boundary_stages_and_rolls_back_without_workspace_mutation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    staging = tmp_path / "staging"
    target = workspace / "core" / "runtime" / "kernel.py"
    source = sandbox / "core" / "runtime" / "kernel.py"
    target.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")
    source.write_text("VERSION = 2\n", encoding="utf-8")

    boundary = RuntimeIsolationBoundary(
        workspace_root=workspace,
        sandbox_root=sandbox,
        rollback_root=rollback,
        staging_root=staging,
        transaction_id="tx:1",
        allowed_paths=("core/runtime",),
    )
    mutation = boundary.mutation_sandbox().stage_paths(
        sandbox,
        ("core/runtime/kernel.py",),
    )
    verification = boundary.verification_sandbox(mutation.filesystem)

    assert mutation.filesystem.read_staged_text("core/runtime/kernel.py") == "VERSION = 2\n"
    assert target.read_text(encoding="utf-8") == "VERSION = 1\n"
    assert verification.verification_root() == staging
    rolled_back = mutation.filesystem.rollback()
    assert rolled_back.staged_paths == ()
    assert target.read_text(encoding="utf-8") == "VERSION = 1\n"


def test_capability_graph_enforces_mutation_scope_and_inheritance() -> None:
    graph = build_mutation_capability_graph(
        allowed_paths=("core/runtime",),
        denied_paths=("core/runtime/secrets",),
        runtime_surfaces=("core/runtime",),
    )

    assert graph.validate_mutation("runtime:governed_mutation", ("core/runtime/kernel.py",))
    with pytest.raises(PermissionError):
        graph.validate_mutation("runtime:governed_mutation", ("core/tools/tool.py",))
    with pytest.raises(PermissionError):
        graph.validate_mutation("runtime:governed_mutation", ("core/runtime/secrets/key.py",))


def test_intent_policy_gates_recursive_and_self_edit() -> None:
    policy = RuntimeIntentPolicy()
    recursive = classify_runtime_intent(
        description="recursive repair runtime loop",
        requested_paths=("core/runtime/kernel.py",),
    )
    self_edit = classify_runtime_intent(
        description="self-edit runtime kernel",
        requested_paths=("core/runtime/kernel.py",),
    )

    assert policy.evaluate(recursive).allowed is False
    assert policy.evaluate(self_edit).allowed is False
    assert RuntimeIntentPolicy(allow_recursive_repair=True).evaluate(recursive).allowed is True


def test_distributed_replay_artifact_is_wal_and_checkpoint_compatible() -> None:
    journal = RuntimeJournal()
    event = RuntimeStateTransitionEvent(
        old_state="PENDING",
        new_state="SCANNING",
        reason="scan",
    )
    journal.append_event(event)
    replay = RuntimeReplaySession(journal, replay_id="replay:1").reconstruct()
    worker = RuntimeWorkerDescriptor(
        worker_id="worker:1",
        capabilities=("runtime:governed_mutation",),
        checkpoint_id="checkpoint:1",
        transaction_id="tx:1",
    )
    shard = RuntimeExecutionShard(
        shard_id="shard:1",
        worker=worker,
        operation_ids=("op:1",),
        transaction_id="tx:1",
        checkpoint_id="checkpoint:1",
    )
    envelope = RuntimeDistributedEventEnvelope.from_event(
        worker=worker,
        shard=shard,
        event=event,
    )
    artifact = RuntimeDistributedReplayArtifact.from_replay(
        replay,
        workers=(worker,),
        shards=(shard,),
        envelopes=(envelope,),
    ).to_dict()

    assert artifact["transaction_aware"] is True
    assert artifact["checkpoint_compatible"] is True
    assert artifact["workers"][0]["checkpoint_id"] == "checkpoint:1"
    assert artifact["event_envelopes"][0]["transaction_id"] == "tx:1"


def test_governed_runtime_records_phase5_memory_policy_capability_and_isolation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    target = workspace / "core" / "runtime" / "kernel.py"
    source = sandbox / "core" / "runtime" / "kernel.py"
    target.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")
    source.write_text("VERSION = 2\n", encoding="utf-8")

    result = run_governed_mutation_runtime(
        MutationGatewayRequest(
            intent="Update runtime kernel file",
            initiator="test",
            reason="phase 5 convergence",
            relative_paths=("core/runtime/kernel.py",),
            scope=MutationScope(allowed_paths=("core/runtime",)),
            workspace_root=workspace,
            sandbox_source_root=sandbox,
            rollback_root=rollback,
            report_root=reports,
            approval_mode=MutationApprovalMode.AUTO,
            risk_level=MutationRiskLevel.HIGH,
            verification=MutationVerificationRequirement.TARGETED_TESTS,
            verification_checks=(
                MutationVerificationCheck(name="pytest", passed=True, details="ok"),
            ),
        )
    )
    payload = result.to_dict()
    evidence = payload["evidence"]
    replay = payload["runtime_replay"]
    wal = payload["runtime_evidence_bundle"]["metadata"]["runtime_wal"]

    assert evidence["runtime_intent_evaluation"]["allowed"] is True
    assert evidence["runtime_capability_graph"]["nodes"]["runtime:governed_mutation"]
    assert evidence["runtime_isolation_boundary"]["transaction_id"].startswith("runtime-tx:")
    assert evidence["runtime_mutation_sandbox"]["mutation_isolated"] is True
    assert evidence["runtime_verification_sandbox"]["uses_staged_runtime_state"] is True
    assert evidence["runtime_memory_snapshots"]
    assert replay["runtime_session_snapshot"]["memory_snapshots"]
    assert replay["distributed_replay"]["transaction_aware"] is True
    assert wal["memory_snapshots"]
    assert wal["capability_state"]
    assert wal["intent_state"]
    assert wal["distributed_state"]
