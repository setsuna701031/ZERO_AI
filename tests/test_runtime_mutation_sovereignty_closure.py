from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SURFACES = {
    "core/runtime/runtime_mutation_gateway.py": "AUTHORITY",
    "core/runtime/governed_mutation_runtime.py": "REQUEST",
    "core/runtime/mutation_runtime_pipeline.py": "REQUEST",
    "core/runtime/mutation_patch_apply.py": "PERSISTENCE",
    "core/runtime/controlled_mutation_bridge.py": "REQUEST",
}

AUTHORITY_DECISION_TERMS = {
    "authority_evaluator.evaluate",
    "capability_evaluator.evaluate",
    "kernel_protection.evaluate",
    "mutation_policy.evaluate",
    "classify_mutation_risk",
}


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def _tree(rel: str) -> ast.Module:
    return ast.parse(_source(rel), filename=rel)


def _calls(rel: str, names: set[str]) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    for node in ast.walk(_tree(rel)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in names:
            results.append((getattr(node, "lineno", 0), name))
    return results


def test_mutation_surface_roles_are_canonicalized() -> None:
    from core.runtime.runtime_mutation_authority import mutation_surface_inventory

    assert mutation_surface_inventory() == SURFACES


def test_only_gateway_owns_mutation_decisions() -> None:
    gateway_source = _source("core/runtime/runtime_mutation_gateway.py")
    for term in AUTHORITY_DECISION_TERMS:
        assert term in gateway_source

    leaks: dict[str, list[str]] = {}
    for rel, role in SURFACES.items():
        if role == "AUTHORITY":
            continue
        source = _source(rel)
        found = [term for term in AUTHORITY_DECISION_TERMS if term in source]
        if found:
            leaks[rel] = found

    assert not leaks, {"non_gateway_mutation_decision_drift": leaks}


def test_patch_apply_is_persistence_client_with_authority_gate() -> None:
    source = _source("core/runtime/mutation_patch_apply.py")
    assert "mutation_capability" in source
    assert "require_runtime_mutation_authority" in source
    assert _calls("core/runtime/mutation_patch_apply.py", {"copy2", "write_text"})


def test_pipeline_delegates_to_patch_apply_with_capability() -> None:
    source = _source("core/runtime/mutation_runtime_pipeline.py")
    assert "issue_runtime_mutation_capability" in source
    assert "mutation_capability=mutation_capability" in source
    assert _calls("core/runtime/mutation_runtime_pipeline.py", {"apply_patch_plan"})


def test_closure_document_records_non_mainline_risks() -> None:
    doc = _source("docs/runtime_mutation_sovereignty_closure.md")
    assert "RuntimeMutationGateway" in doc
    assert "Non-mainline issues" in doc
    assert "Evidence reference ownership" in doc
