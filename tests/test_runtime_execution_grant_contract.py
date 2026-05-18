from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GRANT_PATH = REPO_ROOT / "core" / "runtime" / "runtime_execution_grant.py"

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


def _grant_imports() -> list[str]:
    tree = ast.parse(GRANT_PATH.read_text(encoding="utf-8"), filename=str(GRANT_PATH))
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


def test_runtime_execution_grant_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_execution_grant")

    assert module.__all__ == ["RuntimeExecutionGrant"]


def test_runtime_execution_grant_default_deny_shape():
    module = importlib.import_module("core.runtime.runtime_execution_grant")

    grant = module.RuntimeExecutionGrant(
        grant_id="grant-1",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        metadata={"source": "test"},
    )

    assert grant.grant_id == "grant-1"
    assert grant.request_id == "request-1"
    assert grant.trace_id == "trace-1"
    assert grant.lease_id == "lease-1"
    assert grant.granted is False
    assert grant.status == "grant_not_issued"
    assert grant.reason == "execution_not_granted"
    assert grant.authority_scope == "none"
    assert grant.risk_level == "unknown"
    assert grant.granted_by is None
    assert grant.expires_at is None
    assert grant.metadata == {"source": "test"}


def test_runtime_execution_grant_issued_shape_is_authority_only():
    module = importlib.import_module("core.runtime.runtime_execution_grant")

    grant = module.RuntimeExecutionGrant(
        grant_id="grant-1",
        request_id="request-1",
        trace_id="trace-1",
        lease_id="lease-1",
        granted=True,
        status="grant_issued",
        reason="eligible_for_non_executing_scope",
        authority_scope="dry_run",
        risk_level="low",
        granted_by="runtime_grant_issuer_v0",
        expires_at=None,
        metadata={
            "eligibility": {
                "eligible": True,
                "rule": "scoped_low_risk",
                "authority_scope": "dry_run",
                "risk_level": "low",
            },
        },
    )

    assert grant.granted is True
    assert grant.status == "grant_issued"
    assert grant.reason == "eligible_for_non_executing_scope"
    assert grant.authority_scope == "dry_run"
    assert grant.risk_level == "low"
    assert grant.granted_by == "runtime_grant_issuer_v0"
    assert grant.metadata["eligibility"]["eligible"] is True


def test_runtime_execution_grant_lineage_connects_request_trace_and_lease():
    module = importlib.import_module("core.runtime.runtime_ownership_gate")
    gate = module.RuntimeOwnershipGate()

    decision = gate.evaluate_request(
        {
            "surface": "runtime_public_surface",
            "operation": "submit_runtime_task",
            "request": {
                "task": {"title": "demo"},
                "metadata": {"request_id": "request-1", "source": "test"},
            },
        }
    )

    grant = decision.execution_grant

    assert grant.granted is False
    assert grant.request_id == "request-1"
    assert grant.request_id == decision.request_id
    assert grant.trace_id == decision.admission_trace.trace_id
    assert grant.lease_id == decision.lease.lease_id
    assert decision.admission_trace.grant_id == grant.grant_id


def test_runtime_execution_grant_does_not_import_scheduler_internals():
    imports = _grant_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_execution_grant must not import scheduler internals:\n"
        + "\n".join(violations)
    )


def test_runtime_execution_grant_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_execution_grant")
    public_names = {
        name
        for name in dir(module.RuntimeExecutionGrant)
        if not name.startswith("_")
    }

    assert not (public_names & set(FORBIDDEN_METHODS))
