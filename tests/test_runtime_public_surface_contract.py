from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE_PATH = REPO_ROOT / "core" / "runtime" / "runtime_public_surface.py"

EXPECTED_PUBLIC_SYMBOLS = (
    "submit_runtime_task",
    "request_runtime_repair",
    "request_runtime_mutation",
    "query_runtime_status",
    "request_runtime_replay",
    "request_runtime_recovery",
)

CONTRACT_STUB_SYMBOLS = (
    "request_runtime_repair",
    "request_runtime_mutation",
    "request_runtime_replay",
    "request_runtime_recovery",
)

FORBIDDEN_SCHEDULER_IMPORTS = (
    "core.tasks.scheduler",
    "core.tasks.scheduler_core",
)


def _imported_modules() -> list[str]:
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"), filename=str(SURFACE_PATH))
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
            continue

        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
            imports.extend(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if alias.name != "*"
            )

    return imports


def test_runtime_public_surface_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_public_surface")

    assert module.__doc__


def test_runtime_public_surface_exports_expected_symbols():
    module = importlib.import_module("core.runtime.runtime_public_surface")

    assert tuple(module.__all__) == EXPECTED_PUBLIC_SYMBOLS
    for symbol in EXPECTED_PUBLIC_SYMBOLS:
        assert callable(getattr(module, symbol))


@pytest.mark.parametrize("symbol", CONTRACT_STUB_SYMBOLS)
def test_runtime_public_surface_functions_are_contract_stubs(symbol: str):
    module = importlib.import_module("core.runtime.runtime_public_surface")

    with pytest.raises(NotImplementedError):
        getattr(module, symbol)()


def test_query_runtime_status_returns_read_only_not_connected_shape():
    module = importlib.import_module("core.runtime.runtime_public_surface")

    assert module.query_runtime_status() == {
        "status": "not_connected",
        "surface": "runtime_public_surface",
        "operation": "query_runtime_status",
        "runtime_connected": False,
        "details": {},
    }


def test_submit_runtime_task_returns_request_only_not_connected_envelope():
    module = importlib.import_module("core.runtime.runtime_public_surface")
    task = {"title": "demo task", "steps": [{"type": "noop"}]}
    metadata = {"source": "contract-test"}

    result = module.submit_runtime_task(task, metadata=metadata)

    assert result == {
        "status": "accepted_not_connected",
        "surface": "runtime_public_surface",
        "operation": "submit_runtime_task",
        "runtime_connected": False,
        "request": {
            "task": task,
            "metadata": metadata,
        },
        "details": {
            "message": (
                "Runtime public surface accepted the request envelope but is not "
                "connected to execution runtime."
            ),
        },
    }


def test_submit_runtime_task_does_not_mutate_input_task():
    module = importlib.import_module("core.runtime.runtime_public_surface")
    task = {"title": "demo task", "steps": [{"type": "noop"}]}
    before = {"title": "demo task", "steps": [{"type": "noop"}]}

    module.submit_runtime_task(task)

    assert task == before


def test_runtime_public_surface_does_not_import_scheduler_internals():
    imports = _imported_modules()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_SCHEDULER_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_public_surface must not import scheduler internals:\n"
        + "\n".join(violations)
    )
