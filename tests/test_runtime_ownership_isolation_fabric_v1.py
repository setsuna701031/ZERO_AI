from __future__ import annotations

from core.runtime.runtime_ownership_isolation_fabric import (
    AUTHORITY_ALLOW,
    AUTHORITY_DENY,
    AUTHORITY_ESCALATE,
    CAPABILITY_EXECUTE,
    CAPABILITY_READ,
    CAPABILITY_WRITE,
    RUNTIME_STATUS_FROZEN,
    RUNTIME_STATUS_ISOLATED,
    RUNTIME_STATUS_QUARANTINED,
    RuntimeOwnershipIsolationFabric,
)


def test_runtime_registration_and_authority_allow(tmp_path):
    fabric = RuntimeOwnershipIsolationFabric.with_workspace(tmp_path)

    runtime = fabric.register_runtime(
        runtime_id="runtime-1",
        namespace="zero.main",
        owner_id="owner-a",
        capabilities=[CAPABILITY_READ, CAPABILITY_WRITE],
        allowed_paths=["workspace/"],
    )

    assert runtime.namespace == "zero.main"

    decision = fabric.authorize(
        runtime_id="runtime-1",
        capability=CAPABILITY_WRITE,
        target="workspace/test.txt",
        owner_id="owner-a",
    )

    assert decision.decision == AUTHORITY_ALLOW


def test_runtime_authority_denied_for_missing_capability(tmp_path):
    fabric = RuntimeOwnershipIsolationFabric.with_workspace(tmp_path)

    fabric.register_runtime(
        runtime_id="runtime-2",
        namespace="zero.main",
        owner_id="owner-a",
        capabilities=[CAPABILITY_READ],
    )

    decision = fabric.authorize(
        runtime_id="runtime-2",
        capability=CAPABILITY_WRITE,
        target="workspace/test.txt",
        owner_id="owner-a",
    )

    assert decision.decision == AUTHORITY_DENY


def test_runtime_authority_escalates_outside_scope(tmp_path):
    fabric = RuntimeOwnershipIsolationFabric.with_workspace(tmp_path)

    fabric.register_runtime(
        runtime_id="runtime-3",
        namespace="zero.main",
        owner_id="owner-a",
        capabilities=[CAPABILITY_WRITE],
        allowed_paths=["workspace/safe/"],
    )

    decision = fabric.authorize(
        runtime_id="runtime-3",
        capability=CAPABILITY_WRITE,
        target="workspace/unsafe/test.txt",
        owner_id="owner-a",
    )

    assert decision.decision == AUTHORITY_ESCALATE


def test_runtime_quarantine_blocks_authority(tmp_path):
    fabric = RuntimeOwnershipIsolationFabric.with_workspace(tmp_path)

    fabric.register_runtime(
        runtime_id="runtime-4",
        namespace="zero.main",
        owner_id="owner-a",
        capabilities=[CAPABILITY_EXECUTE],
    )

    quarantined = fabric.quarantine_runtime(
        "runtime-4",
        reason="unsafe execution detected",
        restricted_capabilities=[CAPABILITY_EXECUTE],
    )

    assert quarantined.status == RUNTIME_STATUS_QUARANTINED

    decision = fabric.authorize(
        runtime_id="runtime-4",
        capability=CAPABILITY_EXECUTE,
        target="workspace/run.py",
        owner_id="owner-a",
    )

    assert decision.decision == AUTHORITY_DENY


def test_runtime_isolation_and_freeze(tmp_path):
    fabric = RuntimeOwnershipIsolationFabric.with_workspace(tmp_path)

    fabric.register_runtime(
        runtime_id="runtime-5",
        namespace="zero.main",
        owner_id="owner-a",
        capabilities=[CAPABILITY_EXECUTE],
    )

    isolated = fabric.isolate_runtime(
        "runtime-5",
        reason="cross-runtime contamination",
    )

    assert isolated.status == RUNTIME_STATUS_ISOLATED

    frozen = fabric.freeze_runtime(
        "runtime-5",
        reason="critical governance violation",
    )

    assert frozen.status == RUNTIME_STATUS_FROZEN


def test_runtime_persistence_reload(tmp_path):
    fabric = RuntimeOwnershipIsolationFabric.with_workspace(tmp_path)

    fabric.register_runtime(
        runtime_id="runtime-6",
        namespace="zero.main",
        owner_id="owner-a",
        capabilities=[CAPABILITY_READ],
    )

    reloaded = RuntimeOwnershipIsolationFabric.with_workspace(tmp_path)

    loaded = reloaded.get_runtime("runtime-6")

    assert loaded.runtime_id == "runtime-6"
