from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping


class RuntimePredictionKind(str, Enum):
    MUTATION_IMPACT = "mutation_impact"
    REPAIR_OUTCOME = "repair_outcome"
    ROLLBACK_RISK = "rollback_risk"
    REPLAY_DIVERGENCE = "replay_divergence"
    STABILIZATION_PROBABILITY = "stabilization_probability"


class RuntimePredictionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RuntimePredictionResult:
    prediction_id: str
    kind: RuntimePredictionKind
    task_id: str = ""
    step_id: str = ""
    trace_id: str = ""
    source_transaction_id: str = ""
    source_replay_run_id: str = ""
    source_recovery_attempt_id: str = ""
    source_repair_loop_id: str = ""
    source_memory_ids: tuple[str, ...] = ()
    predicted_risk: RuntimePredictionRisk = RuntimePredictionRisk.UNKNOWN
    confidence: float = 0.0
    predicted_outcome: str = ""
    predicted_side_effects: tuple[str, ...] = ()
    rollback_risk: RuntimePredictionRisk = RuntimePredictionRisk.UNKNOWN
    replay_divergence_risk: RuntimePredictionRisk = RuntimePredictionRisk.UNKNOWN
    stabilization_probability: float = 0.0
    reasoning_summary: str = ""
    evidence_refs: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    invariant_refs: tuple[str, ...] = ()
    created_at: str = ""
    normalized_digest: str = ""
    authoritative: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["predicted_risk"] = self.predicted_risk.value
        payload["rollback_risk"] = self.rollback_risk.value
        payload["replay_divergence_risk"] = self.replay_divergence_risk.value
        for key in (
            "source_memory_ids",
            "predicted_side_effects",
            "evidence_refs",
            "memory_refs",
            "invariant_refs",
        ):
            payload[key] = list(getattr(self, key))
        return payload


@dataclass(frozen=True)
class RuntimeSimulationBranch:
    branch_id: str
    parent_trace_id: str = ""
    simulation_mode: str = "what_if"
    simulated_steps: tuple[dict[str, Any], ...] = ()
    predicted_transactions: tuple[dict[str, Any], ...] = ()
    predicted_recovery_paths: tuple[dict[str, Any], ...] = ()
    predicted_repair_paths: tuple[dict[str, Any], ...] = ()
    predicted_evidence_refs: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    committed: bool = False
    mutation_allowed: bool = False
    authority_granted: bool = False
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "simulated_steps",
            "predicted_transactions",
            "predicted_recovery_paths",
            "predicted_repair_paths",
            "predicted_evidence_refs",
            "memory_refs",
        ):
            payload[key] = list(getattr(self, key))
        return payload


@dataclass(frozen=True)
class RuntimeSimulationSnapshot:
    snapshot_id: str
    branches: tuple[RuntimeSimulationBranch, ...]
    comparison: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    memory_refs: tuple[str, ...] = ()
    created_at: str = ""
    normalized_digest: str = ""
    authoritative: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["branches"] = [branch.to_dict() for branch in self.branches]
        payload["evidence_refs"] = list(self.evidence_refs)
        payload["memory_refs"] = list(self.memory_refs)
        return payload


def predict_mutation_impact(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimePredictionResult:
    payload = _context(context, overrides)
    memory = _memory_refs(payload, kinds=("failure_pattern", "repair_history", "stabilization_history"))
    side_effects = _side_effects(payload)
    risk = _risk_for_counts(len(side_effects), len(memory["failure"]))
    confidence = _confidence(memory, base=0.58)
    return _build_prediction(
        RuntimePredictionKind.MUTATION_IMPACT,
        payload,
        predicted_risk=risk,
        confidence=confidence,
        predicted_outcome="mutation impact predicted without execution",
        predicted_side_effects=side_effects,
        rollback_risk=_risk_for_counts(len(side_effects), len(memory["rollback"])),
        replay_divergence_risk=_risk_for_counts(len(memory["replay"]), len(side_effects)),
        stabilization_probability=_bounded(0.72 - (0.12 * len(side_effects)) + (0.04 * len(memory["stabilization"]))),
        reasoning_summary="read-only mutation impact prediction",
        memory_refs=memory["all"],
    )


def predict_repair_outcome(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimePredictionResult:
    payload = _context(context, overrides)
    memory = _memory_refs(payload, kinds=("repair_history", "stabilization_history", "failure_pattern"))
    stabilization = len(memory["stabilization"])
    failures = len(memory["failure"])
    probability = _bounded(0.54 + 0.12 * stabilization - 0.08 * failures)
    risk = RuntimePredictionRisk.LOW if probability >= 0.7 else RuntimePredictionRisk.MEDIUM if probability >= 0.4 else RuntimePredictionRisk.HIGH
    return _build_prediction(
        RuntimePredictionKind.REPAIR_OUTCOME,
        payload,
        predicted_risk=risk,
        confidence=_confidence(memory, base=0.62),
        predicted_outcome="repair likely stabilizes" if probability >= 0.5 else "repair may require review",
        predicted_side_effects=_side_effects(payload),
        rollback_risk=RuntimePredictionRisk.LOW if probability >= 0.7 else RuntimePredictionRisk.MEDIUM,
        replay_divergence_risk=_risk_for_counts(len(memory["replay"]), failures),
        stabilization_probability=probability,
        reasoning_summary="memory-assisted repair outcome prediction",
        memory_refs=memory["all"],
    )


def predict_rollback_risk(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimePredictionResult:
    payload = _context(context, overrides)
    memory = _memory_refs(payload, kinds=("transaction_history", "recovery_terminal", "failure_pattern", "repair_history"))
    risk = _risk_for_counts(len(memory["rollback"]) + len(memory["failure"]), len(_side_effects(payload)))
    return _build_prediction(
        RuntimePredictionKind.ROLLBACK_RISK,
        payload,
        predicted_risk=risk,
        confidence=_confidence(memory, base=0.6),
        predicted_outcome="rollback risk estimated",
        predicted_side_effects=(),
        rollback_risk=risk,
        replay_divergence_risk=_risk_for_counts(len(memory["replay"]), 0),
        stabilization_probability=_bounded(0.64 - 0.1 * len(memory["failure"])),
        reasoning_summary="rollback lineage prediction",
        memory_refs=memory["all"],
    )


def predict_replay_divergence(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimePredictionResult:
    payload = _context(context, overrides)
    memory = _memory_refs(payload, kinds=("replay_window", "failure_pattern", "repair_history"))
    divergence_risk = _risk_for_counts(len(memory["failure"]), len(memory["replay"]))
    return _build_prediction(
        RuntimePredictionKind.REPLAY_DIVERGENCE,
        payload,
        predicted_risk=divergence_risk,
        confidence=_confidence(memory, base=0.64),
        predicted_outcome="replay divergence predicted from read-only window",
        predicted_side_effects=(),
        rollback_risk=_risk_for_counts(len(memory["rollback"]), 0),
        replay_divergence_risk=divergence_risk,
        stabilization_probability=_bounded(0.68 - 0.08 * len(memory["failure"]) + 0.03 * len(memory["replay"])),
        reasoning_summary="read-only replay window divergence prediction",
        memory_refs=memory["all"],
    )


def predict_stabilization_probability(context: Mapping[str, Any] | None = None, **overrides: Any) -> RuntimePredictionResult:
    payload = _context(context, overrides)
    memory = _memory_refs(payload, kinds=("stabilization_history", "repair_history", "failure_pattern"))
    probability = _bounded(0.5 + 0.16 * len(memory["stabilization"]) + 0.04 * len(memory["repair"]) - 0.12 * len(memory["failure"]))
    risk = RuntimePredictionRisk.LOW if probability >= 0.75 else RuntimePredictionRisk.MEDIUM if probability >= 0.45 else RuntimePredictionRisk.HIGH
    return _build_prediction(
        RuntimePredictionKind.STABILIZATION_PROBABILITY,
        payload,
        predicted_risk=risk,
        confidence=_confidence(memory, base=0.57),
        predicted_outcome="stabilization probability estimated",
        predicted_side_effects=(),
        rollback_risk=_risk_for_counts(len(memory["rollback"]), len(memory["failure"])),
        replay_divergence_risk=_risk_for_counts(len(memory["replay"]), len(memory["failure"])),
        stabilization_probability=probability,
        reasoning_summary="memory-assisted stabilization estimate",
        memory_refs=memory["all"],
    )


def create_simulation_branch(
    context: Mapping[str, Any] | None = None,
    *,
    simulation_mode: str = "what_if",
    simulated_steps: Any = None,
    predictions: Any = None,
    **overrides: Any,
) -> RuntimeSimulationBranch:
    payload = _context(context, overrides)
    steps = tuple(_mapping_tuple(simulated_steps if simulated_steps is not None else payload.get("simulated_steps")))
    prediction_values = _prediction_tuple(predictions)
    predicted_transactions = tuple(
        {
            "transaction_id": _stable_ref("predicted_transaction", payload, index, step),
            "source_transaction_id": payload.get("source_transaction_id") or payload.get("transaction_id") or "",
            "real_transaction": False,
            "committed": False,
            "mutation_allowed": False,
            "step": _normalize_value(step),
        }
        for index, step in enumerate(steps or ({"step_id": payload.get("step_id", "")},))
    )
    memory_refs = _append_unique(payload.get("memory_refs"), *(ref for prediction in prediction_values for ref in prediction.memory_refs))
    evidence_refs = _append_unique(
        payload.get("evidence_refs"),
        *(_stable_ref("predicted_evidence", payload, index, step) for index, step in enumerate(steps or ({},))),
        *(ref for prediction in prediction_values for ref in prediction.evidence_refs),
    )
    base = {
        "parent_trace_id": str(payload.get("parent_trace_id") or payload.get("trace_id") or ""),
        "simulation_mode": str(simulation_mode or payload.get("simulation_mode") or "what_if"),
        "simulated_steps": [_normalize_value(step) for step in steps],
        "predicted_transactions": [_normalize_value(item) for item in predicted_transactions],
        "predicted_recovery_paths": _normalize_value(payload.get("predicted_recovery_paths") or []),
        "predicted_repair_paths": _normalize_value(payload.get("predicted_repair_paths") or []),
        "predicted_evidence_refs": list(evidence_refs),
        "memory_refs": list(memory_refs),
        "committed": False,
        "mutation_allowed": False,
        "authority_granted": False,
    }
    digest = _digest(base)
    branch = RuntimeSimulationBranch(
        branch_id="runtime_simulation_branch:" + digest[:16],
        parent_trace_id=base["parent_trace_id"],
        simulation_mode=base["simulation_mode"],
        simulated_steps=tuple(copy.deepcopy(step) for step in base["simulated_steps"]),
        predicted_transactions=predicted_transactions,
        predicted_recovery_paths=tuple(_mapping_tuple(base["predicted_recovery_paths"])),
        predicted_repair_paths=tuple(_mapping_tuple(base["predicted_repair_paths"])),
        predicted_evidence_refs=tuple(base["predicted_evidence_refs"]),
        memory_refs=tuple(base["memory_refs"]),
        normalized_digest=digest,
    )
    assert_simulation_does_not_mutate(branch)
    assert_simulation_preserves_lineage(branch)
    return branch


def compare_simulation_branches(*branches: Any) -> RuntimeSimulationSnapshot:
    values = tuple(sorted((_branch_from_any(branch) for branch in branches if branch is not None), key=lambda item: item.branch_id))
    comparison = {
        "branch_ids": [branch.branch_id for branch in values],
        "branch_count": len(values),
        "digests": [branch.normalized_digest for branch in values],
        "committed": [branch.committed for branch in values],
        "mutation_allowed": [branch.mutation_allowed for branch in values],
    }
    evidence_refs = tuple(dict.fromkeys(ref for branch in values for ref in branch.predicted_evidence_refs))
    memory_refs = tuple(dict.fromkeys(ref for branch in values for ref in branch.memory_refs))
    digest_payload = {"branches": [branch.to_dict() for branch in values], "comparison": comparison, "evidence_refs": list(evidence_refs), "memory_refs": list(memory_refs), "authoritative": False}
    digest = _digest(digest_payload)
    return RuntimeSimulationSnapshot(
        snapshot_id="runtime_simulation_snapshot:" + digest[:16],
        branches=values,
        comparison=comparison,
        evidence_refs=evidence_refs,
        memory_refs=memory_refs,
        created_at=_now(),
        normalized_digest=digest,
        authoritative=False,
    )


def normalize_prediction_result(result: RuntimePredictionResult | Mapping[str, Any]) -> dict[str, Any]:
    payload = result.to_dict() if isinstance(result, RuntimePredictionResult) else copy.deepcopy(dict(result))
    return _normalize_value(payload)


def normalize_simulation_snapshot(snapshot: RuntimeSimulationSnapshot | RuntimeSimulationBranch | Mapping[str, Any]) -> dict[str, Any]:
    payload = snapshot.to_dict() if hasattr(snapshot, "to_dict") else copy.deepcopy(dict(snapshot))
    return _normalize_value(payload)


def assert_prediction_non_authoritative(result: RuntimePredictionResult | Mapping[str, Any]) -> bool:
    payload = normalize_prediction_result(result)
    if payload.get("authoritative") or payload.get("authority_granted"):
        raise AssertionError("prediction cannot grant authority")
    if payload.get("approval_state") in {"approved", "allowed"} or payload.get("approved") or payload.get("approval_granted"):
        raise AssertionError("prediction result cannot bypass approval")
    if payload.get("creates_transaction") or payload.get("transaction_created"):
        raise AssertionError("prediction cannot create transaction")
    return True


def assert_simulation_does_not_mutate(branch: RuntimeSimulationBranch | Mapping[str, Any]) -> bool:
    payload = normalize_simulation_snapshot(branch)
    if payload.get("committed"):
        raise AssertionError("simulation branch cannot commit")
    if payload.get("mutation_allowed") or payload.get("authority_granted"):
        raise AssertionError("simulation cannot mutate or grant authority")
    for tx in payload.get("predicted_transactions") or []:
        if tx.get("real_transaction") or tx.get("committed") or tx.get("transaction_created"):
            raise AssertionError("simulation cannot create real transaction")
    return True


def assert_simulation_preserves_lineage(branch: RuntimeSimulationBranch | RuntimeSimulationSnapshot | Mapping[str, Any]) -> bool:
    payload = normalize_simulation_snapshot(branch)
    if payload.get("branches"):
        for item in payload["branches"]:
            assert_simulation_preserves_lineage(item)
        return True
    if not (payload.get("parent_trace_id") or payload.get("memory_refs") or payload.get("predicted_evidence_refs")):
        raise AssertionError("simulation source lineage immutable")
    return True


def _build_prediction(
    kind: RuntimePredictionKind,
    payload: Mapping[str, Any],
    *,
    predicted_risk: RuntimePredictionRisk,
    confidence: float,
    predicted_outcome: str,
    predicted_side_effects: Any,
    rollback_risk: RuntimePredictionRisk,
    replay_divergence_risk: RuntimePredictionRisk,
    stabilization_probability: float,
    reasoning_summary: str,
    memory_refs: Any,
) -> RuntimePredictionResult:
    source_memory_ids = _append_unique(payload.get("source_memory_ids"), memory_refs)
    evidence_refs = _append_unique(payload.get("evidence_refs"), _stable_ref("prediction_evidence", kind.value, payload, source_memory_ids))
    invariant_refs = _append_unique(
        payload.get("invariant_refs"),
        "prediction.cannot_grant_authority",
        "prediction.result_cannot_bypass_approval",
        "prediction.source_lineage_immutable",
    )
    base = {
        "kind": kind.value,
        "task_id": str(payload.get("task_id") or ""),
        "step_id": str(payload.get("step_id") or ""),
        "trace_id": str(payload.get("trace_id") or ""),
        "source_transaction_id": str(payload.get("source_transaction_id") or payload.get("transaction_id") or ""),
        "source_replay_run_id": str(payload.get("source_replay_run_id") or payload.get("replay_run_id") or ""),
        "source_recovery_attempt_id": str(payload.get("source_recovery_attempt_id") or payload.get("recovery_attempt_id") or ""),
        "source_repair_loop_id": str(payload.get("source_repair_loop_id") or payload.get("repair_loop_id") or ""),
        "source_memory_ids": list(source_memory_ids),
        "predicted_risk": predicted_risk.value,
        "confidence": _bounded(confidence),
        "predicted_outcome": predicted_outcome,
        "predicted_side_effects": list(_text_tuple(predicted_side_effects)),
        "rollback_risk": rollback_risk.value,
        "replay_divergence_risk": replay_divergence_risk.value,
        "stabilization_probability": _bounded(stabilization_probability),
        "reasoning_summary": reasoning_summary,
        "evidence_refs": list(evidence_refs),
        "memory_refs": list(source_memory_ids),
        "invariant_refs": list(invariant_refs),
        "authoritative": False,
    }
    digest = _digest(base)
    result = RuntimePredictionResult(
        prediction_id="runtime_prediction:" + digest[:16],
        kind=kind,
        task_id=base["task_id"],
        step_id=base["step_id"],
        trace_id=base["trace_id"],
        source_transaction_id=base["source_transaction_id"],
        source_replay_run_id=base["source_replay_run_id"],
        source_recovery_attempt_id=base["source_recovery_attempt_id"],
        source_repair_loop_id=base["source_repair_loop_id"],
        source_memory_ids=tuple(base["source_memory_ids"]),
        predicted_risk=predicted_risk,
        confidence=base["confidence"],
        predicted_outcome=predicted_outcome,
        predicted_side_effects=tuple(base["predicted_side_effects"]),
        rollback_risk=rollback_risk,
        replay_divergence_risk=replay_divergence_risk,
        stabilization_probability=base["stabilization_probability"],
        reasoning_summary=reasoning_summary,
        evidence_refs=tuple(base["evidence_refs"]),
        memory_refs=tuple(base["memory_refs"]),
        invariant_refs=tuple(base["invariant_refs"]),
        created_at=_now(),
        normalized_digest=digest,
        authoritative=False,
    )
    assert_prediction_non_authoritative(result)
    return result


def _memory_refs(payload: Mapping[str, Any], *, kinds: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {"all": [], "failure": [], "repair": [], "stabilization": [], "replay": [], "rollback": []}
    try:
        from core.runtime.runtime_memory_engine import query_runtime_memory
    except Exception:
        return {key: tuple(value) for key, value in result.items()}

    criteria = {
        "trace_id": payload.get("trace_id") or payload.get("parent_trace_id") or "",
        "transaction_id": payload.get("source_transaction_id") or payload.get("transaction_id") or "",
        "replay_run_id": payload.get("source_replay_run_id") or payload.get("replay_run_id") or "",
        "recovery_attempt_id": payload.get("source_recovery_attempt_id") or payload.get("recovery_attempt_id") or "",
        "repair_loop_id": payload.get("source_repair_loop_id") or payload.get("repair_loop_id") or "",
        "failure_signature": payload.get("failure_signature") or payload.get("failure_id") or "",
        "repair_strategy": payload.get("repair_strategy") or payload.get("strategy_id") or "",
    }
    seen: dict[str, Any] = {}
    for kind in kinds:
        queries = [{"kind": kind}]
        queries.extend({"kind": kind, key: value} for key, value in criteria.items() if value)
        for query in queries:
            for record in query_runtime_memory(**query):
                seen[record.memory_id] = record
    for record in sorted(seen.values(), key=lambda item: item.memory_id):
        result["all"].append(record.memory_id)
        kind_value = record.kind.value if hasattr(record.kind, "value") else str(record.kind)
        tags = set(record.semantic_tags)
        if kind_value == "failure_pattern" or "failure" in tags:
            result["failure"].append(record.memory_id)
        if kind_value == "repair_history" or "repair" in tags:
            result["repair"].append(record.memory_id)
        if kind_value == "stabilization_history" or "stabilization" in tags:
            result["stabilization"].append(record.memory_id)
        if kind_value == "replay_window" or "replay" in tags:
            result["replay"].append(record.memory_id)
        if kind_value in {"transaction_history", "recovery_terminal"} or "rollback" in tags or record.terminal_state == "rolled_back":
            result["rollback"].append(record.memory_id)
    explicit = _text_tuple(payload.get("memory_refs") or payload.get("source_memory_ids"))
    result["all"].extend(ref for ref in explicit if ref not in result["all"])
    return {key: tuple(value) for key, value in result.items()}


def _context(context: Mapping[str, Any] | None, overrides: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(context or {}))
    payload.update(copy.deepcopy(dict(overrides or {})))
    return payload


def _side_effects(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return _append_unique(payload.get("predicted_side_effects"), payload.get("side_effects"), payload.get("affected_files"), payload.get("target_path"))


def _risk_for_counts(primary: int, secondary: int) -> RuntimePredictionRisk:
    score = int(primary or 0) + int(secondary or 0)
    if score <= 0:
        return RuntimePredictionRisk.LOW
    if score == 1:
        return RuntimePredictionRisk.MEDIUM
    if score <= 3:
        return RuntimePredictionRisk.HIGH
    return RuntimePredictionRisk.CRITICAL


def _confidence(memory: Mapping[str, tuple[str, ...]], *, base: float) -> float:
    return _bounded(base + 0.04 * len(memory.get("all", ())))


def _branch_from_any(value: RuntimeSimulationBranch | Mapping[str, Any]) -> RuntimeSimulationBranch:
    if isinstance(value, RuntimeSimulationBranch):
        return value
    payload = copy.deepcopy(dict(value))
    digest = str(payload.get("normalized_digest") or _digest(payload))
    return RuntimeSimulationBranch(
        branch_id=str(payload.get("branch_id") or "runtime_simulation_branch:" + digest[:16]),
        parent_trace_id=str(payload.get("parent_trace_id") or ""),
        simulation_mode=str(payload.get("simulation_mode") or "what_if"),
        simulated_steps=tuple(_mapping_tuple(payload.get("simulated_steps"))),
        predicted_transactions=tuple(_mapping_tuple(payload.get("predicted_transactions"))),
        predicted_recovery_paths=tuple(_mapping_tuple(payload.get("predicted_recovery_paths"))),
        predicted_repair_paths=tuple(_mapping_tuple(payload.get("predicted_repair_paths"))),
        predicted_evidence_refs=_text_tuple(payload.get("predicted_evidence_refs")),
        memory_refs=_text_tuple(payload.get("memory_refs")),
        committed=bool(payload.get("committed")),
        mutation_allowed=bool(payload.get("mutation_allowed")),
        authority_granted=bool(payload.get("authority_granted")),
        normalized_digest=digest,
    )


def _prediction_tuple(value: Any) -> tuple[RuntimePredictionResult, ...]:
    if value is None:
        return ()
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result = []
    for item in values:
        if isinstance(item, RuntimePredictionResult):
            result.append(item)
        elif isinstance(item, Mapping):
            result.append(_prediction_from_mapping(item))
    return tuple(result)


def _prediction_from_mapping(payload: Mapping[str, Any]) -> RuntimePredictionResult:
    kind = RuntimePredictionKind(str(payload.get("kind") or RuntimePredictionKind.MUTATION_IMPACT.value))
    digest = str(payload.get("normalized_digest") or _digest(payload))
    return RuntimePredictionResult(
        prediction_id=str(payload.get("prediction_id") or "runtime_prediction:" + digest[:16]),
        kind=kind,
        memory_refs=_text_tuple(payload.get("memory_refs")),
        evidence_refs=_text_tuple(payload.get("evidence_refs")),
        normalized_digest=digest,
    )


def _mapping_tuple(value: Any) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return tuple(copy.deepcopy(dict(item)) if isinstance(item, Mapping) else {"value": copy.deepcopy(item)} for item in values)


def _append_unique(*values: Any) -> tuple[str, ...]:
    refs: list[str] = []
    for value in values:
        for item in _text_tuple(value):
            if item not in refs:
                refs.append(item)
    return tuple(refs)


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


def _stable_ref(prefix: str, *parts: Any) -> str:
    return f"{prefix}:{hashlib.sha256(json.dumps(_normalize_value(parts), sort_keys=True, default=str).encode('utf-8')).hexdigest()[:16]}"


def _bounded(value: float) -> float:
    return round(max(0.0, min(1.0, float(value or 0.0))), 4)


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
