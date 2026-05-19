from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PENDING_PATH = REPO_ROOT / "core" / "runtime" / "runtime_execution_pending.py"

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
    "execute",
    "mutate",
    "recover",
    "replay",
)


def _pending_imports() -> list[str]:
    tree = ast.parse(PENDING_PATH.read_text(encoding="utf-8"), filename=str(PENDING_PATH))
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
    tree = ast.parse(PENDING_PATH.read_text(encoding="utf-8"), filename=str(PENDING_PATH))
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


def _controlled_enqueue(*, accepted: bool, authority_scope: str):
    enqueue_module = importlib.import_module("core.runtime.runtime_controlled_enqueue")
    return enqueue_module.RuntimeControlledEnqueueDecision(
        accepted=accepted,
        status=(
            "controlled_enqueue_accepted"
            if accepted
            else "controlled_enqueue_rejected"
        ),
        reason=(
            "queue_admission_accepted_for_non_executing_scope"
            if accepted
            else "queue_admission_not_accepted"
        ),
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        queue_admission_id="queue_admission:request-1",
        enqueue_id="controlled_enqueue:request-1",
        authority_scope=authority_scope,
        risk_level="low" if accepted else "unknown",
        enqueued=accepted,
        executed=False,
        scheduler_touched=accepted,
        metadata={},
    )


def test_runtime_execution_pending_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_execution_pending")

    assert module.__all__ == [
        "RuntimeExecutionPendingDecision",
        "RuntimeExecutionPendingController",
    ]


def test_runtime_execution_pending_decision_shape():
    module = importlib.import_module("core.runtime.runtime_execution_pending")

    decision = module.RuntimeExecutionPendingDecision(
        accepted=True,
        status="execution_pending",
        reason="controlled_enqueue_accepted",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        enqueue_id="controlled_enqueue:request-1",
        execution_token_id="execution_token:request-1",
        authority_scope="dry_run",
        risk_level="low",
        execution_pending=True,
        enqueued=True,
        scheduler_touched=True,
        executed=False,
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "execution_pending"
    assert decision.reason == "controlled_enqueue_accepted"
    assert decision.execution_token_id == "execution_token:request-1"
    assert decision.execution_pending is True
    assert decision.enqueued is True
    assert decision.scheduler_touched is True
    assert decision.executed is False
    assert decision.metadata == {"source": "test"}


@pytest.mark.parametrize("scope", ["dry_run", "read_only"])
def test_runtime_execution_pending_accepts_controlled_enqueue(scope: str):
    module = importlib.import_module("core.runtime.runtime_execution_pending")
    controller = module.RuntimeExecutionPendingController()

    decision = controller.evaluate(
        _controlled_enqueue(accepted=True, authority_scope=scope),
        metadata={"source": "test"},
    )
    token = controller.issue_token(
        _controlled_enqueue(accepted=True, authority_scope=scope),
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "execution_pending"
    assert decision.reason == "controlled_enqueue_accepted"
    assert decision.execution_pending is True
    assert decision.enqueued is True
    assert decision.scheduler_touched is True
    assert decision.executed is False
    assert token.execution_pending is True
    assert token.executed is False
    assert token.revoked is False


def test_runtime_execution_pending_rejects_controlled_enqueue_rejected():
    module = importlib.import_module("core.runtime.runtime_execution_pending")
    controller = module.RuntimeExecutionPendingController()

    decision = controller.evaluate(
        _controlled_enqueue(accepted=False, authority_scope="dry_run")
    )
    token = controller.issue_token(
        _controlled_enqueue(accepted=False, authority_scope="dry_run")
    )

    assert decision.accepted is False
    assert decision.status == "execution_pending_rejected"
    assert decision.reason == "controlled_enqueue_not_accepted"
    assert decision.execution_pending is False
    assert decision.executed is False
    assert token.execution_pending is False
    assert token.executed is False
    assert token.revoked is False


@pytest.mark.parametrize(
    "scope",
    [
        "write",
        "mutation",
        "recovery",
        "replay",
        "scheduler_enqueue",
    ],
)
def test_runtime_execution_pending_rejects_disallowed_scopes(scope: str):
    module = importlib.import_module("core.runtime.runtime_execution_pending")
    controller = module.RuntimeExecutionPendingController()

    decision = controller.evaluate(
        _controlled_enqueue(accepted=True, authority_scope=scope)
    )

    assert decision.accepted is False
    assert decision.status == "execution_pending_rejected"
    assert decision.reason == "scope_not_allowed_for_execution_pending_v0"
    assert decision.execution_pending is False
    assert decision.executed is False


def test_runtime_execution_pending_does_not_import_executor_or_scheduler():
    imports = _pending_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_execution_pending must not import scheduler/executor internals:\n"
        + "\n".join(violations)
    )


def test_runtime_execution_pending_has_no_execution_methods():
    module = importlib.import_module("core.runtime.runtime_execution_pending")
    public_names = {
        name
        for name in dir(module.RuntimeExecutionPendingController)
        if not name.startswith("_")
    }

    assert public_names == {"evaluate", "issue_token"}
    assert not (public_names & set(FORBIDDEN_METHODS))


def test_runtime_execution_pending_does_not_call_execute():
    calls = _call_names()

    assert "execute" not in calls
    assert "mutate" not in calls
    assert "recover" not in calls
    assert "replay" not in calls


@pytest.mark.parametrize("scope", ["dry_run", "read_only"])
def test_runtime_execution_pending_can_feed_execution_start_marker(scope: str):
    pending_module = importlib.import_module("core.runtime.runtime_execution_pending")
    start_module = importlib.import_module("core.runtime.runtime_execution_start")
    pending_controller = pending_module.RuntimeExecutionPendingController()
    start_controller = start_module.RuntimeExecutionStartController()

    pending = pending_controller.evaluate(
        _controlled_enqueue(accepted=True, authority_scope=scope)
    )
    token = pending_controller.issue_token(
        _controlled_enqueue(accepted=True, authority_scope=scope)
    )
    request = start_module.RuntimeExecutionStartRequest(
        request_id=pending.request_id,
        trace_id=pending.trace_id,
        lease_id=pending.lease_id,
        grant_id=pending.grant_id,
        queue_admission_id=token.queue_admission_id,
        enqueue_id=pending.enqueue_id,
        execution_token_id=pending.execution_token_id,
        authority_scope=pending.authority_scope,
        risk_level=pending.risk_level,
        metadata={},
    )

    started = start_controller.evaluate(
        request,
        execution_pending=pending.execution_pending,
        revoked=token.revoked,
    )

    assert pending.execution_pending is True
    assert started.accepted is True
    assert started.execution_pending is False
    assert started.executed is True
