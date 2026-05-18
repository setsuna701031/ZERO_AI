from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEASE_PATH = REPO_ROOT / "core" / "runtime" / "runtime_execution_lease.py"

FORBIDDEN_IMPORTS = (
    "core.tasks.scheduler",
    "core.tasks.scheduler_core",
    "core.runtime.executor",
    "core.runtime.mutation_runtime_pipeline",
    "core.runtime.mutation_patch_apply",
    "core.runtime.runtime_recovery_coordinator",
    "core.runtime.runtime_recovery_policy",
    "core.runtime.runtime_replay_engine",
)

FORBIDDEN_METHODS = (
    "enqueue",
    "execute",
    "mutate",
    "recover",
    "replay",
)


def _lease_imports() -> list[str]:
    tree = ast.parse(LEASE_PATH.read_text(encoding="utf-8"), filename=str(LEASE_PATH))
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


def test_runtime_execution_lease_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_execution_lease")

    assert module.__all__ == ["RuntimeExecutionLease"]


def test_runtime_execution_lease_default_shape_does_not_grant_execution():
    module = importlib.import_module("core.runtime.runtime_execution_lease")

    lease = module.RuntimeExecutionLease(
        lease_id="lease-1",
        request_id="request-1",
        granted=False,
        trace_id="trace-1",
        metadata={"source": "test"},
    )

    assert lease.lease_id == "lease-1"
    assert lease.request_id == "request-1"
    assert lease.granted is False
    assert lease.trace_id == "trace-1"
    assert lease.status == "lease_not_granted"
    assert lease.reason == "execution_not_granted"
    assert lease.owner is None
    assert lease.metadata == {"source": "test"}


def test_runtime_execution_lease_does_not_import_scheduler_internals():
    imports = _lease_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_execution_lease must not import scheduler internals:\n"
        + "\n".join(violations)
    )


def test_runtime_execution_lease_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_execution_lease")
    public_names = {
        name
        for name in dir(module.RuntimeExecutionLease)
        if not name.startswith("_")
    }

    assert not (public_names & set(FORBIDDEN_METHODS))
