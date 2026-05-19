from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATH = REPO_ROOT / "core" / "runtime" / "runtime_execution_token.py"

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


def _token_imports() -> list[str]:
    tree = ast.parse(TOKEN_PATH.read_text(encoding="utf-8"), filename=str(TOKEN_PATH))
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


def test_runtime_execution_token_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_execution_token")

    assert module.__all__ == ["RuntimeExecutionToken"]


def test_runtime_execution_token_shape_pending_not_executed():
    module = importlib.import_module("core.runtime.runtime_execution_token")

    token = module.RuntimeExecutionToken(
        execution_token_id="execution_token:request-1",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        queue_admission_id="queue_admission:request-1",
        enqueue_id="controlled_enqueue:request-1",
        authority_scope="dry_run",
        risk_level="low",
        execution_pending=True,
        executed=False,
        revoked=False,
        metadata={"source": "test"},
    )

    assert token.execution_token_id == "execution_token:request-1"
    assert token.request_id == "request-1"
    assert token.trace_id == "trace-1"
    assert token.lease_id == "lease-1"
    assert token.grant_id == "grant-1"
    assert token.queue_admission_id == "queue_admission:request-1"
    assert token.enqueue_id == "controlled_enqueue:request-1"
    assert token.authority_scope == "dry_run"
    assert token.risk_level == "low"
    assert token.execution_pending is True
    assert token.executed is False
    assert token.revoked is False
    assert token.metadata == {"source": "test"}


def test_runtime_execution_token_does_not_import_executor_or_scheduler():
    imports = _token_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_execution_token must not import scheduler/executor internals:\n"
        + "\n".join(violations)
    )


def test_runtime_execution_token_has_no_execution_methods():
    module = importlib.import_module("core.runtime.runtime_execution_token")
    public_names = {
        name
        for name in dir(module.RuntimeExecutionToken)
        if not name.startswith("_")
    }

    assert not (public_names & set(FORBIDDEN_METHODS))


def test_runtime_execution_token_can_feed_execution_start_without_execution_behavior():
    token_module = importlib.import_module("core.runtime.runtime_execution_token")
    start_module = importlib.import_module("core.runtime.runtime_execution_start")
    controller = start_module.RuntimeExecutionStartController()
    token = token_module.RuntimeExecutionToken(
        execution_token_id="execution_token:request-1",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        queue_admission_id="queue_admission:request-1",
        enqueue_id="controlled_enqueue:request-1",
        authority_scope="read_only",
        risk_level="low",
        execution_pending=True,
        executed=False,
        revoked=False,
        metadata={},
    )
    request = start_module.RuntimeExecutionStartRequest(
        request_id=token.request_id,
        trace_id=token.trace_id,
        lease_id=token.lease_id,
        grant_id=token.grant_id,
        queue_admission_id=token.queue_admission_id,
        enqueue_id=token.enqueue_id,
        execution_token_id=token.execution_token_id,
        authority_scope=token.authority_scope,
        risk_level=token.risk_level,
        metadata={},
    )

    decision = controller.evaluate(
        request,
        execution_pending=token.execution_pending,
        revoked=token.revoked,
    )

    assert token.executed is False
    assert decision.executed is True
    assert decision.reason == "non_executing_scope_started"
