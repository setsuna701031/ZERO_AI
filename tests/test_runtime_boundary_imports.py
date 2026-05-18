"""Runtime boundary import regression tests.

These checks enforce the Phase 4 Runtime Kernel Boundary Contract without
creating runtime APIs or changing production behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (
    REPO_ROOT / "core",
    REPO_ROOT / "services",
    REPO_ROOT / "tests",
)

EXTERNAL_LAYER_ROOTS = (
    REPO_ROOT / "core" / "capabilities",
    REPO_ROOT / "core" / "agent",
    REPO_ROOT / "core" / "planning",
    REPO_ROOT / "services",
)

FORBIDDEN_IMPORT_TARGETS = (
    "core.tasks.scheduler",
    "core.tasks.scheduler_core",
    "core.runtime.mutation_runtime_pipeline",
    "core.runtime.mutation_boundary",
    "core.runtime.mutation_patch_apply",
    "core.runtime.rollback_verification",
    "core.runtime.runtime_recovery_coordinator",
    "core.runtime.runtime_recovery_policy",
    "core.runtime.runtime_recovery_commit_gate",
)

ALLOWED_DIRECT_IMPORTS = {
    # Bootstrap wiring is the current runtime construction owner. This exception
    # must not expand into general service-layer scheduler access.
    ("services/system_boot.py", "core.tasks.scheduler"),
    ("services/system_boot.py", "core.tasks.scheduler.Scheduler"),
}


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


def _is_forbidden_import(module_name: str) -> bool:
    return any(
        module_name == target or module_name.startswith(f"{target}.")
        for target in FORBIDDEN_IMPORT_TARGETS
    )


def _is_allowed_direct_import(path: Path, module_name: str) -> bool:
    display_path = path.relative_to(REPO_ROOT).as_posix()
    return (display_path, module_name) in ALLOWED_DIRECT_IMPORTS


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


def _imported_modules(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend((node.lineno, alias.name) for alias in node.names)
            continue

        if isinstance(node, ast.ImportFrom):
            base_module = _resolve_relative_import(path, node)
            if not base_module:
                continue

            imported.append((node.lineno, base_module))
            imported.extend(
                (node.lineno, f"{base_module}.{alias.name}")
                for alias in node.names
                if alias.name != "*"
            )

    return imported


def test_external_layers_do_not_import_runtime_boundary_internals_directly():
    violations: list[str] = []

    for path in _iter_python_files():
        if not _is_external_layer(path):
            continue

        for line_number, module_name in _imported_modules(path):
            if _is_forbidden_import(module_name) and not _is_allowed_direct_import(
                path, module_name
            ):
                display_path = path.relative_to(REPO_ROOT).as_posix()
                violations.append(f"{display_path}:{line_number}: {module_name}")

    assert not violations, (
        "External-facing layers must not directly import runtime/scheduler "
        "internals from the Phase 4 Runtime Kernel Boundary Contract:\n"
        + "\n".join(violations)
    )
