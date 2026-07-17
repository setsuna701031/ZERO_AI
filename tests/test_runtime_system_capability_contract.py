from __future__ import annotations

import pytest

from core.runtime.runtime_system_capability import (

    RuntimeCapabilityClass,
    RuntimeSystemCapabilityError,
    SYSTEM_CAPABILITY_INVENTORY,
    issue_runtime_system_capability,
    validate_runtime_system_capability,
)
pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def test_system_permission_inventory_has_every_required_class_and_no_admin_grant() -> None:
    assert set(SYSTEM_CAPABILITY_INVENTORY) == set(RuntimeCapabilityClass)
    assert SYSTEM_CAPABILITY_INVENTORY[RuntimeCapabilityClass.ADMIN] == frozenset()
    for grants in SYSTEM_CAPABILITY_INVENTORY.values():
        assert all("*" not in grant for grant in grants)


def test_live_system_token_validates_all_authority_dimensions() -> None:
    claims = {"task_id": "task:1", "package_id": "package:1"}
    token = issue_runtime_system_capability(
        issuer="RuntimeDispatcher",
        capability_class=RuntimeCapabilityClass.EXECUTE,
        resource="runtime_task",
        action="execute",
        scope=claims,
        lineage=claims,
    )

    assert validate_runtime_system_capability(
        token,
        issuer="RuntimeDispatcher",
        capability_class=RuntimeCapabilityClass.EXECUTE,
        resource="runtime_task",
        action="execute",
        scope=claims,
        lineage=claims,
    ) is token


def test_unknown_issuer_cannot_issue_system_authority() -> None:
    with pytest.raises(RuntimeSystemCapabilityError, match="issuer_not_authorized"):
        issue_runtime_system_capability(
            issuer="SYSTEM",
            capability_class=RuntimeCapabilityClass.ADMIN,
            resource="runtime",
            action="admin",
            scope={"runtime_id": "1"},
            lineage={"runtime_id": "1"},
        )
