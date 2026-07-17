from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


class RuntimeInvariant(str, Enum):
    AUTHORITY_ANONYMOUS_MUTATION_FORBIDDEN = "authority.anonymous_mutation_forbidden"
    AUTHORITY_CONTEXT_IS_NOT_AUTHORITY = "authority.review_evidence_replay_context_is_not_authority"
    AUTHORITY_SIDE_EFFECT_REQUIRES_AUTHORITY = "authority.side_effect_requires_authority"
    SURFACE_MUTATION_REQUIRES_TRANSACTION = "surface.mutation_surface_requires_transaction"
    SURFACE_READ_ONLY_CANNOT_MUTATE = "surface.read_only_surface_cannot_mutate"
    SURFACE_UNKNOWN_MUTATION_DEFAULTS_BLOCKED = "surface.unknown_mutation_like_surface_defaults_blocked"
    TRANSACTION_COMMITTED_REQUIRES_VERIFIED_SUCCESS = "transaction.committed_requires_verified_success"
    TRANSACTION_ROLLBACK_REQUIRES_EVIDENCE = "transaction.rollback_requires_rollback_evidence"
    TRANSACTION_STATE_ORDER_CANNOT_SKIP = "transaction.state_order_cannot_skip"
    TRANSACTION_SOURCE_IMMUTABLE = "transaction.source_transaction_immutable"
    REPLAY_READ_CANNOT_MUTATE = "replay.replay_read_cannot_mutate"
    REPLAY_CANNOT_BYPASS_AUTHORITY = "replay.cannot_bypass_authority"
    REPLAY_CREATED_TRANSACTION_DIFFERS_FROM_SOURCE = "replay.created_transaction_differs_from_source"
    REPLAY_DETERMINISTIC_DIGEST_STABLE = "replay.deterministic_digest_stable"
    RECOVERY_VERIFY_FAIL_CANNOT_COMMIT = "recovery.verify_fail_cannot_commit"
    RECOVERY_RETRY_LOOP_BOUNDED = "recovery.retry_loop_bounded"
    RECOVERY_TERMINAL_FAILURE_QUERYABLE = "recovery.terminal_failure_queryable"
    RECOVERY_ROLLBACK_LINEAGE_PRESERVED = "recovery.rollback_lineage_preserved"
    EVIDENCE_CANNOT_GRANT_AUTHORITY = "evidence.cannot_grant_authority"
    EVIDENCE_CANNOT_CREATE_TRANSACTION = "evidence.cannot_create_transaction"
    EVIDENCE_DIGEST_DETERMINISTIC = "evidence.digest_deterministic"
    EVIDENCE_LINEAGE_PRESERVED = "evidence.lineage_preserved"
    PREDICTION_CANNOT_GRANT_AUTHORITY = "prediction.cannot_grant_authority"
    PREDICTION_CANNOT_BYPASS_APPROVAL = "prediction.result_cannot_bypass_approval"
    PREDICTION_SOURCE_LINEAGE_IMMUTABLE = "prediction.source_lineage_immutable"
    SIMULATION_CANNOT_MUTATE = "simulation.cannot_mutate"
    SIMULATION_BRANCH_CANNOT_COMMIT = "simulation.branch_cannot_commit"


@dataclass(frozen=True)
class RuntimeInvariantViolation:
    invariant: RuntimeInvariant
    component: str
    reason: str
    blocked: bool = True
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["invariant"] = self.invariant.value
        return _normalize_value(payload)


@dataclass(frozen=True)
class RuntimeInvariantSnapshot:
    invariant: RuntimeInvariant
    component: str
    ok: bool
    violation_count: int = 0
    reasons: tuple[str, ...] = ()
    digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["invariant"] = self.invariant.value
        payload["reasons"] = list(self.reasons)
        return _normalize_value(payload)


@dataclass(frozen=True)
class RuntimeConstitutionState:
    snapshot_id: str
    invariant_snapshots: tuple[RuntimeInvariantSnapshot, ...]
    violations: tuple[RuntimeInvariantViolation, ...] = ()
    normalized_digest: str = ""
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "ok": bool(self.ok),
            "normalized_digest": self.normalized_digest,
            "invariant_snapshots": [item.to_dict() for item in self.invariant_snapshots],
            "violations": [item.to_dict() for item in self.violations],
        }


_VIOLATIONS: list[RuntimeInvariantViolation] = []


def record_runtime_invariant_violation(
    invariant: RuntimeInvariant | str,
    *,
    component: str,
    reason: str,
    context: Mapping[str, Any] | None = None,
    blocked: bool = True,
) -> RuntimeInvariantViolation:
    violation = RuntimeInvariantViolation(
        invariant=RuntimeInvariant(str(invariant.value if isinstance(invariant, RuntimeInvariant) else invariant)),
        component=str(component or "runtime"),
        reason=str(reason or "runtime_invariant_violation"),
        blocked=bool(blocked),
        context=copy.deepcopy(dict(context or {})),
    )
    _VIOLATIONS.append(violation)
    try:
        from core.runtime.runtime_memory_engine import append_runtime_memory, memory_record_for_invariant_violation

        append_runtime_memory(memory_record_for_invariant_violation(violation))
    except Exception:
        pass
    return violation


def list_runtime_invariant_violations(*, component: str | None = None) -> tuple[RuntimeInvariantViolation, ...]:
    values = tuple(_VIOLATIONS)
    if component is not None:
        values = tuple(item for item in values if item.component == component)
    return values


def assert_authority_invariant(
    metadata: Mapping[str, Any] | None = None,
    *,
    surface: Any | None = None,
    validation: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> bool:
    from core.runtime.runtime_surface_registry import classify_runtime_surface

    authority = dict(metadata or {})
    validation_payload = dict(validation or {})
    classified = classify_runtime_surface(surface or authority.get("surface") or authority.get("type"))
    if classified.mutation and not authority and validation_payload.get("ok"):
        _raise(RuntimeInvariant.AUTHORITY_ANONYMOUS_MUTATION_FORBIDDEN, "authority", "anonymous mutation cannot be authorized", {"surface": classified.name})
    if _is_context_only_authority(context or authority) and validation_payload.get("ok"):
        _raise(RuntimeInvariant.AUTHORITY_CONTEXT_IS_NOT_AUTHORITY, "authority", "review/evidence/replay context is not authority", {"surface": classified.name})
    if classified.side_effect and not validation_payload.get("ok"):
        reason = str(validation_payload.get("reason") or "side effect requires authority")
        _raise(RuntimeInvariant.AUTHORITY_SIDE_EFFECT_REQUIRES_AUTHORITY, "authority", reason, {"surface": classified.name})
    return True


def assert_surface_invariant(surface: Any, *, mutation_attempted: bool | None = None) -> bool:
    from core.runtime.runtime_surface_registry import RuntimeSurfaceKind, classify_runtime_surface

    classified = classify_runtime_surface(surface)
    if classified.mutation and not classified.requires_transaction:
        _raise(RuntimeInvariant.SURFACE_MUTATION_REQUIRES_TRANSACTION, "surface", "mutation surface requires transaction", {"surface": classified.name})
    if classified.read_only and (mutation_attempted or classified.mutation):
        _raise(RuntimeInvariant.SURFACE_READ_ONLY_CANNOT_MUTATE, "surface", "read-only surface cannot mutate", {"surface": classified.name})
    if classified.kind is RuntimeSurfaceKind.UNKNOWN and classified.mutation and not (classified.requires_authority and classified.requires_transaction):
        _raise(RuntimeInvariant.SURFACE_UNKNOWN_MUTATION_DEFAULTS_BLOCKED, "surface", "unknown mutation-like surface must default blocked", {"surface": classified.name})
    return True


def assert_transaction_invariant(transaction: Any) -> bool:
    payload = _to_mapping(transaction)
    history = [str(item) for item in payload.get("state_history") or ([payload.get("state")] if payload.get("state") else [])]
    state = str(payload.get("state") or "")
    if "committed" in history or state == "committed":
        verification = payload.get("verification_result") if isinstance(payload.get("verification_result"), Mapping) else {}
        if "verified" not in history or not _result_ok(verification):
            _raise(RuntimeInvariant.TRANSACTION_COMMITTED_REQUIRES_VERIFIED_SUCCESS, "transaction", "committed transaction requires verified success", payload)
    if state == "rolled_back" and not payload.get("rollback_result"):
        _raise(RuntimeInvariant.TRANSACTION_ROLLBACK_REQUIRES_EVIDENCE, "transaction", "rollback requires rollback evidence", payload)
    _assert_state_order(history, component="transaction")
    if payload.get("original_transaction_id") and payload.get("transaction_id") == payload.get("original_transaction_id"):
        _raise(RuntimeInvariant.TRANSACTION_SOURCE_IMMUTABLE, "transaction", "source transaction is immutable", payload)
    return True


def assert_replay_invariant(replay: Any, *, second: Any | None = None) -> bool:
    payload = _to_mapping(replay)
    mode = str(payload.get("mode") or "")
    if mode in {"read_only", "replay_read"} and (payload.get("mutation_allowed") or payload.get("transaction_required") or payload.get("mutation_attempted")):
        _raise(RuntimeInvariant.REPLAY_READ_CANNOT_MUTATE, "replay", "replay_read cannot mutate", payload)
    if payload.get("mutation_attempted") and not payload.get("authority_required"):
        _raise(RuntimeInvariant.REPLAY_CANNOT_BYPASS_AUTHORITY, "replay", "replay cannot bypass authority", payload)
    if payload.get("original_transaction_id") and payload.get("transaction_id") == payload.get("original_transaction_id"):
        _raise(RuntimeInvariant.REPLAY_CREATED_TRANSACTION_DIFFERS_FROM_SOURCE, "replay", "replay-created transaction must differ from source", payload)
    if second is not None:
        first_digest = _digest(_normalize_replay_for_digest(payload))
        second_digest = _digest(_normalize_replay_for_digest(_to_mapping(second)))
        if first_digest != second_digest:
            _raise(RuntimeInvariant.REPLAY_DETERMINISTIC_DIGEST_STABLE, "replay", "replay deterministic digest drifted", {"first": first_digest, "second": second_digest})
    return True


def assert_recovery_invariant(recovery: Any) -> bool:
    payload = _to_mapping(recovery)
    state = str(payload.get("state") or "")
    history = [str(item) for item in payload.get("state_history") or ([state] if state else [])]
    verification = payload.get("verification_result") if isinstance(payload.get("verification_result"), Mapping) else {}
    if not _result_ok(verification) and ("committed" in history or state == "committed"):
        _raise(RuntimeInvariant.RECOVERY_VERIFY_FAIL_CANNOT_COMMIT, "recovery", "verify fail cannot commit", payload)
    if int(payload.get("retry_count") or 0) > int(payload.get("max_retries") or 0):
        _raise(RuntimeInvariant.RECOVERY_RETRY_LOOP_BOUNDED, "recovery", "recovery retry count exceeded bound", payload)
    if state == "failed_terminal" and not payload.get("failure_result"):
        _raise(RuntimeInvariant.RECOVERY_TERMINAL_FAILURE_QUERYABLE, "recovery", "terminal failure must be queryable", payload)
    if state == "rolled_back" and not (payload.get("original_transaction_id") and payload.get("rollback_result")):
        _raise(RuntimeInvariant.RECOVERY_ROLLBACK_LINEAGE_PRESERVED, "recovery", "rollback lineage must be preserved", payload)
    return True


def assert_evidence_invariant(evidence: Any, *, second: Any | None = None) -> bool:
    payload = _to_mapping(evidence)
    forbidden = {"execution_authority", "authority_metadata", "execution_authority_metadata"}
    if forbidden & set(payload) or payload.get("authority_granted") or payload.get("approval_state") in {"approved", "allowed"}:
        _raise(RuntimeInvariant.EVIDENCE_CANNOT_GRANT_AUTHORITY, "evidence", "evidence cannot grant authority", payload)
    if payload.get("creates_transaction") or payload.get("transaction_created"):
        _raise(RuntimeInvariant.EVIDENCE_CANNOT_CREATE_TRANSACTION, "evidence", "evidence cannot create transaction", payload)
    if second is not None and _digest(payload) != _digest(_to_mapping(second)):
        _raise(RuntimeInvariant.EVIDENCE_DIGEST_DETERMINISTIC, "evidence", "evidence digest drifted", {"first": payload, "second": _to_mapping(second)})
    if payload.get("evidence_ids") and not _lineage_order_valid(payload):
        _raise(RuntimeInvariant.EVIDENCE_LINEAGE_PRESERVED, "evidence", "evidence lineage order is invalid", payload)
    return True


def assert_prediction_invariant(prediction: Any) -> bool:
    payload = _to_mapping(prediction)
    if payload.get("authoritative") or payload.get("authority_granted"):
        _raise(RuntimeInvariant.PREDICTION_CANNOT_GRANT_AUTHORITY, "prediction", "prediction cannot grant authority", payload)
    if payload.get("approval_state") in {"approved", "allowed"} or payload.get("approved") or payload.get("approval_granted"):
        _raise(RuntimeInvariant.PREDICTION_CANNOT_BYPASS_APPROVAL, "prediction", "prediction result cannot bypass approval", payload)
    if payload.get("source_transaction_id") and payload.get("transaction_id") == payload.get("source_transaction_id"):
        _raise(RuntimeInvariant.PREDICTION_SOURCE_LINEAGE_IMMUTABLE, "prediction", "prediction source lineage immutable", payload)
    if payload.get("creates_transaction") or payload.get("transaction_created"):
        _raise(RuntimeInvariant.PREDICTION_CANNOT_BYPASS_APPROVAL, "prediction", "prediction cannot create transaction", payload)
    return True


def assert_simulation_invariant(simulation: Any) -> bool:
    payload = _to_mapping(simulation)
    branch = payload.get("branch") if isinstance(payload.get("branch"), Mapping) else payload
    if payload.get("committed") or branch.get("committed"):
        _raise(RuntimeInvariant.SIMULATION_BRANCH_CANNOT_COMMIT, "simulation", "simulation branch cannot commit", payload)
    if payload.get("mutation_allowed") or payload.get("authority_granted") or branch.get("mutation_allowed") or branch.get("authority_granted"):
        _raise(RuntimeInvariant.SIMULATION_CANNOT_MUTATE, "simulation", "simulation cannot mutate", payload)
    for tx in branch.get("predicted_transactions") or []:
        if isinstance(tx, Mapping) and (tx.get("real_transaction") or tx.get("committed") or tx.get("transaction_created")):
            _raise(RuntimeInvariant.SIMULATION_CANNOT_MUTATE, "simulation", "simulation cannot create real transaction", payload)
    return True


def collect_runtime_invariants(*, violations: Any = None) -> RuntimeConstitutionState:
    return create_constitution_snapshot(violations=violations)


def create_constitution_snapshot(*, violations: Any = None) -> RuntimeConstitutionState:
    violation_values = tuple(_iter_violations(violations if violations is not None else _VIOLATIONS))
    snapshots = []
    for invariant in RuntimeInvariant:
        related = tuple(item for item in violation_values if item.invariant is invariant)
        payload = {
            "invariant": invariant.value,
            "component": _component_for_invariant(invariant),
            "ok": not related,
            "violation_count": len(related),
            "reasons": sorted({item.reason for item in related}),
        }
        snapshots.append(
            RuntimeInvariantSnapshot(
                invariant=invariant,
                component=payload["component"],
                ok=payload["ok"],
                violation_count=payload["violation_count"],
                reasons=tuple(payload["reasons"]),
                digest=_digest(payload),
            )
        )
    normalized = {
        "invariant_snapshots": [item.to_dict() for item in snapshots],
        "violations": [item.to_dict() for item in violation_values],
    }
    digest = _digest(normalized)
    return RuntimeConstitutionState(
        snapshot_id="runtime_constitution:" + digest[:16],
        invariant_snapshots=tuple(snapshots),
        violations=violation_values,
        normalized_digest=digest,
        ok=not violation_values,
    )


def normalize_constitution_snapshot(snapshot: RuntimeConstitutionState | Mapping[str, Any]) -> dict[str, Any]:
    payload = snapshot.to_dict() if isinstance(snapshot, RuntimeConstitutionState) else copy.deepcopy(dict(snapshot))
    return _normalize_value(payload)


def validate_constitution_snapshot(snapshot: RuntimeConstitutionState | Mapping[str, Any]) -> dict[str, Any]:
    payload = normalize_constitution_snapshot(snapshot)
    invariant_snapshots = payload.get("invariant_snapshots") or []
    violations = payload.get("violations") or []
    expected_digest = _digest({"invariant_snapshots": invariant_snapshots, "violations": violations})
    return {
        "ok": payload.get("normalized_digest") == expected_digest and len(invariant_snapshots) >= len(RuntimeInvariant),
        "normalized_digest": payload.get("normalized_digest"),
        "expected_digest": expected_digest,
        "violation_count": len(violations),
        "invariant_count": len(invariant_snapshots),
    }


def assert_runtime_constitution_integrity(snapshot: RuntimeConstitutionState | Mapping[str, Any] | None = None) -> bool:
    state = snapshot if snapshot is not None else create_constitution_snapshot(violations=())
    validation = validate_constitution_snapshot(state)
    if not validation["ok"]:
        raise AssertionError("runtime constitution snapshot integrity invalid")
    if normalize_constitution_snapshot(state).get("violations"):
        raise AssertionError("runtime constitution has invariant violations")
    return True


def _raise(invariant: RuntimeInvariant, component: str, reason: str, context: Mapping[str, Any]) -> None:
    violation = record_runtime_invariant_violation(invariant, component=component, reason=reason, context=context)
    raise AssertionError(reason) from RuntimeError(json.dumps(violation.to_dict(), sort_keys=True))


def _assert_state_order(history: list[str], *, component: str) -> None:
    order = {
        "proposed": 0,
        "preflight": 1,
        "approved": 2,
        "blocked": 2,
        "applied": 3,
        "verified": 4,
        "committed": 5,
        "rolled_back": 5,
        "failed": 5,
        "failed_terminal": 5,
        "audited": 6,
    }
    previous = -1
    for state in history:
        current = order.get(state, previous)
        if current < previous:
            _raise(RuntimeInvariant.TRANSACTION_STATE_ORDER_CANNOT_SKIP, component, "transaction state order cannot move backwards", {"state_history": history})
        previous = current
    if "committed" in history and "verified" not in history:
        _raise(RuntimeInvariant.TRANSACTION_STATE_ORDER_CANNOT_SKIP, component, "transaction state order cannot skip verified", {"state_history": history})


def _is_context_only_authority(value: Mapping[str, Any] | None) -> bool:
    if not value:
        return False
    context_keys = {
        "review_context",
        "governance_context",
        "policy_context",
        "policy_result",
        "replay_context",
        "replay_source",
        "replay_run_id",
        "evidence",
        "canonical_evidence",
        "evidence_snapshot",
        "evidence_refs",
        "recovery_context",
        "recovery_source",
        "recovery_attempt_id",
    }
    return set(value).issubset(context_keys)


def _component_for_invariant(invariant: RuntimeInvariant) -> str:
    return invariant.value.split(".", 1)[0]


def _iter_violations(value: Any) -> list[RuntimeInvariantViolation]:
    if value is None:
        return []
    if isinstance(value, RuntimeInvariantViolation):
        return [value]
    try:
        items = list(value)
    except TypeError:
        items = [value]
    violations = []
    for item in items:
        if isinstance(item, RuntimeInvariantViolation):
            violations.append(item)
        elif isinstance(item, Mapping) and item.get("invariant"):
            violations.append(
                RuntimeInvariantViolation(
                    invariant=RuntimeInvariant(str(item["invariant"])),
                    component=str(item.get("component") or _component_for_invariant(RuntimeInvariant(str(item["invariant"])))),
                    reason=str(item.get("reason") or "runtime_invariant_violation"),
                    blocked=bool(item.get("blocked", True)),
                    context=copy.deepcopy(dict(item.get("context") or {})),
                )
            )
    return violations


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return copy.deepcopy(dict(converted))
    return copy.deepcopy(asdict(value)) if hasattr(value, "__dataclass_fields__") else {}


def _result_ok(result: Mapping[str, Any] | None) -> bool:
    if not isinstance(result, Mapping):
        return False
    if result.get("ok") is False or result.get("allowed") is False:
        return False
    return bool(result.get("ok") or result.get("allowed") or result.get("approved") or result.get("verification_ok") or result.get("committed"))


def _lineage_order_valid(payload: Mapping[str, Any]) -> bool:
    evidence_ids = list(payload.get("evidence_ids") or [])
    positions = []
    for key in ("authority_refs", "surface_refs", "transaction_refs", "replay_refs", "recovery_refs", "audit_refs"):
        refs = [ref for ref in payload.get(key, []) if ref in evidence_ids]
        if refs:
            positions.append(min(evidence_ids.index(ref) for ref in refs))
    return positions == sorted(positions)


def _normalize_replay_for_digest(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_value(payload)
    for key in ("started_at", "finished_at"):
        normalized.pop(key, None)
    return normalized


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
