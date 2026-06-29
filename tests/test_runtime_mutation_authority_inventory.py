from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract]



ROOT = Path(__file__).resolve().parents[1]


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_runtime_mutation_authority_module_exports_contract() -> None:
    source = _source("core/runtime/runtime_mutation_authority.py")
    for name in (
        "RuntimeMutationCapability",
        "RuntimeMutationAuthorityError",
        "issue_runtime_mutation_capability",
        "validate_runtime_mutation_capability",
        "require_runtime_mutation_authority",
        "mutation_surface_inventory",
    ):
        assert name in source


def test_request_clients_do_not_import_gateway_as_authority() -> None:
    request_clients = {
        "core/runtime/mutation_patch_apply.py",
        "core/runtime/mutation_runtime_pipeline.py",
        "core/runtime/controlled_mutation_bridge.py",
    }
    findings = {
        rel: "RuntimeMutationGateway" in _source(rel)
        for rel in request_clients
    }
    assert not any(findings.values()), findings


def test_authority_inventory_has_no_unknown_core_surfaces() -> None:
    from core.runtime.runtime_mutation_authority import (
        MUTATION_AUTHORITY_ROLE,
        MUTATION_PERSISTENCE_ROLE,
        MUTATION_REQUEST_ROLE,
        mutation_surface_inventory,
    )

    inventory = mutation_surface_inventory()
    assert inventory["core/runtime/runtime_mutation_gateway.py"] == MUTATION_AUTHORITY_ROLE
    assert inventory["core/runtime/mutation_patch_apply.py"] == MUTATION_PERSISTENCE_ROLE
    assert inventory["core/runtime/mutation_runtime_pipeline.py"] == MUTATION_REQUEST_ROLE
    assert inventory["core/runtime/governed_mutation_runtime.py"] == MUTATION_REQUEST_ROLE
    assert inventory["core/runtime/controlled_mutation_bridge.py"] == MUTATION_REQUEST_ROLE
