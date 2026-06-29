from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.runtime.runtime_boundary import RuntimeBoundary, RuntimeBoundaryRejected
from core.runtime.runtime_mutation_guard import RuntimeMutationGuard, RuntimeMutationRejected
from core.runtime.runtime_ownership import (

    RuntimeAction,
    RuntimeOwner,
    RuntimeResource,
    can_access,
    system_authority_rules,
)
pytestmark = [pytest.mark.contract]


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_OWNERSHIP_FILE = ROOT / "core/runtime/runtime_ownership.py"

SYSTEM_DENIED_MUTATIONS = (
    (RuntimeResource.QUEUE_STATE, RuntimeAction.WRITE),
    (RuntimeResource.QUEUE_STATE, RuntimeAction.TRANSITION),
    (RuntimeResource.EXECUTION_RESULT, RuntimeAction.WRITE),
    (RuntimeResource.ORCHESTRATION_STATE, RuntimeAction.DISPATCH),
    (RuntimeResource.REPAIR_STATE, RuntimeAction.WRITE),
    (RuntimeResource.RUNTIME_SNAPSHOT, RuntimeAction.WRITE),
    (RuntimeResource.RUNTIME_INCIDENT, RuntimeAction.REPLAY),
)

SYSTEM_ALLOWED_OBSERVABILITY = (
    (RuntimeResource.QUEUE_STATE, RuntimeAction.READ),
    (RuntimeResource.EXECUTION_RESULT, RuntimeAction.READ),
    (RuntimeResource.RUNTIME_EVENT, RuntimeAction.EMIT),
    (RuntimeResource.RUNTIME_INCIDENT, RuntimeAction.EMIT),
    (RuntimeResource.RUNTIME_SNAPSHOT, RuntimeAction.SNAPSHOT),
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_source(path), filename=str(path))


def test_system_owner_is_scoped_not_wildcard() -> None:
    allowed = {
        (resource, action)
        for resource in RuntimeResource
        for action in RuntimeAction
        if can_access(RuntimeOwner.SYSTEM, resource, action)
    }

    all_declared = {
        (resource, action)
        for resource in RuntimeResource
        for action in RuntimeAction
    }

    assert allowed == {(resource, action) for _, resource, action in system_authority_rules()}
    assert allowed != all_declared
    assert len(allowed) < len(all_declared)

    for resource, action in SYSTEM_DENIED_MUTATIONS:
        assert (resource, action) not in allowed
        assert can_access(RuntimeOwner.SYSTEM, resource, action) is False

    for resource, action in SYSTEM_ALLOWED_OBSERVABILITY:
        assert (resource, action) in allowed
        assert can_access(RuntimeOwner.SYSTEM, resource, action) is True


def test_mutation_guard_rejects_system_mutation_requests() -> None:
    for resource, action in SYSTEM_DENIED_MUTATIONS:
        with pytest.raises(RuntimeMutationRejected):
            RuntimeMutationGuard.validate(
                RuntimeOwner.SYSTEM,
                resource,
                action,
                reason="system_authority_enforcement",
            )


def test_mutation_guard_allows_system_observability_requests() -> None:
    for resource, action in SYSTEM_ALLOWED_OBSERVABILITY:
        request = RuntimeMutationGuard.validate(
            RuntimeOwner.SYSTEM,
            resource,
            action,
            reason="system_authority_observability",
        )

        assert request.allowed is True
        assert request.owner is RuntimeOwner.SYSTEM
        assert request.resource is resource
        assert request.action is action


def test_runtime_boundary_no_longer_treats_system_as_universal_owner() -> None:
    boundary = RuntimeBoundary()

    rejected_operations = (
        boundary.request_queue_transition,
        boundary.request_execution_result_write,
        boundary.request_orchestration_dispatch,
    )
    for operation in rejected_operations:
        with pytest.raises(RuntimeBoundaryRejected):
            operation(RuntimeOwner.SYSTEM)

    assert boundary.request_runtime_snapshot(RuntimeOwner.SYSTEM).allowed is True
    assert boundary.emit_runtime_event(RuntimeOwner.SYSTEM).allowed is True
    assert boundary.emit_runtime_incident(RuntimeOwner.SYSTEM).allowed is True


def test_runtime_ownership_source_has_no_system_return_true_wildcard() -> None:
    source = _source(RUNTIME_OWNERSHIP_FILE)

    assert 'SYSTEM = "system"' in source
    assert "def system_authority_rules" in source
    assert "_SYSTEM_ALLOWED_RULES" in source

    for node in ast.walk(_tree(RUNTIME_OWNERSHIP_FILE)):
        if isinstance(node, ast.If):
            segment = ast.get_source_segment(source, node) or ""
            if "RuntimeOwner.SYSTEM" not in segment:
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and isinstance(child.value, ast.Constant):
                    assert child.value.value is not True, segment
