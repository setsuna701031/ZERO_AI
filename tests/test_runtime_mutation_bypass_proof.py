from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SYSTEM_WILDCARD_FILE = "core/runtime/runtime_ownership.py"
PATCH_APPLY_FILE = "core/runtime/mutation_patch_apply.py"
CONTROLLED_BRIDGE_FILE = "core/runtime/controlled_mutation_bridge.py"
PIPELINE_FILE = "core/runtime/mutation_runtime_pipeline.py"

DIRECT_FILE_MUTATION_METHODS = {
    "write_text",
    "write_bytes",
    "copy2",
    "replace",
    "unlink",
    "rmtree",
    "move",
}


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def _tree(rel: str) -> ast.Module:
    return ast.parse(_source(rel), filename=rel)


def _call_name(node: ast.AST) -> str:
    if not isinstance(node, ast.Call):
        return ""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _calls(rel: str, names: set[str]) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for node in ast.walk(_tree(rel)):
        name = _call_name(node)
        if name in names:
            result.append((getattr(node, "lineno", 0), name))
    return result


def _imports(rel: str, imported: str) -> bool:
    for node in ast.walk(_tree(rel)):
        if isinstance(node, ast.Import):
            if any(alias.name == imported or alias.name.endswith(f".{imported}") for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == imported for alias in node.names):
                return True
    return False


def test_system_owner_wildcard_authority_is_sealed() -> None:
    source = _source(SYSTEM_WILDCARD_FILE)
    assert 'SYSTEM = "system"' in source
    assert "_SYSTEM_ALLOWED_RULES" in source
    assert "def system_authority_rules" in source
    assert "if runtime_owner is RuntimeOwner.SYSTEM:\n        return True" not in source


def test_patch_apply_has_direct_file_write_surface_outside_gateway() -> None:
    direct_calls = _calls(PATCH_APPLY_FILE, DIRECT_FILE_MUTATION_METHODS)
    assert direct_calls, {"expected_direct_file_mutation_calls": PATCH_APPLY_FILE}
    assert not _imports(PATCH_APPLY_FILE, "RuntimeMutationGateway")
    assert not _imports(PATCH_APPLY_FILE, "RuntimeMutationGuard")
    assert not _imports(PATCH_APPLY_FILE, "guard_mutation")


def test_pipeline_calls_patch_apply_without_gateway_import() -> None:
    assert _calls(PIPELINE_FILE, {"apply_patch_plan"})
    assert not _imports(PIPELINE_FILE, "RuntimeMutationGateway")


def test_controlled_mutation_bridge_uses_execution_probe_not_gateway() -> None:
    source = _source(CONTROLLED_BRIDGE_FILE)
    assert "AgentExecutionRuntime" in source
    assert "mutation_executed" in source
    assert "real_source_mutation_blocked_in_v1" in source
    assert not _imports(CONTROLLED_BRIDGE_FILE, "RuntimeMutationGateway")
