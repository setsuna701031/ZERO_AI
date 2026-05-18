from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLED_ENQUEUE_PATH = REPO_ROOT / "core" / "runtime" / "runtime_controlled_enqueue.py"

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


def _controlled_enqueue_imports() -> list[str]:
    tree = ast.parse(
        CONTROLLED_ENQUEUE_PATH.read_text(encoding="utf-8"),
        filename=str(CONTROLLED_ENQUEUE_PATH),
    )
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
    tree = ast.parse(
        CONTROLLED_ENQUEUE_PATH.read_text(encoding="utf-8"),
        filename=str(CONTROLLED_ENQUEUE_PATH),
    )
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


def _queue_admission(*, accepted: bool, authority_scope: str):
    queue_module = importlib.import_module("core.runtime.runtime_queue_admission")
    return queue_module.RuntimeQueueAdmissionDecision(
        accepted=accepted,
        status=(
            "queue_admission_accepted"
            if accepted
            else "queue_admission_rejected"
        ),
        reason=(
            "adapter_ready_for_non_executing_scope"
            if accepted
            else "adapter_not_ready"
        ),
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        authority_scope=authority_scope,
        risk_level="low" if accepted else "unknown",
        adapter_status="adapter_ready" if accepted else "adapter_rejected",
        queue_admission_id="queue_admission:request-1",
        enqueued=False,
        executed=False,
        scheduler_touched=False,
        metadata={},
    )


def test_runtime_controlled_enqueue_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_controlled_enqueue")

    assert module.__all__ == [
        "RuntimeControlledEnqueueRequest",
        "RuntimeControlledEnqueueDecision",
        "RuntimeControlledEnqueueController",
    ]


def test_runtime_controlled_enqueue_request_shape():
    module = importlib.import_module("core.runtime.runtime_controlled_enqueue")

    request = module.RuntimeControlledEnqueueRequest(
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        queue_admission_id="queue_admission:request-1",
        authority_scope="dry_run",
        risk_level="low",
        metadata={"source": "test"},
    )

    assert request.request_id == "request-1"
    assert request.trace_id == "trace-1"
    assert request.lease_id == "lease-1"
    assert request.grant_id == "grant-1"
    assert request.queue_admission_id == "queue_admission:request-1"
    assert request.authority_scope == "dry_run"
    assert request.risk_level == "low"
    assert request.metadata == {"source": "test"}


def test_runtime_controlled_enqueue_decision_shape():
    module = importlib.import_module("core.runtime.runtime_controlled_enqueue")

    decision = module.RuntimeControlledEnqueueDecision(
        accepted=True,
        status="controlled_enqueue_accepted",
        reason="queue_admission_accepted_for_non_executing_scope",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        queue_admission_id="queue_admission:request-1",
        enqueue_id="controlled_enqueue:request-1",
        authority_scope="dry_run",
        risk_level="low",
        enqueued=True,
        executed=False,
        scheduler_touched=True,
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "controlled_enqueue_accepted"
    assert decision.reason == "queue_admission_accepted_for_non_executing_scope"
    assert decision.request_id == "request-1"
    assert decision.trace_id == "trace-1"
    assert decision.lease_id == "lease-1"
    assert decision.grant_id == "grant-1"
    assert decision.queue_admission_id == "queue_admission:request-1"
    assert decision.enqueue_id == "controlled_enqueue:request-1"
    assert decision.authority_scope == "dry_run"
    assert decision.risk_level == "low"
    assert decision.enqueued is True
    assert decision.scheduler_touched is True
    assert decision.executed is False
    assert decision.metadata == {"source": "test"}


@pytest.mark.parametrize("scope", ["dry_run", "read_only"])
def test_runtime_controlled_enqueue_accepts_queue_admitted_non_executing_scopes(
    scope: str,
):
    module = importlib.import_module("core.runtime.runtime_controlled_enqueue")
    controller = module.RuntimeControlledEnqueueController()

    decision = controller.evaluate(
        _queue_admission(accepted=True, authority_scope=scope),
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "controlled_enqueue_accepted"
    assert decision.reason == "queue_admission_accepted_for_non_executing_scope"
    assert decision.authority_scope == scope
    assert decision.enqueue_id == "controlled_enqueue:request-1"
    assert decision.enqueued is True
    assert decision.scheduler_touched is True
    assert decision.executed is False
    assert decision.metadata == {"source": "test"}


def test_runtime_controlled_enqueue_rejects_queue_admission_rejected():
    module = importlib.import_module("core.runtime.runtime_controlled_enqueue")
    controller = module.RuntimeControlledEnqueueController()

    decision = controller.evaluate(
        _queue_admission(accepted=False, authority_scope="dry_run")
    )

    assert decision.accepted is False
    assert decision.status == "controlled_enqueue_rejected"
    assert decision.reason == "queue_admission_not_accepted"
    assert decision.enqueued is False
    assert decision.scheduler_touched is False
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
def test_runtime_controlled_enqueue_rejects_disallowed_scopes(scope: str):
    module = importlib.import_module("core.runtime.runtime_controlled_enqueue")
    controller = module.RuntimeControlledEnqueueController()

    decision = controller.evaluate(
        _queue_admission(accepted=True, authority_scope=scope)
    )

    assert decision.accepted is False
    assert decision.status == "controlled_enqueue_rejected"
    assert decision.reason == "scope_not_allowed_for_controlled_enqueue_v0"
    assert decision.authority_scope == scope
    assert decision.enqueued is False
    assert decision.scheduler_touched is False
    assert decision.executed is False


def test_runtime_controlled_enqueue_does_not_import_scheduler_internals():
    imports = _controlled_enqueue_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_controlled_enqueue must not import scheduler/runtime internals:\n"
        + "\n".join(violations)
    )


def test_runtime_controlled_enqueue_has_no_execution_methods():
    module = importlib.import_module("core.runtime.runtime_controlled_enqueue")
    public_names = {
        name
        for name in dir(module.RuntimeControlledEnqueueController)
        if not name.startswith("_")
    }

    assert public_names == {"evaluate"}
    assert not (public_names & set(FORBIDDEN_METHODS))


def test_runtime_controlled_enqueue_does_not_call_scheduler_or_execute():
    calls = _call_names()

    assert "enqueue" not in calls
    assert "execute" not in calls
    assert "mutate" not in calls
    assert "recover" not in calls
    assert "replay" not in calls


def test_runtime_controlled_enqueue_can_feed_execution_pending_without_execution():
    enqueue_module = importlib.import_module("core.runtime.runtime_controlled_enqueue")
    pending_module = importlib.import_module("core.runtime.runtime_execution_pending")
    enqueue_controller = enqueue_module.RuntimeControlledEnqueueController()
    pending_controller = pending_module.RuntimeExecutionPendingController()

    enqueue_decision = enqueue_controller.evaluate(
        _queue_admission(accepted=True, authority_scope="dry_run")
    )
    pending_decision = pending_controller.evaluate(enqueue_decision)

    assert enqueue_decision.enqueued is True
    assert enqueue_decision.executed is False
    assert pending_decision.execution_pending is True
    assert pending_decision.executed is False
