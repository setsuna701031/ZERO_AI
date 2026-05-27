from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_constitution_freeze import (
    RuntimeConstitutionState,
    RuntimeInvariantViolation,
    assert_authority_invariant,
    assert_evidence_invariant,
    assert_prediction_invariant,
    assert_recovery_invariant,
    assert_replay_invariant,
    assert_runtime_constitution_integrity,
    assert_simulation_invariant,
    assert_transaction_invariant,
    create_constitution_snapshot,
    normalize_constitution_snapshot,
)


@dataclass(frozen=True)
class RuntimeBurnInResult:
    ok: bool
    iterations: int
    replay_digest: str = ""
    transaction_digest: str = ""
    evidence_digest: str = ""
    constitution_snapshot: RuntimeConstitutionState | None = None
    violations: tuple[RuntimeInvariantViolation, ...] = ()
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["constitution_snapshot"] = (
            self.constitution_snapshot.to_dict() if self.constitution_snapshot else {}
        )
        payload["violations"] = [item.to_dict() for item in self.violations]
        return payload


def run_runtime_burnin(*, iterations: int = 3, inject_violation: bool = False) -> RuntimeBurnInResult:
    count = max(1, int(iterations or 1))
    checks: dict[str, Any] = {}
    violations: list[RuntimeInvariantViolation] = []

    authority = run_authority_burnin(iterations=count)
    replay = run_replay_burnin(iterations=count)
    transaction = run_transaction_burnin(iterations=count)
    recovery = run_recovery_burnin(iterations=count)
    evidence = run_evidence_burnin(iterations=count)
    repair = run_repair_loop_burnin(iterations=count)
    prediction = run_prediction_burnin(iterations=count)
    simulation = run_simulation_burnin(iterations=count)
    checks.update(
        {
            "authority": authority,
            "replay": replay,
            "transaction": transaction,
            "recovery": recovery,
            "evidence": evidence,
            "repair": repair,
            "prediction": prediction,
            "simulation": simulation,
        }
    )

    if inject_violation:
        try:
            assert_authority_invariant({}, surface="write_file", validation={"ok": True})
        except AssertionError:
            from core.runtime.runtime_constitution_freeze import list_runtime_invariant_violations

            violations.extend(list_runtime_invariant_violations(component="authority")[-1:])

    snapshot = create_constitution_snapshot(violations=violations)
    result = RuntimeBurnInResult(
        ok=not violations and all(_check_ok(item) for item in checks.values()),
        iterations=count,
        replay_digest=str(replay.get("digest") or ""),
        transaction_digest=str(transaction.get("digest") or ""),
        evidence_digest=str(evidence.get("digest") or ""),
        constitution_snapshot=snapshot,
        violations=tuple(violations),
        checks=checks,
    )
    try:
        from core.runtime.runtime_memory_engine import append_runtime_memory, memory_record_for_burnin

        append_runtime_memory(memory_record_for_burnin(result))
    except Exception:
        pass
    return result


def run_authority_burnin(*, iterations: int = 3) -> dict[str, Any]:
    decisions = []
    for index in range(max(1, iterations)):
        metadata = _authority("write_file")
        assert_authority_invariant(metadata, surface="write_file", validation={"ok": True})
        decisions.append({"index": index, "authority_source": metadata["authority_source"], "trace_id": metadata["trace_id"]})
    return {"ok": True, "authority_drift": False, "digest": _digest(decisions)}


def run_transaction_burnin(*, iterations: int = 3) -> dict[str, Any]:
    serializations = [_sample_transaction_serialization() for _ in range(max(1, iterations))]
    for item in serializations:
        assert_transaction_invariant(item)
    digest = _digest(serializations[0])
    return {
        "ok": all(_digest(item) == digest for item in serializations),
        "digest": digest,
        "lineage_corruption": False,
        "serializations": serializations,
    }


def run_replay_burnin(*, iterations: int = 3) -> dict[str, Any]:
    from core.runtime.runtime_replay_freeze import replay_read_only

    outputs = [
        replay_read_only(
            [
                {
                    "event_id": "burnin-replay",
                    "sequence": 1,
                    "surface": "replay_read",
                    "event_type": "replay_read",
                    "trace_id": "trace-burnin-replay",
                    "timestamp": f"2026-05-26T00:00:0{index}Z",
                }
            ]
        )
        for index in range(max(1, iterations))
    ]
    for first, second in zip(outputs, outputs[1:]):
        assert_replay_invariant(first, second=second)
    digest = str(outputs[0]["normalized_digest"])
    return {"ok": all(item["normalized_digest"] == digest for item in outputs), "digest": digest, "replay_drift": False}


def run_recovery_burnin(*, iterations: int = 3) -> dict[str, Any]:
    attempts = []
    for index in range(max(1, iterations)):
        attempt = {
            "recovery_attempt_id": f"runtime_recovery:burnin-{index}",
            "original_transaction_id": "runtime_tx:burnin-source",
            "state": "failed_terminal",
            "retry_count": 0,
            "max_retries": 1,
            "failure_result": {"reason": "burnin_terminal"},
            "state_history": ["proposed", "failed_terminal"],
        }
        assert_recovery_invariant(attempt)
        attempts.append(attempt)
    return {"ok": True, "digest": _digest(attempts[0]), "terminal_stable": True, "retry_bounded": True}


def run_evidence_burnin(*, iterations: int = 3) -> dict[str, Any]:
    from core.runtime.runtime_evidence_freeze import attach_authority_evidence, normalize_evidence_record

    records = [
        normalize_evidence_record(
            attach_authority_evidence(
                {"surface": "write_file", "authority_validation": {"ok": False, "reason": "missing_authority_metadata"}}
            )
        )
        for _ in range(max(1, iterations))
    ]
    for first, second in zip(records, records[1:]):
        assert_evidence_invariant(first, second=second)
    digest = _digest(records[0])
    return {"ok": all(_digest(item) == digest for item in records), "digest": digest, "lineage_corruption": False}


def run_repair_loop_burnin(*, iterations: int = 3) -> dict[str, Any]:
    from core.runtime.autonomous_repair_loop import (
        assert_repair_loop_bounded,
        assert_repair_loop_preserves_lineage,
        assert_repair_loop_terminal,
        normalize_repair_loop_result,
        run_autonomous_repair_loop,
    )

    normalized_results = []
    for _ in range(max(1, iterations)):
        result = run_autonomous_repair_loop(
            {
                "task_id": "task-repair-burnin",
                "step_id": "step-repair-burnin",
                "trace_id": "trace-repair-burnin",
                "failure_id": "failure-repair-burnin",
                "transaction_id": "runtime_tx:repair-burnin-source",
                "replay_run_id": "replay_run:repair-burnin",
                "recovery_attempt_id": "runtime_recovery:repair-burnin",
            },
            authority=_authority("repair_chain_apply"),
            strategy={"strategy_id": "burnin_strategy", "surface": "repair_chain_apply"},
            repair_payload={"surface": "repair_chain_apply", "affected_files": ["workspace/shared/repair-burnin.txt"]},
            verification={"ok": True, "verification_ok": True},
            max_attempts=1,
        )
        assert_repair_loop_terminal(result)
        assert_repair_loop_bounded(result)
        assert_repair_loop_preserves_lineage(result)
        normalized = _stable_repair_burnin_result(normalize_repair_loop_result(result))
        normalized_results.append(normalized)
    digest = _digest(normalized_results[0])
    return {
        "ok": all(_digest(item) == digest for item in normalized_results),
        "digest": digest,
        "terminal_stable": True,
        "anti_oscillation_stable": True,
        "source_transaction_immutable": True,
        "authority_drift": False,
    }


def run_prediction_burnin(*, iterations: int = 3, inject_authority_drift: bool = False) -> dict[str, Any]:
    from core.runtime.runtime_prediction_engine import (
        assert_prediction_non_authoritative,
        normalize_prediction_result,
        predict_mutation_impact,
    )

    outputs = []
    for _ in range(max(1, iterations)):
        prediction = predict_mutation_impact(
            {
                "task_id": "task-prediction-burnin",
                "step_id": "step-prediction-burnin",
                "trace_id": "trace-prediction-burnin",
                "source_transaction_id": "runtime_tx:prediction-burnin",
                "affected_files": ["workspace/shared/prediction-burnin.txt"],
            }
        )
        assert_prediction_non_authoritative(prediction)
        assert_prediction_invariant(prediction)
        outputs.append(normalize_prediction_result(prediction))
    if inject_authority_drift:
        try:
            assert_prediction_invariant({"prediction_id": "runtime_prediction:drift", "authoritative": True})
        except AssertionError:
            return {"ok": False, "authority_drift": True, "digest": _digest(outputs[0]), "prediction_digest_stable": True}
    digest = _digest(outputs[0])
    return {
        "ok": all(_digest(item) == digest for item in outputs),
        "digest": digest,
        "prediction_digest_stable": True,
        "authority_drift": False,
        "non_authoritative": True,
    }


def run_simulation_burnin(*, iterations: int = 3, inject_mutation_drift: bool = False) -> dict[str, Any]:
    from core.runtime.runtime_simulation_engine import (
        assert_simulation_read_only,
        normalize_simulation_result,
        simulate_runtime_step,
    )

    outputs = []
    for _ in range(max(1, iterations)):
        simulation = simulate_runtime_step(
            {
                "task_id": "task-simulation-burnin",
                "step_id": "step-simulation-burnin",
                "trace_id": "trace-simulation-burnin",
                "source_transaction_id": "runtime_tx:simulation-burnin",
                "simulated_steps": [{"step_id": "step-simulation-burnin", "surface": "write_file"}],
            }
        )
        assert_simulation_read_only(simulation)
        assert_simulation_invariant(simulation)
        outputs.append(normalize_simulation_result(simulation))
    if inject_mutation_drift:
        try:
            assert_simulation_invariant({"branch_id": "runtime_simulation_branch:drift", "mutation_allowed": True})
        except AssertionError:
            return {"ok": False, "mutation_drift": True, "digest": _digest(outputs[0]), "simulation_branch_stable": True}
    digest = _digest(outputs[0])
    return {
        "ok": all(_digest(item) == digest for item in outputs),
        "digest": digest,
        "simulation_branch_stable": True,
        "mutation_drift": False,
        "read_only": True,
    }


def _stable_repair_burnin_result(normalized: dict[str, Any]) -> dict[str, Any]:
    stable = copy.deepcopy(normalized)
    stable.pop("normalized_digest", None)
    stable["transaction_refs"] = ["<repair_transaction>"] if stable.get("transaction_refs") else []
    stable["evidence_refs"] = ["<repair_evidence>"] if stable.get("evidence_refs") else []
    stable["authority_refs"] = ["<authority_ref>"] if stable.get("authority_refs") else []
    stable["prediction_refs"] = ["<prediction_ref>"] if stable.get("prediction_refs") else []
    if isinstance(stable.get("repair_strategy"), dict) and stable["repair_strategy"].get("prediction_refs"):
        stable["repair_strategy"]["prediction_refs"] = ["<prediction_ref>"]
    for attempt in stable.get("attempts", []):
        if not isinstance(attempt, dict):
            continue
        attempt["attempt_id"] = "<repair_attempt>"
        if attempt.get("transaction_id"):
            attempt["transaction_id"] = "<repair_transaction>"
        if attempt.get("evidence_id"):
            attempt["evidence_id"] = "<repair_evidence>"
    return stable


def assert_burnin_stable(result: RuntimeBurnInResult | Mapping[str, Any]) -> bool:
    payload = result.to_dict() if isinstance(result, RuntimeBurnInResult) else copy.deepcopy(dict(result))
    if not payload.get("ok"):
        raise AssertionError("runtime burn-in detected invariant violation")
    snapshot = result.constitution_snapshot if isinstance(result, RuntimeBurnInResult) else payload.get("constitution_snapshot")
    assert_runtime_constitution_integrity(snapshot)
    normalized = normalize_constitution_snapshot(snapshot)
    if normalized.get("violations"):
        raise AssertionError("runtime burn-in emitted invariant violations")
    return True


def _sample_transaction_serialization() -> dict[str, Any]:
    return {
        "transaction_id": "runtime_tx:burnin",
        "task_id": "task-burnin",
        "step_id": "step-burnin",
        "trace_id": "trace-burnin",
        "authority_source": "execution_gateway",
        "surface": "write_file",
        "state": "committed",
        "affected_files": ["workspace/shared/burnin.txt"],
        "verification_result": {"ok": True, "verification_ok": True},
        "rollback_result": {},
        "state_history": ["proposed", "preflight", "approved", "applied", "verified", "committed"],
        "original_transaction_id": "",
    }


def _authority(surface: str) -> dict[str, Any]:
    return {
        "task_id": f"task-{surface}",
        "step_id": f"step-{surface}",
        "authority_source": "execution_gateway",
        "runtime_session": f"session-{surface}",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": f"trace-{surface}",
        "authority_status": "allowed",
        "action_type": "mutation",
    }


def _check_ok(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value.get("ok"))


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(value[key]) for key in sorted(value) if key not in {"created_at", "updated_at", "timestamp", "started_at", "finished_at"}}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    return copy.deepcopy(value)


def _digest(value: Any) -> str:
    payload = json.dumps(_normalize_value(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
