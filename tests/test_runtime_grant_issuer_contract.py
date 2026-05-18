from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ISSUER_PATH = REPO_ROOT / "core" / "runtime" / "runtime_grant_issuer.py"
GATE_PATH = REPO_ROOT / "core" / "runtime" / "runtime_ownership_gate.py"

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


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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


def _call_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            calls.append(node.func.id)
            continue

        if isinstance(node.func, ast.Attribute):
            calls.append(node.func.attr)

    return calls


def test_runtime_grant_issuer_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_grant_issuer")

    assert module.__all__ == ["RuntimeGrantIssuer"]
    assert module.RuntimeGrantIssuer.issuer_id == "runtime_grant_issuer_v0"


def test_runtime_grant_issuer_v0_default_deny():
    issuer_module = importlib.import_module("core.runtime.runtime_grant_issuer")
    policy_module = importlib.import_module("core.runtime.runtime_admission_policy")
    trace_module = importlib.import_module("core.runtime.runtime_admission_trace")
    lease_module = importlib.import_module("core.runtime.runtime_execution_lease")
    issuer = issuer_module.RuntimeGrantIssuer()

    policy_decision = policy_module.RuntimeAdmissionPolicyDecision(
        allowed=False,
        rule="default_deny",
        reason="execution_not_granted",
        status="accepted_not_connected",
        risk_level="high",
        authority_scope="runtime",
        request_id="request-1",
        metadata={"policy": "ignored-by-v0"},
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

    grant = issuer.issue_grant(
        policy_decision,
        admission_trace,
        lease,
        metadata={"source": "test"},
    )

    assert grant.grant_id == "execution_grant:request-1"
    assert grant.request_id == lease.request_id
    assert grant.trace_id == admission_trace.trace_id
    assert grant.lease_id == lease.lease_id
    assert grant.granted is False
    assert grant.status == "grant_not_issued"
    assert grant.reason == "execution_not_granted"
    assert grant.authority_scope == "none"
    assert grant.risk_level == "unknown"
    assert grant.granted_by == "runtime_grant_issuer_v0"
    assert grant.expires_at is None
    assert grant.metadata == {
        "source": "test",
        "eligibility": {
            "eligible": False,
            "rule": "default_deny",
            "authority_scope": "none",
            "risk_level": "unknown",
        },
    }


def test_runtime_grant_issuer_does_not_grant_when_eligible_true():
    issuer_module = importlib.import_module("core.runtime.runtime_grant_issuer")
    policy_module = importlib.import_module("core.runtime.runtime_admission_policy")
    trace_module = importlib.import_module("core.runtime.runtime_admission_trace")
    lease_module = importlib.import_module("core.runtime.runtime_execution_lease")
    issuer = issuer_module.RuntimeGrantIssuer()

    policy_decision = policy_module.RuntimeAdmissionPolicyDecision(
        allowed=False,
        rule="default_deny",
        reason="execution_not_granted",
        status="accepted_not_connected",
        risk_level="unknown",
        authority_scope="none",
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
        risk_level="unknown",
        authority_scope="none",
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

    grant = issuer.issue_grant(
        policy_decision,
        admission_trace,
        lease,
        metadata={"authority_scope": "dry_run"},
    )

    assert grant.granted is False
    assert grant.status == "grant_not_issued"
    assert grant.reason == "execution_not_granted"
    assert grant.granted_by == "runtime_grant_issuer_v0"
    assert grant.metadata["eligibility"] == {
        "eligible": True,
        "rule": "scoped_low_risk",
        "authority_scope": "dry_run",
        "risk_level": "low",
    }


def test_runtime_grant_issuer_calls_eligibility_evaluator():
    issuer_module = importlib.import_module("core.runtime.runtime_grant_issuer")
    policy_module = importlib.import_module("core.runtime.runtime_admission_policy")
    trace_module = importlib.import_module("core.runtime.runtime_admission_trace")
    lease_module = importlib.import_module("core.runtime.runtime_execution_lease")
    eligibility_module = importlib.import_module("core.runtime.runtime_grant_eligibility")
    calls = []

    class RecordingEvaluator:
        def evaluate(self, policy_decision, admission_trace, lease, metadata=None):
            calls.append(
                {
                    "policy_decision": policy_decision,
                    "admission_trace": admission_trace,
                    "lease": lease,
                    "metadata": metadata,
                }
            )
            return eligibility_module.RuntimeGrantEligibility(
                eligible=False,
                rule="recorded_default_deny",
                reason="execution_not_granted",
                authority_scope="none",
                risk_level="unknown",
                request_id=lease.request_id,
                metadata={},
            )

    issuer = issuer_module.RuntimeGrantIssuer(
        eligibility_evaluator=RecordingEvaluator()
    )
    policy_decision = policy_module.RuntimeAdmissionPolicyDecision(
        allowed=False,
        rule="default_deny",
        reason="execution_not_granted",
        status="accepted_not_connected",
        risk_level="unknown",
        authority_scope="none",
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
        risk_level="unknown",
        authority_scope="none",
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

    grant = issuer.issue_grant(
        policy_decision,
        admission_trace,
        lease,
        metadata={"source": "test"},
    )

    assert len(calls) == 1
    assert calls[0]["policy_decision"] == policy_decision
    assert calls[0]["admission_trace"] == admission_trace
    assert calls[0]["lease"] == lease
    assert calls[0]["metadata"] == {"source": "test"}
    assert grant.granted is False
    assert grant.status == "grant_not_issued"
    assert grant.reason == "execution_not_granted"
    assert grant.granted_by == "runtime_grant_issuer_v0"
    assert grant.metadata["eligibility"] == {
        "eligible": False,
        "rule": "recorded_default_deny",
        "authority_scope": "none",
        "risk_level": "unknown",
    }


def test_runtime_grant_issuer_is_only_grant_creation_path():
    issuer_calls = _call_names(ISSUER_PATH)
    gate_calls = _call_names(GATE_PATH)

    assert issuer_calls.count("RuntimeExecutionGrant") == 1
    assert "RuntimeExecutionGrant" not in gate_calls
    assert "issue_grant" in gate_calls


def test_runtime_grant_issuer_does_not_import_runtime_internals():
    imports = _imports(ISSUER_PATH)
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_grant_issuer must not import scheduler/runtime internals:\n"
        + "\n".join(violations)
    )


def test_runtime_grant_issuer_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_grant_issuer")
    public_names = {
        name
        for name in dir(module.RuntimeGrantIssuer)
        if not name.startswith("_")
    }

    assert public_names == {"issuer_id", "issue_grant"}
    assert not (public_names & set(FORBIDDEN_METHODS))
