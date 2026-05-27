from __future__ import annotations

from core.runtime.runtime_burnin_runner import run_repair_loop_burnin
from core.runtime.autonomous_repair_loop import normalize_repair_loop_result, run_autonomous_repair_loop


def test_repair_loop_burn_in_stable() -> None:
    result = run_repair_loop_burnin(iterations=3)

    assert result["ok"] is True
    assert result["terminal_stable"] is True


def test_repeated_repair_loop_produces_stable_normalized_result() -> None:
    first = _stable_result()
    second = _stable_result()

    assert first["final_state"] == second["final_state"]
    assert first["diagnosis"] == second["diagnosis"]
    assert first["repair_strategy"] == second["repair_strategy"]


def test_evidence_digest_stable_across_repair_loop_burn_in() -> None:
    first = run_repair_loop_burnin(iterations=2)
    second = run_repair_loop_burnin(iterations=2)

    assert first["digest"] == second["digest"]


def test_repair_terminal_state_stable() -> None:
    result = run_repair_loop_burnin(iterations=3)

    assert result["terminal_stable"] is True


def test_anti_oscillation_remains_stable() -> None:
    result = run_repair_loop_burnin(iterations=3)

    assert result["anti_oscillation_stable"] is True


def test_source_transaction_immutable_across_burn_in() -> None:
    result = run_repair_loop_burnin(iterations=3)

    assert result["source_transaction_immutable"] is True


def test_no_authority_drift_during_repeated_repair_loop() -> None:
    first = run_repair_loop_burnin(iterations=3)
    second = run_repair_loop_burnin(iterations=3)

    assert first["authority_drift"] is False
    assert first["digest"] == second["digest"]


def _stable_result():
    result = run_autonomous_repair_loop(
        {
            "task_id": "task-repair-stable",
            "step_id": "step-repair-stable",
            "trace_id": "trace-repair-stable",
            "failure_id": "failure-repair-stable",
            "transaction_id": "runtime_tx:repair-stable-source",
        },
        authority={
            "task_id": "task-repair-stable",
            "step_id": "step-repair-stable",
            "authority_source": "execution_gateway",
            "runtime_session": "session-repair-stable",
            "approval_state": "approved",
            "policy_result": {"allowed": True, "decision": "allow"},
            "trace_id": "trace-repair-stable",
            "authority_status": "allowed",
            "execution_authority_endpoint": "step_executor",
            "action_type": "mutation",
        },
        strategy={"strategy_id": "stable_strategy", "surface": "repair_chain_apply"},
        verification={"ok": True, "verification_ok": True},
        max_attempts=1,
    )
    normalized = normalize_repair_loop_result(result)
    normalized["transaction_refs"] = ["<repair_transaction>"] if normalized.get("transaction_refs") else []
    normalized["evidence_refs"] = ["<repair_evidence>"] if normalized.get("evidence_refs") else []
    return normalized
