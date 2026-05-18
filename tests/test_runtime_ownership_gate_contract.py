from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
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


def _gate_imports() -> list[str]:
    tree = ast.parse(GATE_PATH.read_text(encoding="utf-8"), filename=str(GATE_PATH))
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


def test_runtime_ownership_gate_imports_cleanly():
    module = importlib.import_module("core.runtime.runtime_ownership_gate")

    assert module.__all__ == ["RuntimeOwnershipDecision", "RuntimeOwnershipGate"]


def test_runtime_ownership_decision_shape():
    module = importlib.import_module("core.runtime.runtime_ownership_gate")
    policy_module = importlib.import_module("core.runtime.runtime_admission_policy")
    lease_module = importlib.import_module("core.runtime.runtime_execution_lease")
    trace_module = importlib.import_module("core.runtime.runtime_admission_trace")
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
    lease = lease_module.RuntimeExecutionLease(
        lease_id="lease-1",
        request_id="request-1",
        granted=False,
        trace_id="trace-1",
        metadata={"source": "test"},
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
        metadata={"source": "test"},
    )

    decision = module.RuntimeOwnershipDecision(
        accepted=False,
        status="accepted_not_connected",
        reason="execution_not_granted",
        request_id="request-1",
        policy_decision=policy_decision,
        lease=lease,
        admission_trace=admission_trace,
        metadata={"source": "test"},
    )

    assert decision.accepted is False
    assert decision.status == "accepted_not_connected"
    assert decision.reason == "execution_not_granted"
    assert decision.request_id == "request-1"
    assert decision.policy_decision == policy_decision
    assert decision.lease == lease
    assert decision.admission_trace == admission_trace
    assert decision.metadata == {"source": "test"}


def test_runtime_ownership_gate_default_decision_does_not_grant_execution():
    module = importlib.import_module("core.runtime.runtime_ownership_gate")
    gate = module.RuntimeOwnershipGate()

    decision = gate.evaluate_request(
        {
            "surface": "runtime_public_surface",
            "operation": "submit_runtime_task",
            "request": {
                "task": {"title": "demo"},
                "metadata": {"request_id": "request-1", "source": "test"},
            },
        }
    )

    assert decision.accepted is False
    assert decision.status == "accepted_not_connected"
    assert decision.reason == "execution_not_granted"
    assert decision.request_id == "request-1"
    assert decision.lease.granted is False
    assert decision.lease.status == "lease_not_granted"
    assert decision.lease.reason == "execution_not_granted"
    assert decision.lease.request_id == "request-1"
    assert decision.lease.trace_id == decision.admission_trace.trace_id
    assert decision.admission_trace.request_id == "request-1"
    assert decision.admission_trace.decision == "denied"
    assert decision.admission_trace.stage == "ownership_gate"
    assert decision.admission_trace.policy_rule == "default_deny"
    assert decision.admission_trace.risk_level == "unknown"
    assert decision.admission_trace.authority_scope == "none"
    assert decision.admission_trace.lease_id is None
    assert decision.admission_trace.trace_id == "admission_trace:request-1"
    assert decision.policy_decision.rule == "default_deny"
    assert decision.metadata == {}


def test_runtime_ownership_gate_calls_admission_policy_first():
    module = importlib.import_module("core.runtime.runtime_ownership_gate")
    policy_module = importlib.import_module("core.runtime.runtime_admission_policy")
    calls = []

    class RecordingPolicy:
        def evaluate(self, request_envelope):
            calls.append(request_envelope)
            return policy_module.RuntimeAdmissionPolicyDecision(
                allowed=False,
                rule="default_deny",
                reason="execution_not_granted",
                status="accepted_not_connected",
                risk_level="unknown",
                authority_scope="none",
                request_id="request-1",
                metadata={},
            )

    gate = module.RuntimeOwnershipGate(admission_policy=RecordingPolicy())
    envelope = {
        "surface": "runtime_public_surface",
        "operation": "submit_runtime_task",
        "request": {
            "task": {"title": "demo"},
            "metadata": {"request_id": "request-1", "source": "test"},
        },
    }

    decision = gate.evaluate_request(envelope)

    assert calls == [envelope]
    assert decision.accepted is False
    assert decision.policy_decision.rule == "default_deny"


def test_runtime_ownership_gate_does_not_import_scheduler_internals():
    imports = _gate_imports()
    violations = [
        module
        for module in imports
        if any(
            module == forbidden or module.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_IMPORTS
        )
    ]

    assert not violations, (
        "runtime_ownership_gate must not import scheduler internals:\n"
        + "\n".join(violations)
    )


def test_runtime_ownership_gate_has_no_runtime_authority_methods():
    module = importlib.import_module("core.runtime.runtime_ownership_gate")
    public_names = {
        name
        for name in dir(module.RuntimeOwnershipGate)
        if not name.startswith("_")
    }

    assert public_names == {"evaluate_request"}
    assert not (public_names & set(FORBIDDEN_METHODS))
