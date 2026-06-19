from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MUTATION_SURFACES = {
    "core/runtime/runtime_mutation_gateway.py": "AUTHORITY",
    "core/runtime/governed_mutation_runtime.py": "REQUEST",
    "core/runtime/mutation_runtime_pipeline.py": "REQUEST",
    "core/runtime/mutation_patch_apply.py": "PERSISTENCE",
    "core/runtime/controlled_mutation_bridge.py": "REQUEST",
}

CANONICAL_GATEWAY_FILE = "core/runtime/runtime_mutation_gateway.py"
REQUEST_CLIENT_FILES = {
    path for path, role in MUTATION_SURFACES.items() if role != "AUTHORITY"
}

DIRECT_MUTATION_CALLS = {
    "write_text",
    "write_bytes",
    "replace",
    "copy2",
    "move",
    "rmtree",
    "unlink",
}

CANONICAL_DECISION_TERMS = {
    "authority_evaluator.evaluate",
    "capability_evaluator.evaluate",
    "kernel_protection.evaluate",
    "mutation_policy.evaluate",
    "classify_mutation_risk",
}


def _repo_rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_source(path), filename=str(path))


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return ""


def _imports_name(path: Path, name: str) -> bool:
    tree = _tree(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == name or alias.name.endswith(f".{name}") for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == name for alias in node.names):
                return True
    return False


def _calls(path: Path, names: set[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(_tree(path)):
        call = _call_name(node)
        if call in names:
            found.append((getattr(node, "lineno", 0), call))
    return found


def test_runtime_mutation_authority_contract_exists() -> None:
    authority = ROOT / "core/runtime/runtime_mutation_authority.py"
    source = _source(authority)

    assert "CANONICAL_MUTATION_AUTHORITY" in source
    assert "RuntimeMutationCapability" in source
    assert "issue_runtime_mutation_capability" in source
    assert "require_runtime_mutation_authority" in source
    assert "MUTATION_SURFACE_ROLES" in source


def test_runtime_mutation_gateway_is_the_only_decision_owner() -> None:
    gateway_source = _source(ROOT / CANONICAL_GATEWAY_FILE)
    assert "class RuntimeMutationGateway" in gateway_source
    assert "def mutate" in gateway_source
    for term in CANONICAL_DECISION_TERMS:
        assert term in gateway_source

    drift: dict[str, list[str]] = {}
    for rel in REQUEST_CLIENT_FILES:
        source = _source(ROOT / rel)
        leaked_terms = [term for term in CANONICAL_DECISION_TERMS if term in source]
        if leaked_terms:
            drift[rel] = leaked_terms

    assert not drift, {"request_client_decision_drift": drift}


def test_mutation_request_clients_delegate_authority() -> None:
    for rel in REQUEST_CLIENT_FILES:
        path = ROOT / rel
        source = _source(path)
        assert "runtime_mutation_authority" in source or rel == "core/runtime/controlled_mutation_bridge.py", rel

    pipeline = ROOT / "core/runtime/mutation_runtime_pipeline.py"
    assert "issue_runtime_mutation_capability" in _source(pipeline)
    assert "mutation_capability=mutation_capability" in _source(pipeline)

    patch_apply = ROOT / "core/runtime/mutation_patch_apply.py"
    patch_source = _source(patch_apply)
    assert "mutation_capability" in patch_source
    assert "require_runtime_mutation_authority" in patch_source


def test_direct_file_mutation_surfaces_are_persistence_not_authority() -> None:
    direct = {
        rel: _calls(ROOT / rel, DIRECT_MUTATION_CALLS)
        for rel in REQUEST_CLIENT_FILES
    }

    assert direct["core/runtime/mutation_patch_apply.py"], direct
    assert "require_runtime_mutation_authority" in _source(ROOT / "core/runtime/mutation_patch_apply.py")
    assert "RuntimeMutationGateway" not in _source(ROOT / "core/runtime/mutation_patch_apply.py")


def test_runtime_mutation_sovereignty_targets_are_closed() -> None:
    targets = sorted(REQUEST_CLIENT_FILES | {"core/runtime/runtime_ownership.py"})
    assert targets == [
        "core/runtime/controlled_mutation_bridge.py",
        "core/runtime/governed_mutation_runtime.py",
        "core/runtime/mutation_patch_apply.py",
        "core/runtime/mutation_runtime_pipeline.py",
        "core/runtime/runtime_ownership.py",
    ]
