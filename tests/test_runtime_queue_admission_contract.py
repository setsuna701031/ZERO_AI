from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
QUEUE_ADMISSION_PATH = REPO_ROOT / "core" / "runtime" / "runtime_queue_admission.py"

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


def _queue_admission_imports() -> list[str]:
    tree = ast.parse(
        QUEUE_ADMISSION_PATH.read_text(encoding="utf-8"),
        filename=str(QUEUE_ADMISSION_PATH),
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
        QUEUE_ADMISSION_PATH.read_text(encoding="utf-8"),
        filename=str(QUEUE_ADMISSION_PATH),
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


def _adapter_decision(*, accepted: bool, status: str, authority_scope: str):
    adapter_module = importlib.import_module("core.runtime.runtime_scheduler_adapter")
    return adapter_module.RuntimeSchedulerAdapterDecision(
        accepted=accepted,
        status=status,
        reason=(
            "bridge_accepted_for_non_executing_scope"
            if accepted
            else "bridge_not_accepted_for_adapter_v0"
        ),
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        authority_scope=authority_scope,
        risk_level="low" if accepted else "unknown",
        metadata={},
    )


def test_runtime_queue_admission_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_queue_admission")

    assert module.__all__ == [
        "RuntimeQueueAdmissionDecision",
        "RuntimeQueueAdmissionController",
    ]


def test_runtime_queue_admission_decision_shape():
    module = importlib.import_module("core.runtime.runtime_queue_admission")

    decision = module.RuntimeQueueAdmissionDecision(
        accepted=True,
        status="queue_admission_accepted",
        reason="adapter_ready_for_non_executing_scope",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        grant_id="grant-1",
        authority_scope="dry_run",
        risk_level="low",
        adapter_status="adapter_ready",
        queue_admission_id="queue_admission:request-1",
        enqueued=False,
        executed=False,
        scheduler_touched=False,
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "queue_admission_accepted"
    assert decision.reason == "adapter_ready_for_non_executing_scope"
    assert decision.request_id == "request-1"
    assert decision.trace_id == "trace-1"
    assert decision.lease_id == "lease-1"
    assert decision.grant_id == "grant-1"
    assert decision.authority_scope == "dry_run"
    assert decision.risk_level == "low"
    assert decision.adapter_status == "adapter_ready"
    assert decision.queue_admission_id == "queue_admission:request-1"
    assert decision.enqueued is False
    assert decision.executed is False
    assert decision.scheduler_touched is False
    assert decision.metadata == {"source": "test"}


@pytest.mark.parametrize("scope", ["dry_run", "read_only"])
def test_runtime_queue_admission_accepts_adapter_ready_non_executing_scopes(scope: str):
    module = importlib.import_module("core.runtime.runtime_queue_admission")
    controller = module.RuntimeQueueAdmissionController()

    decision = controller.evaluate(
        _adapter_decision(
            accepted=True,
            status="adapter_ready",
            authority_scope=scope,
        ),
        metadata={"source": "test"},
    )

    assert decision.accepted is True
    assert decision.status == "queue_admission_accepted"
    assert decision.reason == "adapter_ready_for_non_executing_scope"
    assert decision.authority_scope == scope
    assert decision.adapter_status == "adapter_ready"
    assert decision.queue_admission_id == "queue_admission:request-1"
    assert decision.enqueued is False
    assert decision.executed is False
    assert decision.scheduler_touched is False
    assert decision.metadata == {"source": "test"}


def test_runtime_queue_admission_rejects_adapter_rejected():
    module = importlib.import_module("core.runtime.runtime_queue_admission")
    controller = module.RuntimeQueueAdmissionController()

    decision = controller.evaluate(
        _adapter_decision(
            accepted=False,
            status="adapter_rejected",
            authority_scope="dry_run",
        )
    )

    assert decision.accepted is False
    assert decision.status == "queue_admission_rejected"
    assert decision.reason == "adapter_not_ready"
    assert decision.adapter_status == "adapter_rejected"
    assert decision.enqueued is False
    assert decision.executed is False
    assert decision.scheduler_touched is False


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
def test_runtime_queue_admission_rejects_disallowed_scopes(scope: str):
    module = importlib.import_module("core.runtime.runtime_queue_admission")
    controller = module.RuntimeQueueAdmissionController()

    decision = controller.evaluate(
        _adapter_decision(
            accepted=True,
            status="adapter_ready",
            authority_scope=scope,
        )
    )

    assert decision.accepted is False
    assert decision.status == "queue_admission_rejected"
    assert decision.reason == "scope_not_allowed_for_queue_admission_v0"
    assert decision.authority_scope == scope
    assert decision.enqueued is False
    assert decision.executed is False
    assert decision.scheduler_touched is False


def test_runtime_queue_admission_does_not_import_scheduler_internals():
    imports = _queue_admission_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_queue_admission must not import scheduler/runtime internals:\n"
        + "\n".join(violations)
    )


def test_runtime_queue_admission_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_queue_admission")
    public_names = {
        name
        for name in dir(module.RuntimeQueueAdmissionController)
        if not name.startswith("_")
    }

    assert public_names == {"evaluate"}
    assert not (public_names & set(FORBIDDEN_METHODS))


def test_runtime_queue_admission_accepted_does_not_enqueue_or_execute():
    calls = _call_names()

    assert "enqueue" not in calls
    assert "execute" not in calls
    assert "mutate" not in calls
    assert "recover" not in calls
    assert "replay" not in calls
