from __future__ import annotations

import pytest

from core.runtime.runtime_mutation_authority import (
    CANONICAL_MUTATION_AUTHORITY,
    RuntimeMutationAuthorityError,
    issue_runtime_mutation_capability,
    validate_runtime_mutation_capability,
)
from core.runtime.runtime_system_capability import (
    RuntimeCapabilityClass,
    RuntimeSystemCapabilityError,
    issue_runtime_system_capability,
    validate_runtime_system_capability,
)


def test_system_token_rejects_scope_and_lineage_drift() -> None:
    token = issue_runtime_system_capability(
        issuer="TaskRunner",
        capability_class=RuntimeCapabilityClass.ROLLBACK,
        resource="workspace",
        action="rollback",
        scope={"task_id": "task:1"},
        lineage={"task_id": "task:1", "attempt": "1"},
    )
    for scope, lineage in (
        ({"task_id": "task:2"}, {"task_id": "task:1"}),
        ({"task_id": "task:1"}, {"task_id": "task:2"}),
    ):
        with pytest.raises(RuntimeSystemCapabilityError):
            validate_runtime_system_capability(
                token,
                issuer="TaskRunner",
                capability_class=RuntimeCapabilityClass.ROLLBACK,
                resource="workspace",
                action="rollback",
                scope=scope,
                lineage=lineage,
            )


def test_mutation_capability_is_request_target_scope_and_lineage_bound() -> None:
    token = issue_runtime_mutation_capability(
        issuer=CANONICAL_MUTATION_AUTHORITY,
        source="test",
        request_id="request:1",
        operation_type="file_write",
        target_path="workspace/a.txt",
        scope={"request_id": "request:1"},
        lineage={"task_id": "task:1"},
    )
    validated = validate_runtime_mutation_capability(
        token,
        source="test",
        operation_type="file_write",
        target_path="workspace/a.txt",
        scope={"request_id": "request:1"},
        lineage={"task_id": "task:1"},
    )
    assert validated["validated"] is True

    with pytest.raises(RuntimeMutationAuthorityError, match="scope_mismatch"):
        validate_runtime_mutation_capability(
            token,
            source="test",
            operation_type="file_write",
            target_path="workspace/a.txt",
            scope={"request_id": "request:2"},
            lineage={"task_id": "task:1"},
        )


def test_mutation_capability_rejects_wildcard_grants() -> None:
    token = issue_runtime_mutation_capability(
        issuer=CANONICAL_MUTATION_AUTHORITY,
        source="test",
        request_id="request:1",
        operation_type="file_write",
        target_path="workspace/a.txt",
        allowed_operations=("*",),
        allowed_targets=("*",),
    )
    with pytest.raises(RuntimeMutationAuthorityError, match="wildcard_authority_forbidden"):
        validate_runtime_mutation_capability(
            token,
            source="test",
            operation_type="file_write",
            target_path="workspace/a.txt",
        )
