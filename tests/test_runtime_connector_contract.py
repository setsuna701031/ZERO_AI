from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONNECTOR_PATH = REPO_ROOT / "core" / "runtime" / "runtime_connector.py"

FORBIDDEN_IMPORTS = (
    "core.tasks.scheduler",
    "core.tasks.scheduler_core",
)

FORBIDDEN_METHODS = (
    "enqueue",
    "execute",
    "mutate",
    "recover",
    "replay",
)


def _connector_imports() -> list[str]:
    tree = ast.parse(CONNECTOR_PATH.read_text(encoding="utf-8"), filename=str(CONNECTOR_PATH))
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


def test_runtime_connector_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_connector")

    assert module.__all__ == ["RuntimeConnector"]
    assert module.RuntimeConnector.runtime_connected is False


def test_runtime_connector_v0_builds_handoff_envelope_only():
    module = importlib.import_module("core.runtime.runtime_connector")
    connector = module.RuntimeConnector()
    request = {"task": {"title": "demo"}, "metadata": {"source": "test"}}

    result = connector.submit_request(
        surface="runtime_public_surface",
        operation="submit_runtime_task",
        request=request,
        details={"message": "not connected"},
    )

    assert result == {
        "status": "accepted_not_connected",
        "surface": "runtime_public_surface",
        "operation": "submit_runtime_task",
        "runtime_connected": False,
        "request": request,
        "details": {"message": "not connected"},
    }


def test_runtime_connector_calls_ownership_gate_before_handoff():
    module = importlib.import_module("core.runtime.runtime_connector")
    calls = []

    class RecordingGate:
        def evaluate_request(self, request_envelope):
            calls.append(request_envelope)

    connector = module.RuntimeConnector(ownership_gate=RecordingGate())
    result = connector.submit_request(
        surface="runtime_public_surface",
        operation="submit_runtime_task",
        request={"task": {"title": "demo"}, "metadata": {}},
        details={"message": "not connected"},
    )

    assert calls == [result]
    assert result["status"] == "accepted_not_connected"


def test_runtime_connector_does_not_import_scheduler_internals():
    imports = _connector_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_connector must not import scheduler internals:\n"
        + "\n".join(violations)
    )


def test_runtime_connector_v0_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_connector")
    public_names = {
        name
        for name in dir(module.RuntimeConnector)
        if not name.startswith("_")
    }

    assert public_names == {"runtime_connected", "submit_request"}
    assert not (public_names & set(FORBIDDEN_METHODS))
