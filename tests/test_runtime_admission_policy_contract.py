from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "core" / "runtime" / "runtime_admission_policy.py"

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


def _policy_imports() -> list[str]:
    tree = ast.parse(POLICY_PATH.read_text(encoding="utf-8"), filename=str(POLICY_PATH))
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


def test_runtime_admission_policy_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_admission_policy")

    assert module.__all__ == [
        "RuntimeAdmissionPolicy",
        "RuntimeAdmissionPolicyDecision",
    ]


def test_runtime_admission_policy_decision_shape():
    module = importlib.import_module("core.runtime.runtime_admission_policy")

    decision = module.RuntimeAdmissionPolicyDecision(
        allowed=False,
        rule="default_deny",
        reason="execution_not_granted",
        status="accepted_not_connected",
        risk_level="unknown",
        authority_scope="none",
        request_id="request-1",
        metadata={},
    )

    assert decision.allowed is False
    assert decision.rule == "default_deny"
    assert decision.reason == "execution_not_granted"
    assert decision.status == "accepted_not_connected"
    assert decision.risk_level == "unknown"
    assert decision.authority_scope == "none"
    assert decision.request_id == "request-1"
    assert decision.metadata == {}


def test_runtime_admission_policy_default_denies_execution():
    module = importlib.import_module("core.runtime.runtime_admission_policy")
    policy = module.RuntimeAdmissionPolicy()

    decision = policy.evaluate(
        {
            "surface": "runtime_public_surface",
            "operation": "submit_runtime_task",
            "request": {
                "task": {"title": "demo"},
                "metadata": {"request_id": "request-1", "source": "test"},
            },
        }
    )

    assert decision.allowed is False
    assert decision.rule == "default_deny"
    assert decision.reason == "execution_not_granted"
    assert decision.status == "accepted_not_connected"
    assert decision.risk_level == "unknown"
    assert decision.authority_scope == "none"
    assert decision.request_id == "request-1"
    assert decision.metadata == {}


def test_runtime_admission_policy_does_not_import_runtime_authority_internals():
    imports = _policy_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_admission_policy must not import runtime authority internals:\n"
        + "\n".join(violations)
    )


def test_runtime_admission_policy_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_admission_policy")
    public_names = {
        name
        for name in dir(module.RuntimeAdmissionPolicy)
        if not name.startswith("_")
    }

    assert public_names == {"evaluate"}
    assert not (public_names & set(FORBIDDEN_METHODS))
