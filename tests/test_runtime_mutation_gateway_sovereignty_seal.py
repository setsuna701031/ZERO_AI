from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MUTATION_SURFACES = {
    "core/runtime/runtime_mutation_gateway.py": "canonical_gateway",
    "core/runtime/mutation_patch_apply.py": "patch_apply_surface",
    "core/runtime/mutation_runtime_pipeline.py": "pipeline_surface",
    "core/runtime/governed_mutation_runtime.py": "governed_runtime_surface",
    "core/runtime/controlled_mutation_bridge.py": "controlled_bridge_surface",
}

CANONICAL_GATEWAY_FILE = "core/runtime/runtime_mutation_gateway.py"
BYPASS_CANDIDATE_FILES = {
    "core/runtime/mutation_patch_apply.py",
    "core/runtime/mutation_runtime_pipeline.py",
    "core/runtime/controlled_mutation_bridge.py",
}

REQUIRED_GATEWAY_GUARDS = {
    "runtime_identity_required",
    "runtime_authority_scope_required",
    "runtime_capability_scope_required",
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


def _string_constants(path: Path) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.add(node.value)
    return values


def test_runtime_mutation_gateway_declares_canonical_blocking_guards() -> None:
    gateway = ROOT / CANONICAL_GATEWAY_FILE
    source = _source(gateway)
    constants = _string_constants(gateway)

    assert "class RuntimeMutationGateway" in source
    assert "def mutate" in source
    assert REQUIRED_GATEWAY_GUARDS <= constants
    assert "authority_evaluator.evaluate" in source
    assert "capability_evaluator.evaluate" in source
    assert "kernel_protection.evaluate" in source
    assert "mutation_policy.evaluate" in source


def test_mutation_surfaces_are_mapped_and_classified() -> None:
    missing = [path for path in MUTATION_SURFACES if not (ROOT / path).exists()]
    assert not missing, {"missing_mutation_surfaces": missing}

    classification = {
        path: {
            "role": role,
            "imports_gateway": _imports_name(ROOT / path, "RuntimeMutationGateway"),
            "direct_mutation_calls": _calls(ROOT / path, DIRECT_MUTATION_CALLS),
            "calls_apply_patch_plan": bool(_calls(ROOT / path, {"apply_patch_plan"})),
        }
        for path, role in MUTATION_SURFACES.items()
    }

    assert classification[CANONICAL_GATEWAY_FILE]["imports_gateway"] is False
    assert classification["core/runtime/mutation_patch_apply.py"]["direct_mutation_calls"], classification
    assert classification["core/runtime/mutation_runtime_pipeline.py"]["calls_apply_patch_plan"], classification


def test_current_bypass_candidates_do_not_enter_runtime_mutation_gateway() -> None:
    findings: dict[str, dict[str, object]] = {}

    for rel in sorted(BYPASS_CANDIDATE_FILES):
        path = ROOT / rel
        findings[rel] = {
            "imports_gateway": _imports_name(path, "RuntimeMutationGateway"),
            "imports_guard": _imports_name(path, "guard_mutation") or _imports_name(path, "RuntimeMutationGuard"),
            "direct_mutation_calls": _calls(path, DIRECT_MUTATION_CALLS),
            "apply_patch_plan_calls": _calls(path, {"apply_patch_plan"}),
        }

    # This is a proof test, not the final enforcement seal: it pins the audit's
    # current finding that legacy mutation surfaces can still exist outside the
    # canonical RuntimeMutationGateway path.
    assert any(not item["imports_gateway"] for item in findings.values()), findings
    assert findings["core/runtime/mutation_patch_apply.py"]["direct_mutation_calls"], findings
    assert findings["core/runtime/controlled_mutation_bridge.py"]["imports_gateway"] is False, findings


def test_runtime_gateway_sovereignty_next_seal_has_explicit_targets() -> None:
    targets = sorted(BYPASS_CANDIDATE_FILES | {"core/runtime/runtime_ownership.py"})
    assert targets == [
        "core/runtime/controlled_mutation_bridge.py",
        "core/runtime/mutation_patch_apply.py",
        "core/runtime/mutation_runtime_pipeline.py",
        "core/runtime/runtime_ownership.py",
    ]
