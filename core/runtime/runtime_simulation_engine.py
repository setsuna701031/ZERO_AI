from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping

from core.runtime.runtime_prediction_engine import (
    RuntimePredictionResult,
    RuntimeSimulationBranch,
    assert_simulation_does_not_mutate,
    assert_simulation_preserves_lineage,
    compare_simulation_branches,
    create_simulation_branch,
    normalize_simulation_snapshot,
    predict_mutation_impact,
    predict_repair_outcome,
    predict_replay_divergence,
    predict_rollback_risk,
)


class RuntimeSimulationMode(str, Enum):
    WHAT_IF = "what_if"
    REPAIR_STRATEGY = "repair_strategy"
    RECOVERY_PATH = "recovery_path"
    REPLAY_DIVERGENCE = "replay_divergence"
    TRANSACTION_LIFECYCLE = "transaction_lifecycle"
    COUNTERFACTUAL = "counterfactual"


@dataclass(frozen=True)
class RuntimeSimulationResult:
    simulation_id: str
    mode: RuntimeSimulationMode
    branch: RuntimeSimulationBranch
    prediction_refs: tuple[str, ...] = ()
    predicted_outcome: str = ""
    predicted_transactions: tuple[dict[str, Any], ...] = ()
    predicted_recovery_paths: tuple[dict[str, Any], ...] = ()
    predicted_repair_paths: tuple[dict[str, Any], ...] = ()
    evidence_refs: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    transaction_registry_before: tuple[str, ...] = ()
    transaction_registry_after: tuple[str, ...] = ()
    committed: bool = False
    mutation_allowed: bool = False
    authority_granted: bool = False
    authoritative: bool = False
    created_at: str = ""
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        payload["branch"] = self.branch.to_dict()
        for key in (
            "prediction_refs",
            "predicted_transactions",
            "predicted_recovery_paths",
            "predicted_repair_paths",
            "evidence_refs",
            "memory_refs",
            "transaction_registry_before",
            "transaction_registry_after",
        ):
            payload[key] = list(getattr(self, key))
        return payload


def simulate_runtime_step(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimeSimulationResult:
    payload = _context(context, overrides)
    before = _transaction_ids()
    prediction = predict_mutation_impact(payload)
    branch = create_simulation_branch(
        payload,
        simulation_mode=RuntimeSimulationMode.WHAT_IF.value,
        simulated_steps=payload.get("simulated_steps") or [{"step_id": payload.get("step_id", ""), "surface": payload.get("surface", "read_only")}],
        predictions=[prediction],
    )
    after = _transaction_ids()
    return _build_result(
        RuntimeSimulationMode.WHAT_IF,
        branch,
        predictions=[prediction],
        predicted_outcome="runtime step simulated read-only",
        before=before,
        after=after,
    )


def simulate_repair_strategy(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimeSimulationResult:
    payload = _context(context, overrides)
    before = _transaction_ids()
    prediction = predict_repair_outcome(payload)
    repair_path = {
        "repair_loop_id": payload.get("source_repair_loop_id") or payload.get("repair_loop_id") or "",
        "strategy_id": payload.get("strategy_id") or payload.get("repair_strategy") or "simulated_repair",
        "step_executor_invoked": False,
        "side_effects_invoked": False,
        "authority_granted": False,
    }
    branch = create_simulation_branch(
        {**payload, "predicted_repair_paths": [repair_path]},
        simulation_mode=RuntimeSimulationMode.REPAIR_STRATEGY.value,
        simulated_steps=payload.get("simulated_steps") or [{"step_id": payload.get("step_id", ""), "strategy": repair_path["strategy_id"]}],
        predictions=[prediction],
    )
    after = _transaction_ids()
    return _build_result(
        RuntimeSimulationMode.REPAIR_STRATEGY,
        branch,
        predictions=[prediction],
        predicted_outcome="repair strategy simulated without StepExecutor side effects",
        predicted_repair_paths=[repair_path],
        before=before,
        after=after,
    )


def simulate_recovery_path(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimeSimulationResult:
    payload = _context(context, overrides)
    before = _transaction_ids()
    prediction = predict_rollback_risk(payload)
    recovery_path = {
        "recovery_attempt_id": payload.get("source_recovery_attempt_id") or payload.get("recovery_attempt_id") or "",
        "source_transaction_id": payload.get("source_transaction_id") or payload.get("transaction_id") or "",
        "rollback_risk": prediction.rollback_risk.value,
        "authority_required": True,
        "authority_granted": False,
        "real_recovery": False,
    }
    branch = create_simulation_branch(
        {**payload, "predicted_recovery_paths": [recovery_path]},
        simulation_mode=RuntimeSimulationMode.RECOVERY_PATH.value,
        simulated_steps=payload.get("simulated_steps") or [{"step_id": payload.get("step_id", ""), "recovery": "simulated"}],
        predictions=[prediction],
    )
    after = _transaction_ids()
    return _build_result(
        RuntimeSimulationMode.RECOVERY_PATH,
        branch,
        predictions=[prediction],
        predicted_outcome="recovery path simulated without transaction",
        predicted_recovery_paths=[recovery_path],
        before=before,
        after=after,
    )


def simulate_replay_divergence(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimeSimulationResult:
    payload = _context(context, overrides)
    before = _transaction_ids()
    prediction = predict_replay_divergence(payload)
    branch = create_simulation_branch(
        payload,
        simulation_mode=RuntimeSimulationMode.REPLAY_DIVERGENCE.value,
        simulated_steps=payload.get("simulated_steps") or [{"replay_run_id": payload.get("source_replay_run_id") or payload.get("replay_run_id") or ""}],
        predictions=[prediction],
    )
    after = _transaction_ids()
    return _build_result(
        RuntimeSimulationMode.REPLAY_DIVERGENCE,
        branch,
        predictions=[prediction],
        predicted_outcome="replay divergence simulated read-only",
        before=before,
        after=after,
    )


def simulate_transaction_lifecycle(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimeSimulationResult:
    payload = _context(context, overrides)
    before = _transaction_ids()
    prediction = predict_mutation_impact(payload)
    lifecycle = [
        {"state": "proposed", "real_transaction": False},
        {"state": "preflight", "real_transaction": False},
        {"state": "approved", "approval_granted": False, "real_transaction": False},
        {"state": "applied", "mutation_allowed": False, "real_transaction": False},
        {"state": "verified", "real_transaction": False},
        {"state": "committed", "committed": False, "real_transaction": False},
    ]
    branch = create_simulation_branch(
        {**payload, "simulated_steps": lifecycle},
        simulation_mode=RuntimeSimulationMode.TRANSACTION_LIFECYCLE.value,
        predictions=[prediction],
    )
    after = _transaction_ids()
    return _build_result(
        RuntimeSimulationMode.TRANSACTION_LIFECYCLE,
        branch,
        predictions=[prediction],
        predicted_outcome="transaction lifecycle predicted without real transaction",
        before=before,
        after=after,
    )


def compare_runtime_simulations(*simulations: Any) -> dict[str, Any]:
    values = tuple(_result_from_any(item) for item in simulations if item is not None)
    snapshot = compare_simulation_branches(*(item.branch for item in values))
    normalized = normalize_simulation_snapshot(snapshot)
    return {
        "comparison_id": "runtime_simulation_comparison:" + _digest(normalized)[:16],
        "simulation_ids": [item.simulation_id for item in values],
        "snapshot": normalized,
        "deterministic": True,
        "normalized_digest": _digest(normalized),
    }


def assert_simulation_result_stable(first: RuntimeSimulationResult | Mapping[str, Any], second: RuntimeSimulationResult | Mapping[str, Any] | None = None) -> bool:
    first_payload = normalize_simulation_result(first)
    second_payload = normalize_simulation_result(second if second is not None else first)
    if _digest(first_payload) != _digest(second_payload):
        raise AssertionError("simulation result is not deterministic")
    return True


def assert_simulation_read_only(result: RuntimeSimulationResult | Mapping[str, Any]) -> bool:
    payload = normalize_simulation_result(result)
    if payload.get("committed") or payload.get("mutation_allowed") or payload.get("authority_granted") or payload.get("authoritative"):
        raise AssertionError("simulation result must remain read-only")
    if payload.get("transaction_registry_before") != payload.get("transaction_registry_after"):
        raise AssertionError("simulation changed transaction registry")
    assert_simulation_does_not_mutate(payload.get("branch") or {})
    assert_simulation_preserves_lineage(payload.get("branch") or {})
    return True


def normalize_simulation_result(result: RuntimeSimulationResult | Mapping[str, Any]) -> dict[str, Any]:
    payload = result.to_dict() if isinstance(result, RuntimeSimulationResult) else copy.deepcopy(dict(result))
    return _normalize_value(payload)


def _build_result(
    mode: RuntimeSimulationMode,
    branch: RuntimeSimulationBranch,
    *,
    predictions: Any = None,
    predicted_outcome: str,
    predicted_recovery_paths: Any = None,
    predicted_repair_paths: Any = None,
    before: tuple[str, ...],
    after: tuple[str, ...],
) -> RuntimeSimulationResult:
    prediction_values = _prediction_tuple(predictions)
    base = {
        "mode": mode.value,
        "branch": branch.to_dict(),
        "prediction_refs": [prediction.prediction_id for prediction in prediction_values],
        "predicted_outcome": predicted_outcome,
        "predicted_transactions": [copy.deepcopy(item) for item in branch.predicted_transactions],
        "predicted_recovery_paths": _normalize_value(predicted_recovery_paths or branch.predicted_recovery_paths),
        "predicted_repair_paths": _normalize_value(predicted_repair_paths or branch.predicted_repair_paths),
        "evidence_refs": list(branch.predicted_evidence_refs),
        "memory_refs": list(branch.memory_refs),
        "transaction_registry_before": list(before),
        "transaction_registry_after": list(after),
        "committed": False,
        "mutation_allowed": False,
        "authority_granted": False,
        "authoritative": False,
    }
    digest = _digest(base)
    result = RuntimeSimulationResult(
        simulation_id="runtime_simulation:" + digest[:16],
        mode=mode,
        branch=branch,
        prediction_refs=tuple(base["prediction_refs"]),
        predicted_outcome=predicted_outcome,
        predicted_transactions=tuple(base["predicted_transactions"]),
        predicted_recovery_paths=tuple(_mapping_tuple(base["predicted_recovery_paths"])),
        predicted_repair_paths=tuple(_mapping_tuple(base["predicted_repair_paths"])),
        evidence_refs=tuple(base["evidence_refs"]),
        memory_refs=tuple(base["memory_refs"]),
        transaction_registry_before=before,
        transaction_registry_after=after,
        created_at=_now(),
        normalized_digest=digest,
    )
    assert_simulation_read_only(result)
    return result


def _result_from_any(value: RuntimeSimulationResult | Mapping[str, Any]) -> RuntimeSimulationResult:
    if isinstance(value, RuntimeSimulationResult):
        return value
    payload = copy.deepcopy(dict(value))
    branch = payload.get("branch")
    if not isinstance(branch, RuntimeSimulationBranch):
        branch = create_simulation_branch(branch or {"trace_id": "simulation"})
    digest = str(payload.get("normalized_digest") or _digest(payload))
    return RuntimeSimulationResult(
        simulation_id=str(payload.get("simulation_id") or "runtime_simulation:" + digest[:16]),
        mode=RuntimeSimulationMode(str(payload.get("mode") or RuntimeSimulationMode.WHAT_IF.value)),
        branch=branch,
        prediction_refs=_text_tuple(payload.get("prediction_refs")),
        normalized_digest=digest,
    )


def _prediction_tuple(value: Any) -> tuple[RuntimePredictionResult, ...]:
    if value is None:
        return ()
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return tuple(item for item in values if isinstance(item, RuntimePredictionResult))


def _transaction_ids() -> tuple[str, ...]:
    try:
        from core.runtime.runtime_transaction_registry import list_transactions

        return tuple(sorted(item.transaction_id for item in list_transactions()))
    except Exception:
        return ()


def _context(context: Mapping[str, Any] | None, overrides: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(context or {}))
    payload.update(copy.deepcopy(dict(overrides or {})))
    return payload


def _mapping_tuple(value: Any) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return tuple(copy.deepcopy(dict(item)) if isinstance(item, Mapping) else {"value": copy.deepcopy(item)} for item in values)


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = list(value.values())
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return tuple(str(item) for item in values if str(item or "").strip())


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(value[key]) for key in sorted(value) if key not in {"created_at", "updated_at", "timestamp", "started_at", "finished_at"}}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return copy.deepcopy(value)


def _digest(value: Any) -> str:
    payload = json.dumps(_normalize_value(value), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
