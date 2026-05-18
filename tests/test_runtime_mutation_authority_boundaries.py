"""Runtime mutation authority boundary regression tests.

This test enforces the Phase 4 Runtime Kernel Boundary Contract at a
lightweight static-analysis level. It checks external-facing layers for direct
imports or obvious calls into mutation, rollback, recovery, patch, approval, or
repair-transaction authority surfaces.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (
    REPO_ROOT / "core",
    REPO_ROOT / "services",
)

EXTERNAL_LAYER_ROOTS = (
    REPO_ROOT / "core" / "capabilities",
    REPO_ROOT / "core" / "agent",
    REPO_ROOT / "core" / "planning",
    REPO_ROOT / "services",
)

BOOTSTRAP_OWNER = REPO_ROOT / "services" / "system_boot.py"

FORBIDDEN_AUTHORITY_TOKENS = (
    "mutate",
    "mutation",
    "apply_patch",
    "rollback",
    "recover",
    "recovery",
    "override",
    "patch_apply",
    "mutation_patch_apply",
    "atomic_edit",
    "atomic_apply",
    "commit_gate",
    "repair_execution",
    "approval",
    "repair_transaction",
    "run_governed_repair_transaction",
    "build_gateway_request_from_repair_transaction",
    "runtime_repair_apply",
    "recovery_coordinator",
    "recovery_policy",
    "recovery_commit_gate",
    "recovery_execution",
    "force_execute",
    "bypass",
    "unsafe_apply",
    "applypatch",
    "atomicedit",
    "atomicapply",
    "mutationruntimepipeline",
    "mutationboundary",
    "rollbackverification",
    "runtimerecoverycoordinator",
    "runtimerecoverypolicy",
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if root.exists():
            files.extend(
                path
                for path in root.rglob("*.py")
                if "__pycache__" not in path.parts
            )
    return sorted(files)


def _is_external_layer(path: Path) -> bool:
    return any(path.is_relative_to(root) for root in EXTERNAL_LAYER_ROOTS)


def _is_bootstrap_owner(path: Path) -> bool:
    return path == BOOTSTRAP_OWNER


def _module_name_for_path(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(relative.parts)


def _resolve_relative_import(path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module

    current_module_parts = _module_name_for_path(path).split(".")
    package_parts = current_module_parts[:-1]
    if node.level > len(package_parts) + 1:
        return node.module

    anchor = package_parts[: len(package_parts) - node.level + 1]
    if node.module:
        anchor.extend(node.module.split("."))
    return ".".join(anchor)


def _matches_forbidden_authority(symbol: str) -> bool:
    normalized = symbol.replace("-", "_").lower()
    squashed = normalized.replace("_", "")
    return any(
        token in normalized or token in squashed
        for token in FORBIDDEN_AUTHORITY_TOKENS
    )


def _attribute_chain(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent = _attribute_chain(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr

    return None


def _matches_forbidden_call(symbol: str) -> bool:
    terminal_name = symbol.rsplit(".", 1)[-1]
    normalized = terminal_name.replace("-", "_").lower()
    if normalized.startswith(("_build_", "build_", "_format_", "format_")):
        return False
    return _matches_forbidden_authority(terminal_name)


def _authority_violations(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_name = alias.name
                bound_name = alias.asname or alias.name.rsplit(".", 1)[-1]
                if _matches_forbidden_authority(
                    imported_name
                ) or _matches_forbidden_authority(bound_name):
                    violations.append((node.lineno, imported_name))
            continue

        if isinstance(node, ast.ImportFrom):
            base_module = _resolve_relative_import(path, node)
            imported_names = [base_module] if base_module else []
            imported_names.extend(
                f"{base_module}.{alias.name}" if base_module else alias.name
                for alias in node.names
                if alias.name != "*"
            )
            imported_names.extend(
                alias.asname
                for alias in node.names
                if alias.asname and alias.name != "*"
            )

            for imported_name in imported_names:
                if imported_name and _matches_forbidden_authority(imported_name):
                    violations.append((node.lineno, imported_name))
            continue

        if isinstance(node, ast.Call):
            called_symbol = _attribute_chain(node.func)
            if called_symbol and _matches_forbidden_call(called_symbol):
                violations.append((node.lineno, called_symbol))

    return violations


def test_external_layers_do_not_claim_mutation_authority_directly():
    violations: list[str] = []

    for path in _iter_python_files():
        if not _is_external_layer(path) or _is_bootstrap_owner(path):
            continue

        for line_number, symbol in _authority_violations(path):
            display_path = path.relative_to(REPO_ROOT).as_posix()
            violations.append(f"{display_path}:{line_number}: {symbol}")

    assert not violations, (
        "External-facing layers must not directly import or call mutation, "
        "rollback, recovery, patch, approval, or repair-transaction authority "
        "surfaces from the Phase 4 Runtime Kernel Boundary Contract:\n"
        + "\n".join(violations)
    )
