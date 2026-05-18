from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ELIGIBILITY_PATH = REPO_ROOT / "core" / "runtime" / "runtime_grant_eligibility.py"

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


def _eligibility_imports() -> list[str]:
    tree = ast.parse(
        ELIGIBILITY_PATH.read_text(encoding="utf-8"),
        filename=str(ELIGIBILITY_PATH),
    )
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


def test_runtime_grant_eligibility_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_grant_eligibility")

    assert module.__all__ == [
        "RuntimeGrantEligibility",
        "RuntimeGrantEligibilityEvaluator",
    ]


def test_runtime_grant_eligibility_evaluator_default_deny():
    eligibility_module = importlib.import_module("core.runtime.runtime_grant_eligibility")
    policy_module = importlib.import_module("core.runtime.runtime_admission_policy")
    trace_module = importlib.import_module("core.runtime.runtime_admission_trace")
    lease_module = importlib.import_module("core.runtime.runtime_execution_lease")
    evaluator = eligibility_module.RuntimeGrantEligibilityEvaluator()

    policy_decision = policy_module.RuntimeAdmissionPolicyDecision(
        allowed=False,
        rule="default_deny",
        reason="execution_not_granted",
        status="accepted_not_connected",
        risk_level="high",
        authority_scope="runtime",
        request_id="request-1",
        metadata={},
    )
    admission_trace = trace_module.RuntimeAdmissionTrace(
        trace_id="trace-1",
        request_id="request-1",
        stage="ownership_gate",
        decision="denied",
        status="accepted_not_connected",
        reason="execution_not_granted",
        policy_rule="default_deny",
        risk_level="high",
        authority_scope="runtime",
        lease_id="lease-1",
        grant_id=None,
        metadata={},
    )
    lease = lease_module.RuntimeExecutionLease(
        lease_id="lease-1",
        request_id="request-1",
        granted=False,
        trace_id="trace-1",
    )

    eligibility = evaluator.evaluate(
        policy_decision,
        admission_trace,
        lease,
        metadata={"source": "test"},
    )

    assert eligibility.eligible is False
    assert eligibility.rule == "default_deny"
    assert eligibility.reason == "execution_not_granted"
    assert eligibility.authority_scope == "none"
    assert eligibility.risk_level == "unknown"
    assert eligibility.request_id == "request-1"
    assert eligibility.metadata == {"source": "test"}


def test_runtime_grant_eligibility_does_not_import_runtime_internals():
    imports = _eligibility_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_grant_eligibility must not import scheduler/runtime internals:\n"
        + "\n".join(violations)
    )


def test_runtime_grant_eligibility_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_grant_eligibility")
    public_names = {
        name
        for name in dir(module.RuntimeGrantEligibilityEvaluator)
        if not name.startswith("_")
    }

    assert public_names == {"evaluate"}
    assert not (public_names & set(FORBIDDEN_METHODS))
