from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = REPO_ROOT / "core" / "runtime" / "runtime_execution_bridge.py"

FORBIDDEN_IMPORTS = (
    "core.tasks.scheduler",
    "core.tasks.scheduler_core",
    "core.runtime.executor",
    "core.runtime.mutation_runtime_pipeline",
    "core.runtime.mutation_patch_apply",
    "core.runtime.runtime_recovery_coordinator",
    "core.runtime.runtime_recovery_policy",
    "core.runtime.runtime_replay_engine",
)

FORBIDDEN_METHODS = (
    "enqueue",
    "execute",
    "mutate",
    "recover",
    "replay",
)


def _bridge_imports() -> list[str]:
    tree = ast.parse(BRIDGE_PATH.read_text(encoding="utf-8"), filename=str(BRIDGE_PATH))
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
            continue

        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
            imports.extend(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if alias.name != "*"
            )

    return imports


def _call_names() -> list[str]:
    tree = ast.parse(BRIDGE_PATH.read_text(encoding="utf-8"), filename=str(BRIDGE_PATH))
    calls: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            calls.append(node.func.id)
            continue

        if isinstance(node.func, ast.Attribute):
            calls.append(node.func.attr)

    return calls


def _grant(*, granted: bool, authority_scope: str, risk_level: str = "low"):
    grant_module = importlib.import_module("core.runtime.runtime_execution_grant")
    return grant_module.RuntimeExecutionGrant(
        grant_id="grant-1",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        granted=granted,
        status="grant_issued" if granted else "grant_not_issued",
        reason=(
            "eligible_for_non_executing_scope"
            if granted
            else "execution_not_granted"
        ),
        authority_scope=authority_scope,
        risk_level=risk_level,
        granted_by="runtime_grant_issuer_v0",
        expires_at=None,
        metadata={},
    )


def test_runtime_execution_bridge_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_execution_bridge")

    assert module.__all__ == [
        "RuntimeExecutionBridgeDecision",
        "RuntimeExecutionBridge",
    ]


def test_runtime_execution_bridge_decision_shape():
    module = importlib.import_module("core.runtime.runtime_execution_bridge")

    decision = module.RuntimeExecutionBridgeDecision(
        accepted=True,
        status="bridge_accepted",
        reason="grant_accepted_for_non_executing_scope",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        authority_scope="dry_run",
        risk_level="low",
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "bridge_accepted"
    assert decision.reason == "grant_accepted_for_non_executing_scope"
    assert decision.request_id == "request-1"
    assert decision.trace_id == "trace-1"
    assert decision.lease_id == "lease-1"
    assert decision.grant_id == "grant-1"
    assert decision.authority_scope == "dry_run"
    assert decision.risk_level == "low"
    assert decision.metadata == {"source": "test"}


@pytest.mark.parametrize("scope", ["dry_run", "read_only"])
def test_runtime_execution_bridge_accepts_granted_low_risk_scopes(scope: str):
    module = importlib.import_module("core.runtime.runtime_execution_bridge")
    bridge = module.RuntimeExecutionBridge()

    decision = bridge.evaluate_handoff(
        _grant(granted=True, authority_scope=scope),
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "bridge_accepted"
    assert decision.reason == "grant_accepted_for_non_executing_scope"
    assert decision.request_id == "request-1"
    assert decision.trace_id == "trace-1"
    assert decision.lease_id == "lease-1"
    assert decision.grant_id == "grant-1"
    assert decision.authority_scope == scope
    assert decision.risk_level == "low"
    assert decision.metadata == {"source": "test"}


def test_runtime_execution_bridge_rejects_unissued_grant():
    module = importlib.import_module("core.runtime.runtime_execution_bridge")
    bridge = module.RuntimeExecutionBridge()

    decision = bridge.evaluate_handoff(_grant(granted=False, authority_scope="none"))

    assert decision.accepted is False
    assert decision.status == "bridge_rejected"
    assert decision.reason == "grant_not_issued"
    assert decision.authority_scope == "none"


@pytest.mark.parametrize(
    "scope",
    [
        "scheduler_enqueue",
        "write",
        "mutation",
        "recovery",
        "replay",
        "unknown",
        "none",
    ],
)
def test_runtime_execution_bridge_rejects_disallowed_scopes(scope: str):
    module = importlib.import_module("core.runtime.runtime_execution_bridge")
    bridge = module.RuntimeExecutionBridge()

    decision = bridge.evaluate_handoff(
        _grant(granted=True, authority_scope=scope, risk_level="unknown")
    )

    assert decision.accepted is False
    assert decision.status == "bridge_rejected"
    assert decision.reason == "scope_not_allowed_for_bridge_v0"
    assert decision.authority_scope == scope


def test_runtime_execution_bridge_does_not_import_scheduler_internals():
    imports = _bridge_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_execution_bridge must not import scheduler/runtime internals:\n"
        + "\n".join(violations)
    )


def test_runtime_execution_bridge_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_execution_bridge")
    public_names = {
        name
        for name in dir(module.RuntimeExecutionBridge)
        if not name.startswith("_")
    }

    assert public_names == {"evaluate_handoff"}
    assert not (public_names & set(FORBIDDEN_METHODS))


def test_runtime_execution_bridge_accepted_does_not_enqueue_or_execute():
    calls = _call_names()

    assert "enqueue" not in calls
    assert "execute" not in calls
    assert "mutate" not in calls
    assert "recover" not in calls
    assert "replay" not in calls
