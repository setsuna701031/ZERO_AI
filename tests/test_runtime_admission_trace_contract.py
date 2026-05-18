from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = REPO_ROOT / "core" / "runtime" / "runtime_admission_trace.py"

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


def _trace_imports() -> list[str]:
    tree = ast.parse(TRACE_PATH.read_text(encoding="utf-8"), filename=str(TRACE_PATH))
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


def test_runtime_admission_trace_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_admission_trace")

    assert module.__all__ == ["RuntimeAdmissionTrace"]


def test_runtime_admission_trace_shape():
    module = importlib.import_module("core.runtime.runtime_admission_trace")

    trace = module.RuntimeAdmissionTrace(
        trace_id="trace-1",
        request_id="request-1",
        stage="ownership_gate",
        decision="denied",
        status="accepted_not_connected",
        reason="execution_not_granted",
        policy_rule="default_deny",
        risk_level="unknown",
        authority_scope="none",
        lease_id=None,
        grant_id="grant-1",
        metadata={"source": "test"},
    )

    assert trace.trace_id == "trace-1"
    assert trace.request_id == "request-1"
    assert trace.stage == "ownership_gate"
    assert trace.decision == "denied"
    assert trace.status == "accepted_not_connected"
    assert trace.reason == "execution_not_granted"
    assert trace.policy_rule == "default_deny"
    assert trace.risk_level == "unknown"
    assert trace.authority_scope == "none"
    assert trace.lease_id is None
    assert trace.grant_id == "grant-1"
    assert trace.metadata == {"source": "test"}


def test_runtime_admission_trace_does_not_import_scheduler_internals():
    imports = _trace_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_admission_trace must not import scheduler internals:\n"
        + "\n".join(violations)
    )


def test_runtime_admission_trace_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_admission_trace")
    public_names = {
        name
        for name in dir(module.RuntimeAdmissionTrace)
        if not name.startswith("_")
    }

    assert not (public_names & set(FORBIDDEN_METHODS))
