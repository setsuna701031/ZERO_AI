from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / "core" / "runtime" / "runtime_scheduler_adapter.py"

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


def _adapter_imports() -> list[str]:
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"), filename=str(ADAPTER_PATH))
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
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"), filename=str(ADAPTER_PATH))
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


def _bridge_decision(*, accepted: bool, status: str, authority_scope: str):
    bridge_module = importlib.import_module("core.runtime.runtime_execution_bridge")
    return bridge_module.RuntimeExecutionBridgeDecision(
        accepted=accepted,
        status=status,
        reason=(
            "grant_accepted_for_non_executing_scope"
            if accepted
            else "grant_not_issued"
        ),
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        authority_scope=authority_scope,
        risk_level="low" if accepted else "unknown",
        metadata={},
    )


def test_runtime_scheduler_adapter_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_scheduler_adapter")

    assert module.__all__ == [
        "RuntimeSchedulerAdapterDecision",
        "RuntimeSchedulerAdapter",
    ]


def test_runtime_scheduler_adapter_decision_shape():
    module = importlib.import_module("core.runtime.runtime_scheduler_adapter")

    decision = module.RuntimeSchedulerAdapterDecision(
        accepted=True,
        status="adapter_ready",
        reason="bridge_accepted_for_non_executing_scope",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        authority_scope="dry_run",
        risk_level="low",
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "adapter_ready"
    assert decision.reason == "bridge_accepted_for_non_executing_scope"
    assert decision.request_id == "request-1"
    assert decision.trace_id == "trace-1"
    assert decision.lease_id == "lease-1"
    assert decision.grant_id == "grant-1"
    assert decision.authority_scope == "dry_run"
    assert decision.risk_level == "low"
    assert decision.metadata == {"source": "test"}


@pytest.mark.parametrize("scope", ["dry_run", "read_only"])
def test_runtime_scheduler_adapter_ready_for_accepted_non_executing_scopes(scope: str):
    module = importlib.import_module("core.runtime.runtime_scheduler_adapter")
    adapter = module.RuntimeSchedulerAdapter()

    decision = adapter.evaluate_bridge_decision(
        _bridge_decision(
            accepted=True,
            status="bridge_accepted",
            authority_scope=scope,
        ),
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "adapter_ready"
    assert decision.reason == "bridge_accepted_for_non_executing_scope"
    assert decision.authority_scope == scope
    assert decision.risk_level == "low"
    assert decision.metadata == {"source": "test"}


@pytest.mark.parametrize(
    "scope",
    [
        "write",
        "mutation",
        "recovery",
        "replay",
        "scheduler_enqueue",
        "unknown",
        "none",
    ],
)
def test_runtime_scheduler_adapter_rejects_disallowed_scopes(scope: str):
    module = importlib.import_module("core.runtime.runtime_scheduler_adapter")
    adapter = module.RuntimeSchedulerAdapter()

    decision = adapter.evaluate_bridge_decision(
        _bridge_decision(
            accepted=True,
            status="bridge_accepted",
            authority_scope=scope,
        )
    )

    assert decision.accepted is False
    assert decision.status == "adapter_rejected"
    assert decision.reason == "bridge_not_accepted_for_adapter_v0"
    assert decision.authority_scope == scope


def test_runtime_scheduler_adapter_rejects_unaccepted_bridge_decision():
    module = importlib.import_module("core.runtime.runtime_scheduler_adapter")
    adapter = module.RuntimeSchedulerAdapter()

    decision = adapter.evaluate_bridge_decision(
        _bridge_decision(
            accepted=False,
            status="bridge_rejected",
            authority_scope="dry_run",
        )
    )

    assert decision.accepted is False
    assert decision.status == "adapter_rejected"
    assert decision.reason == "bridge_not_accepted_for_adapter_v0"


def test_runtime_scheduler_adapter_does_not_import_scheduler_internals():
    imports = _adapter_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_scheduler_adapter must not import scheduler/runtime internals:\n"
        + "\n".join(violations)
    )


def test_runtime_scheduler_adapter_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_scheduler_adapter")
    public_names = {
        name
        for name in dir(module.RuntimeSchedulerAdapter)
        if not name.startswith("_")
    }

    assert public_names == {"evaluate_bridge_decision"}
    assert not (public_names & set(FORBIDDEN_METHODS))


def test_runtime_scheduler_adapter_ready_does_not_enqueue_or_execute():
    calls = _call_names()

    assert "enqueue" not in calls
    assert "execute" not in calls
    assert "mutate" not in calls
    assert "recover" not in calls
    assert "replay" not in calls
