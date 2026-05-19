from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
START_PATH = REPO_ROOT / "core" / "runtime" / "runtime_execution_start.py"

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

FORBIDDEN_CALLS = (
    "enqueue",
    "execute",
    "mutate",
    "recover",
    "replay",
    "run",
    "Popen",
    "call",
    "check_call",
    "check_output",
    "system",
)


def _start_imports() -> list[str]:
    tree = ast.parse(START_PATH.read_text(encoding="utf-8"), filename=str(START_PATH))
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
    tree = ast.parse(START_PATH.read_text(encoding="utf-8"), filename=str(START_PATH))
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


def _request(*, authority_scope: str = "dry_run", risk_level: str = "low"):
    module = importlib.import_module("core.runtime.runtime_execution_start")
    return module.RuntimeExecutionStartRequest(
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        queue_admission_id="queue_admission:request-1",
        enqueue_id="controlled_enqueue:request-1",
        execution_token_id="execution_token:request-1",
        authority_scope=authority_scope,
        risk_level=risk_level,
        metadata={"source": "request"},
    )


def test_runtime_execution_start_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_execution_start")

    assert module.__all__ == [
        "RuntimeExecutionStartRequest",
        "RuntimeExecutionStartDecision",
        "RuntimeExecutionStartController",
    ]


def test_runtime_execution_start_request_shape():
    request = _request()

    assert request.request_id == "request-1"
    assert request.trace_id == "trace-1"
    assert request.lease_id == "lease-1"
    assert request.grant_id == "grant-1"
    assert request.queue_admission_id == "queue_admission:request-1"
    assert request.enqueue_id == "controlled_enqueue:request-1"
    assert request.execution_token_id == "execution_token:request-1"
    assert request.authority_scope == "dry_run"
    assert request.risk_level == "low"
    assert request.metadata == {"source": "request"}


def test_runtime_execution_start_decision_shape():
    module = importlib.import_module("core.runtime.runtime_execution_start")

    decision = module.RuntimeExecutionStartDecision(
        accepted=True,
        status="execution_started",
        reason="non_executing_scope_started",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        queue_admission_id="queue_admission:request-1",
        enqueue_id="controlled_enqueue:request-1",
        execution_token_id="execution_token:request-1",
        execution_start_id="execution_start:request-1",
        authority_scope="dry_run",
        risk_level="low",
        execution_pending=False,
        enqueued=True,
        scheduler_touched=True,
        executed=True,
        revoked=False,
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "execution_started"
    assert decision.reason == "non_executing_scope_started"
    assert decision.execution_start_id == "execution_start:request-1"
    assert decision.execution_pending is False
    assert decision.enqueued is True
    assert decision.scheduler_touched is True
    assert decision.executed is True
    assert decision.revoked is False
    assert decision.metadata == {"source": "test"}


@pytest.mark.parametrize("scope", ["dry_run", "read_only"])
def test_runtime_execution_start_accepts_pending_non_executing_low_risk(scope: str):
    module = importlib.import_module("core.runtime.runtime_execution_start")
    controller = module.RuntimeExecutionStartController()

    decision = controller.evaluate(
        _request(authority_scope=scope),
        execution_pending=True,
        revoked=False,
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "execution_started"
    assert decision.reason == "non_executing_scope_started"
    assert decision.authority_scope == scope
    assert decision.execution_pending is False
    assert decision.enqueued is True
    assert decision.scheduler_touched is True
    assert decision.executed is True
    assert decision.revoked is False
    assert decision.metadata == {"source": "test"}


def test_runtime_execution_start_executed_true_is_lifecycle_marker_only():
    module = importlib.import_module("core.runtime.runtime_execution_start")
    controller = module.RuntimeExecutionStartController()
    before_modules = set(sys.modules)

    decision = controller.evaluate(_request(), execution_pending=True)

    assert decision.executed is True
    assert "core.runtime.executor" not in set(sys.modules) - before_modules
    assert "core.tasks.scheduler" not in set(sys.modules) - before_modules


def test_runtime_execution_start_rejects_not_pending_without_execution_marker():
    module = importlib.import_module("core.runtime.runtime_execution_start")
    controller = module.RuntimeExecutionStartController()

    decision = controller.evaluate(_request(), execution_pending=False)

    assert decision.accepted is False
    assert decision.status == "execution_start_rejected"
    assert decision.reason == "execution_not_pending"
    assert decision.execution_pending is False
    assert decision.executed is False


def test_runtime_execution_start_rejects_revoked_without_execution_marker():
    module = importlib.import_module("core.runtime.runtime_execution_start")
    controller = module.RuntimeExecutionStartController()

    decision = controller.evaluate(_request(), execution_pending=True, revoked=True)

    assert decision.accepted is False
    assert decision.status == "execution_start_rejected"
    assert decision.reason == "execution_token_revoked"
    assert decision.revoked is True
    assert decision.executed is False


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
def test_runtime_execution_start_rejects_disallowed_scopes(scope: str):
    module = importlib.import_module("core.runtime.runtime_execution_start")
    controller = module.RuntimeExecutionStartController()

    decision = controller.evaluate(
        _request(authority_scope=scope),
        execution_pending=True,
    )

    assert decision.accepted is False
    assert decision.status == "execution_start_rejected"
    assert decision.reason == "scope_or_risk_not_allowed_for_execution_start_v0"
    assert decision.authority_scope == scope
    assert decision.executed is False


def test_runtime_execution_start_rejects_non_low_risk_without_execution_marker():
    module = importlib.import_module("core.runtime.runtime_execution_start")
    controller = module.RuntimeExecutionStartController()

    decision = controller.evaluate(
        _request(authority_scope="dry_run", risk_level="medium"),
        execution_pending=True,
    )

    assert decision.accepted is False
    assert decision.reason == "scope_or_risk_not_allowed_for_execution_start_v0"
    assert decision.executed is False


def test_runtime_execution_start_does_not_import_executor_or_scheduler():
    imports = _start_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_execution_start must not import scheduler/executor internals:\n"
        + "\n".join(violations)
    )


def test_runtime_execution_start_has_no_execution_methods():
    module = importlib.import_module("core.runtime.runtime_execution_start")
    public_names = {
        name
        for name in dir(module.RuntimeExecutionStartController)
        if not name.startswith("_")
    }

    assert public_names == {"evaluate"}
    assert not (public_names & set(FORBIDDEN_METHODS))


def test_runtime_execution_start_does_not_call_runtime_or_command_execution():
    calls = _call_names()

    assert not (set(calls) & set(FORBIDDEN_CALLS))
