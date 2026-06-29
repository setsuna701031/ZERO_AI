from __future__ import annotations

from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_ownership_isolation_fabric import (

    AUTHORITY_ALLOW,
    AUTHORITY_DENY,
    CAPABILITY_EXECUTE,
    CAPABILITY_MUTATE,
    CAPABILITY_READ,
    CAPABILITY_WRITE,
    RuntimeOwnershipIsolationFabric,
)
from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_transaction_fabric import RuntimeTransactionFabric
import pytest

pytestmark = [pytest.mark.contract]



def test_runtime_ownership_isolation_mainline(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "ownership-recovery-exec",
            "replay_id": "ownership-replay",
        },
    )

    execution_fabric = RuntimeExecutionFabric.with_workspace(
        tmp_path / "execution_fabric",
        recovery_orchestrator=orchestrator,
    )

    transaction_fabric = RuntimeTransactionFabric.with_workspace(
        tmp_path / "transaction_fabric",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
    )

    ownership_fabric = RuntimeOwnershipIsolationFabric.with_workspace(
        tmp_path / "ownership_fabric",
    )

    runtime = ownership_fabric.register_runtime(
        runtime_id="runtime-main",
        namespace="zero.runtime.main",
        owner_id="runtime-owner",
        session_ids=["session-main"],
        capabilities=[
            CAPABILITY_READ,
            CAPABILITY_WRITE,
            CAPABILITY_EXECUTE,
        ],
        allowed_paths=["workspace/safe/"],
        denied_paths=["workspace/system/"],
    )

    assert runtime.namespace == "zero.runtime.main"

    allow = ownership_fabric.authorize(
        runtime_id="runtime-main",
        capability=CAPABILITY_WRITE,
        target="workspace/safe/output.txt",
        owner_id="runtime-owner",
    )

    assert allow.decision == AUTHORITY_ALLOW

    denied = ownership_fabric.authorize(
        runtime_id="runtime-main",
        capability=CAPABILITY_MUTATE,
        target="workspace/system/core.py",
        owner_id="runtime-owner",
    )

    assert denied.decision == AUTHORITY_DENY

    execution = execution_fabric.start_execution(
        source_session_id="session-main",
        task_id="isolated-task",
        steps=[
            {"type": "transaction", "name": "isolated-write"},
        ],
    )

    tx = transaction_fabric.begin_transaction(
        source_session_id="session-main",
        execution_id=execution.execution_id,
        task_id="isolated-task",
        before_snapshot={"files": {"safe.txt": "before"}},
        steps=[
            {"type": "write", "path": "workspace/safe/safe.txt"},
            {"type": "verify", "path": "workspace/safe/safe.txt"},
        ],
    )

    executed = transaction_fabric.execute_transaction(tx.transaction_id)

    assert executed.status == "prepared"

    committed = transaction_fabric.commit_transaction(tx.transaction_id)

    assert committed.status == "committed"

    quarantined = ownership_fabric.quarantine_runtime(
        "runtime-main",
        reason="suspicious cross-runtime access",
        restricted_capabilities=[CAPABILITY_EXECUTE],
        blocked_sessions=["session-main"],
    )

    assert quarantined.status == "quarantined"

    blocked = ownership_fabric.authorize(
        runtime_id="runtime-main",
        capability=CAPABILITY_EXECUTE,
        target="workspace/safe/run.py",
        owner_id="runtime-owner",
    )

    assert blocked.decision == AUTHORITY_DENY
