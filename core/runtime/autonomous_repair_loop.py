from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping

from core.runtime.execution_authority import validate_authority_metadata
from core.runtime.runtime_constitution_freeze import (
    RuntimeInvariantViolation,
    assert_authority_invariant,
    assert_recovery_invariant,
    assert_transaction_invariant,
    record_runtime_invariant_violation,
)
from core.runtime.runtime_surface_registry import classify_runtime_surface
from core.runtime.runtime_transaction_registry import (
    RuntimeTransaction,
    create_transaction,
    get_transaction,
    record_apply,
    record_approval,
    record_audit,
    record_commit,
    record_preflight,
    record_rollback,
    record_verification,
)


class AutonomousRepairState(str, Enum):
    OBSERVED = "observed"
    DIAGNOSED = "diagnosed"
    REPAIR_PROPOSED = "repair_proposed"
    REPAIR_APPLIED = "repair_applied"
    VERIFIED = "verified"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    RESUMED = "resumed"
    STABILIZED = "stabilized"
    FAILED_TERMINAL = "failed_terminal"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    BLOCKED = "blocked"


class AutonomousRepairDecision(str, Enum):
    OBSERVE = "observe"
    DIAGNOSE = "diagnose"
    PROPOSE_REPAIR = "propose_repair"
    APPLY_REPAIR = "apply_repair"
    VERIFY = "verify"
    COMMIT = "commit"
    ROLLBACK = "rollback"
    RESUME = "resume"
    STABILIZE = "stabilize"
    FAIL_TERMINAL = "fail_terminal"
    REQUIRE_HUMAN_REVIEW = "require_human_review"
    BLOCK = "block"


TERMINAL_REPAIR_STATES = {
    AutonomousRepairState.STABILIZED,
    AutonomousRepairState.FAILED_TERMINAL,
    AutonomousRepairState.REQUIRES_HUMAN_REVIEW,
    AutonomousRepairState.BLOCKED,
}


@dataclass(frozen=True)
class AutonomousRepairAttempt:
    attempt_id: str
    loop_id: str
    state: AutonomousRepairState
    decision: AutonomousRepairDecision
    strategy: str = ""
    reason: str = ""
    verification_result: dict[str, Any] = field(default_factory=dict)
    transaction_id: str = ""
    recovery_attempt_id: str = ""
    evidence_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["decision"] = self.decision.value
        return payload


@dataclass(frozen=True)
class AutonomousRepairLoopResult:
    loop_id: str
    task_id: str
    step_id: str
    trace_id: str
    source_failure_id: str = ""
    source_transaction_id: str = ""
    source_replay_run_id: str = ""
    source_recovery_attempt_id: str = ""
    diagnosis: dict[str, Any] = field(default_factory=dict)
    repair_strategy: dict[str, Any] = field(default_factory=dict)
    attempts: tuple[AutonomousRepairAttempt, ...] = ()
    max_attempts: int = 1
    final_state: AutonomousRepairState = AutonomousRepairState.OBSERVED
    terminal: bool = False
    committed: bool = False
    rolled_back: bool = False
    resumed: bool = False
    stabilized: bool = False
    authority_refs: tuple[str, ...] = ()
    transaction_refs: tuple[str, ...] = ()
    replay_refs: tuple[str, ...] = ()
    recovery_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    invariant_refs: tuple[str, ...] = ()
    prediction_refs: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    normalized_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["attempts"] = [attempt.to_dict() for attempt in self.attempts]
        payload["final_state"] = self.final_state.value
        for key in (
            "authority_refs",
            "transaction_refs",
            "replay_refs",
            "recovery_refs",
            "evidence_refs",
            "invariant_refs",
            "prediction_refs",
        ):
            payload[key] = list(getattr(self, key))
        return payload


_LOOPS: dict[str, AutonomousRepairLoopResult] = {}


def observe_runtime_failure(
    failure: Mapping[str, Any] | None = None,
    *,
    task_id: str = "",
    step_id: str = "",
    trace_id: str = "",
    source_transaction_id: str = "",
    source_replay_run_id: str = "",
    source_recovery_attempt_id: str = "",
    max_attempts: int = 1,
) -> AutonomousRepairLoopResult:
    payload = dict(failure or {})
    task = _first_text(task_id, payload.get("task_id"), "task-autonomous-repair")
    step = _first_text(step_id, payload.get("step_id"), "step-autonomous-repair")
    trace = _first_text(trace_id, payload.get("trace_id"), payload.get("source_trace_id"), "trace-autonomous-repair")
    source_failure_id = _first_text(payload.get("failure_id"), payload.get("error_id"), _stable_id("failure", payload))
    loop_id = _stable_id(
        "repair_loop",
        task,
        step,
        trace,
        source_failure_id,
        source_transaction_id or payload.get("transaction_id"),
        source_replay_run_id or payload.get("replay_run_id"),
        source_recovery_attempt_id or payload.get("recovery_attempt_id"),
    )
    evidence_id = _repair_evidence(
        "observe",
        loop_id=loop_id,
        task_id=task,
        step_id=step,
        trace_id=trace,
        state=AutonomousRepairState.OBSERVED.value,
        reason=str(payload.get("reason") or payload.get("message") or "runtime_failure_observed"),
    )
    now = _now()
    attempt = AutonomousRepairAttempt(
        attempt_id=_attempt_id(loop_id, 1, "observe"),
        loop_id=loop_id,
        state=AutonomousRepairState.OBSERVED,
        decision=AutonomousRepairDecision.OBSERVE,
        reason=str(payload.get("reason") or payload.get("message") or "runtime_failure_observed"),
        evidence_id=evidence_id,
        created_at=now,
        updated_at=now,
    )
    result = AutonomousRepairLoopResult(
        loop_id=loop_id,
        task_id=task,
        step_id=step,
        trace_id=trace,
        source_failure_id=source_failure_id,
        source_transaction_id=str(source_transaction_id or payload.get("transaction_id") or ""),
        source_replay_run_id=str(source_replay_run_id or payload.get("replay_run_id") or ""),
        source_recovery_attempt_id=str(source_recovery_attempt_id or payload.get("recovery_attempt_id") or ""),
        attempts=(attempt,),
        max_attempts=max(0, int(max_attempts or 0)),
        final_state=AutonomousRepairState.OBSERVED,
        replay_refs=_text_tuple(source_replay_run_id or payload.get("replay_run_id")),
        recovery_refs=_text_tuple(source_recovery_attempt_id or payload.get("recovery_attempt_id")),
        evidence_refs=(evidence_id,),
        created_at=now,
        updated_at=now,
    )
    return _store(_with_digest(result))


def diagnose_runtime_failure(loop: AutonomousRepairLoopResult | str, diagnosis: Mapping[str, Any] | None = None) -> AutonomousRepairLoopResult:
    current = get_repair_loop(loop)
    payload = {
        "failure_class": "verification_failure",
        "repairable": True,
        "requires_human_review": False,
        **dict(diagnosis or {}),
    }
    if payload.get("requires_human_review"):
        return _terminal(
            current,
            state=AutonomousRepairState.REQUIRES_HUMAN_REVIEW,
            decision=AutonomousRepairDecision.REQUIRE_HUMAN_REVIEW,
            reason=str(payload.get("reason") or "diagnosis_requires_human_review"),
            diagnosis=payload,
        )
    evidence_id = _repair_evidence(
        "diagnose",
        loop_id=current.loop_id,
        task_id=current.task_id,
        step_id=current.step_id,
        trace_id=current.trace_id,
        state=AutonomousRepairState.DIAGNOSED.value,
        reason=str(payload.get("failure_class") or "diagnosed"),
    )
    attempt = _attempt(current, AutonomousRepairState.DIAGNOSED, AutonomousRepairDecision.DIAGNOSE, reason=str(payload.get("failure_class") or "diagnosed"), evidence_id=evidence_id)
    return _store(_with_digest(_replace(current, diagnosis=payload, attempts=(*current.attempts, attempt), final_state=AutonomousRepairState.DIAGNOSED, evidence_refs=_append(current.evidence_refs, evidence_id))))


def propose_repair_action(loop: AutonomousRepairLoopResult | str, strategy: Mapping[str, Any] | None = None) -> AutonomousRepairLoopResult:
    current = get_repair_loop(loop)
    if current.final_state in TERMINAL_REPAIR_STATES:
        return current
    payload = {
        "strategy_id": "bounded_repair",
        "surface": "repair_chain_apply",
        "requires_authority": True,
        "requires_transaction": True,
        **dict(strategy or {}),
    }
    if _strategy_exhausted(current, str(payload.get("strategy_id") or "")):
        violation = record_runtime_invariant_violation(
            "recovery.retry_loop_bounded",
            component="repair",
            reason="repair strategy oscillation detected",
            context={"loop_id": current.loop_id, "strategy_id": payload.get("strategy_id")},
        )
        return _terminal(
            current,
            state=AutonomousRepairState.REQUIRES_HUMAN_REVIEW,
            decision=AutonomousRepairDecision.REQUIRE_HUMAN_REVIEW,
            reason="repair_strategy_oscillation_detected",
            repair_strategy=payload,
            invariant_ref=violation.invariant.value,
        )
    evidence_id = _repair_evidence(
        "propose",
        loop_id=current.loop_id,
        task_id=current.task_id,
        step_id=current.step_id,
        trace_id=current.trace_id,
        state=AutonomousRepairState.REPAIR_PROPOSED.value,
        reason=str(payload.get("strategy_id") or "repair_proposed"),
    )
    prediction_refs = _prediction_refs_for_repair(current, payload)
    attempt = _attempt(current, AutonomousRepairState.REPAIR_PROPOSED, AutonomousRepairDecision.PROPOSE_REPAIR, strategy=str(payload.get("strategy_id") or ""), evidence_id=evidence_id)
    return _store(_with_digest(_replace(current, repair_strategy=payload, attempts=(*current.attempts, attempt), final_state=AutonomousRepairState.REPAIR_PROPOSED, evidence_refs=_append(current.evidence_refs, evidence_id), prediction_refs=_append(current.prediction_refs, prediction_refs))))


def apply_repair_action(
    loop: AutonomousRepairLoopResult | str,
    *,
    authority: Mapping[str, Any] | None = None,
    repair_payload: Mapping[str, Any] | None = None,
) -> AutonomousRepairLoopResult:
    current = get_repair_loop(loop)
    if current.final_state in TERMINAL_REPAIR_STATES:
        return current
    payload = dict(repair_payload or {})
    surface = str(payload.get("surface") or current.repair_strategy.get("surface") or "repair_chain_apply")
    validation = validate_authority_metadata(authority or {}, surface=surface)
    try:
        assert_authority_invariant(authority or {}, surface=surface, validation=validation)
    except AssertionError:
        violation = _latest_violation_ref()
        return _terminal(
            current,
            state=AutonomousRepairState.BLOCKED,
            decision=AutonomousRepairDecision.BLOCK,
            reason=str(validation.get("reason") or "repair_authority_blocked"),
            invariant_ref=violation,
        )
    if not validation.get("ok"):
        return _terminal(current, state=AutonomousRepairState.BLOCKED, decision=AutonomousRepairDecision.BLOCK, reason=str(validation.get("reason") or "repair_authority_blocked"))

    classified = classify_runtime_surface(surface)
    if not classified.requires_transaction:
        violation = record_runtime_invariant_violation("surface.mutation_surface_requires_transaction", component="repair", reason="repair apply requires transaction", context={"loop_id": current.loop_id, "surface": surface})
        return _terminal(current, state=AutonomousRepairState.BLOCKED, decision=AutonomousRepairDecision.BLOCK, reason="repair_apply_requires_transaction", invariant_ref=violation.invariant.value)

    tx = create_transaction(
        task_id=str(authority.get("task_id") or current.task_id),
        step_id=str(authority.get("step_id") or current.step_id),
        trace_id=str(authority.get("trace_id") or current.trace_id),
        authority_source=str(authority.get("authority_source") or "autonomous_repair_loop"),
        surface=surface,
        affected_files=payload.get("affected_files") or payload.get("target_path") or ["workspace/shared/autonomous-repair.txt"],
        parent_transaction_id=current.source_transaction_id,
        original_transaction_id=current.source_transaction_id,
        original_trace_id=current.trace_id,
        repair_loop_id=current.loop_id,
        repair_source="autonomous_repair_loop",
        replay_refs=current.replay_refs,
    )
    tx = record_preflight(tx, {"ok": True, "repair_loop_id": current.loop_id})
    tx = record_approval(tx, {"ok": True, "approved": True, "repair_loop_id": current.loop_id})
    tx = record_apply(tx, {"ok": True, "repair_loop_id": current.loop_id}, affected_files=payload.get("affected_files") or payload.get("target_path"))
    assert_transaction_invariant(tx)
    evidence_id = _repair_evidence(
        "apply",
        loop_id=current.loop_id,
        task_id=current.task_id,
        step_id=current.step_id,
        trace_id=current.trace_id,
        transaction_id=tx.transaction_id,
        state=AutonomousRepairState.REPAIR_APPLIED.value,
        reason="repair_applied",
    )
    attempt = _attempt(current, AutonomousRepairState.REPAIR_APPLIED, AutonomousRepairDecision.APPLY_REPAIR, strategy=str(current.repair_strategy.get("strategy_id") or ""), transaction_id=tx.transaction_id, evidence_id=evidence_id)
    return _store(_with_digest(_replace(current, attempts=(*current.attempts, attempt), final_state=AutonomousRepairState.REPAIR_APPLIED, authority_refs=_append(current.authority_refs, str(authority.get("trace_id") or "")), transaction_refs=_append(current.transaction_refs, tx.transaction_id), evidence_refs=_append(current.evidence_refs, evidence_id))))


def verify_repair_action(loop: AutonomousRepairLoopResult | str, verification: Mapping[str, Any] | None = None) -> AutonomousRepairLoopResult:
    current = get_repair_loop(loop)
    if current.final_state in TERMINAL_REPAIR_STATES:
        return current
    result = {"ok": True, "verification_ok": True, **dict(verification or {})}
    tx = _last_transaction(current)
    if tx is not None:
        tx = record_verification(tx, result)
    state = AutonomousRepairState.VERIFIED if _result_ok(result) else AutonomousRepairState.FAILED_TERMINAL
    decision = AutonomousRepairDecision.VERIFY if _result_ok(result) else AutonomousRepairDecision.FAIL_TERMINAL
    evidence_id = _repair_evidence("verify", loop_id=current.loop_id, task_id=current.task_id, step_id=current.step_id, trace_id=current.trace_id, transaction_id=getattr(tx, "transaction_id", ""), state=state.value, reason=str(result.get("reason") or "repair_verified"))
    attempt = _attempt(current, state, decision, reason=str(result.get("reason") or "repair_verified"), verification_result=result, transaction_id=getattr(tx, "transaction_id", ""), evidence_id=evidence_id)
    updated_state = state if _result_ok(result) else AutonomousRepairState.REPAIR_APPLIED
    updated = _replace(current, attempts=(*current.attempts, attempt), final_state=updated_state, evidence_refs=_append(current.evidence_refs, evidence_id))
    if not _result_ok(result):
        updated = decide_repair_commit_or_rollback(updated, rollback_evidence={"reason": str(result.get("reason") or "repair_verification_failed")})
    return _store(_with_digest(updated))


def decide_repair_commit_or_rollback(
    loop: AutonomousRepairLoopResult | str,
    *,
    rollback_evidence: Mapping[str, Any] | None = None,
) -> AutonomousRepairLoopResult:
    current = get_repair_loop(loop)
    if current.final_state in TERMINAL_REPAIR_STATES:
        return current
    tx = _last_transaction(current)
    if tx is None:
        return _terminal(current, state=AutonomousRepairState.FAILED_TERMINAL, decision=AutonomousRepairDecision.FAIL_TERMINAL, reason="repair_transaction_missing")
    if current.final_state is AutonomousRepairState.VERIFIED:
        tx = record_commit(tx, {"ok": True, "committed": True, "repair_loop_id": current.loop_id})
        tx = record_audit(tx, [current.trace_id])
        evidence_id = _repair_evidence("commit", loop_id=current.loop_id, task_id=current.task_id, step_id=current.step_id, trace_id=current.trace_id, transaction_id=tx.transaction_id, state=AutonomousRepairState.COMMITTED.value, reason="repair_committed")
        attempt = _attempt(current, AutonomousRepairState.COMMITTED, AutonomousRepairDecision.COMMIT, transaction_id=tx.transaction_id, evidence_id=evidence_id)
        return _store(_with_digest(_replace(current, attempts=(*current.attempts, attempt), final_state=AutonomousRepairState.COMMITTED, committed=True, evidence_refs=_append(current.evidence_refs, evidence_id))))
    if not rollback_evidence:
        violation = record_runtime_invariant_violation("transaction.rollback_requires_rollback_evidence", component="repair", reason="repair rollback requires rollback evidence", context={"loop_id": current.loop_id})
        return _terminal(current, state=AutonomousRepairState.REQUIRES_HUMAN_REVIEW, decision=AutonomousRepairDecision.REQUIRE_HUMAN_REVIEW, reason="rollback_evidence_required", invariant_ref=violation.invariant.value)
    tx = record_rollback(tx, rollback_evidence)
    evidence_id = _repair_evidence("rollback", loop_id=current.loop_id, task_id=current.task_id, step_id=current.step_id, trace_id=current.trace_id, transaction_id=tx.transaction_id, state=AutonomousRepairState.ROLLED_BACK.value, reason=str(rollback_evidence.get("reason") or "repair_rolled_back"))
    attempt = _attempt(current, AutonomousRepairState.ROLLED_BACK, AutonomousRepairDecision.ROLLBACK, reason=str(rollback_evidence.get("reason") or "repair_rolled_back"), transaction_id=tx.transaction_id, evidence_id=evidence_id)
    return _store(_with_digest(_replace(current, attempts=(*current.attempts, attempt), final_state=AutonomousRepairState.ROLLED_BACK, rolled_back=True, evidence_refs=_append(current.evidence_refs, evidence_id))))


def resume_after_repair(loop: AutonomousRepairLoopResult | str) -> AutonomousRepairLoopResult:
    current = get_repair_loop(loop)
    if current.final_state not in {AutonomousRepairState.COMMITTED, AutonomousRepairState.ROLLED_BACK}:
        return _terminal(current, state=AutonomousRepairState.REQUIRES_HUMAN_REVIEW, decision=AutonomousRepairDecision.REQUIRE_HUMAN_REVIEW, reason="resume_requires_verified_commit_or_safe_rollback")
    evidence_id = _repair_evidence("resume", loop_id=current.loop_id, task_id=current.task_id, step_id=current.step_id, trace_id=current.trace_id, state=AutonomousRepairState.RESUMED.value, reason="repair_resumed")
    attempt = _attempt(current, AutonomousRepairState.RESUMED, AutonomousRepairDecision.RESUME, evidence_id=evidence_id)
    return _store(_with_digest(_replace(current, attempts=(*current.attempts, attempt), final_state=AutonomousRepairState.RESUMED, resumed=True, evidence_refs=_append(current.evidence_refs, evidence_id))))


def stabilize_repair_loop(loop: AutonomousRepairLoopResult | str) -> AutonomousRepairLoopResult:
    current = get_repair_loop(loop)
    if current.final_state not in {AutonomousRepairState.RESUMED, AutonomousRepairState.COMMITTED, AutonomousRepairState.ROLLED_BACK, AutonomousRepairState.FAILED_TERMINAL, AutonomousRepairState.REQUIRES_HUMAN_REVIEW, AutonomousRepairState.BLOCKED}:
        return _terminal(current, state=AutonomousRepairState.REQUIRES_HUMAN_REVIEW, decision=AutonomousRepairDecision.REQUIRE_HUMAN_REVIEW, reason="stabilize_requires_terminal_repair_state")
    if current.final_state in {AutonomousRepairState.FAILED_TERMINAL, AutonomousRepairState.REQUIRES_HUMAN_REVIEW, AutonomousRepairState.BLOCKED}:
        return _store(_with_digest(replace(current, terminal=True, updated_at=_now())))
    evidence_id = _repair_evidence("stabilize", loop_id=current.loop_id, task_id=current.task_id, step_id=current.step_id, trace_id=current.trace_id, state=AutonomousRepairState.STABILIZED.value, reason="repair_stabilized")
    attempt = _attempt(current, AutonomousRepairState.STABILIZED, AutonomousRepairDecision.STABILIZE, evidence_id=evidence_id)
    return _store(_with_digest(_replace(current, attempts=(*current.attempts, attempt), final_state=AutonomousRepairState.STABILIZED, terminal=True, stabilized=True, evidence_refs=_append(current.evidence_refs, evidence_id))))


def run_autonomous_repair_loop(
    failure: Mapping[str, Any] | None = None,
    *,
    authority: Mapping[str, Any] | None = None,
    diagnosis: Mapping[str, Any] | None = None,
    strategy: Mapping[str, Any] | None = None,
    repair_payload: Mapping[str, Any] | None = None,
    verification: Mapping[str, Any] | None = None,
    max_attempts: int = 1,
) -> AutonomousRepairLoopResult:
    loop = observe_runtime_failure(failure, max_attempts=max_attempts)
    loop = diagnose_runtime_failure(loop, diagnosis)
    if loop.terminal or loop.final_state in TERMINAL_REPAIR_STATES:
        return stabilize_repair_loop(loop)
    loop = propose_repair_action(loop, strategy)
    if loop.terminal or loop.final_state in TERMINAL_REPAIR_STATES:
        return stabilize_repair_loop(loop)
    loop = apply_repair_action(loop, authority=authority, repair_payload=repair_payload)
    if loop.terminal or loop.final_state in TERMINAL_REPAIR_STATES:
        return stabilize_repair_loop(loop)
    loop = verify_repair_action(loop, verification)
    if loop.final_state is AutonomousRepairState.VERIFIED:
        loop = decide_repair_commit_or_rollback(loop)
    loop = resume_after_repair(loop)
    loop = stabilize_repair_loop(loop)
    return loop


def get_repair_loop(loop: AutonomousRepairLoopResult | str) -> AutonomousRepairLoopResult:
    if isinstance(loop, AutonomousRepairLoopResult):
        return loop
    item = _LOOPS.get(str(loop or ""))
    if item is None:
        raise KeyError(f"repair loop not found: {loop}")
    return item


def normalize_repair_loop_result(loop: AutonomousRepairLoopResult | Mapping[str, Any]) -> dict[str, Any]:
    payload = loop.to_dict() if isinstance(loop, AutonomousRepairLoopResult) else copy.deepcopy(dict(loop))
    return _normalize_value(payload)


def assert_repair_loop_terminal(loop: AutonomousRepairLoopResult | str) -> bool:
    current = get_repair_loop(loop)
    if not current.terminal and current.final_state not in TERMINAL_REPAIR_STATES:
        raise AssertionError("repair loop terminal state is not explicit")
    return True


def assert_repair_loop_bounded(loop: AutonomousRepairLoopResult | str) -> bool:
    current = get_repair_loop(loop)
    applied = [attempt for attempt in current.attempts if attempt.state is AutonomousRepairState.REPAIR_APPLIED]
    if len(applied) > current.max_attempts:
        raise AssertionError("repair loop exceeded max attempts")
    strategies = [
        attempt.strategy
        for attempt in current.attempts
        if attempt.strategy and attempt.state is AutonomousRepairState.REPAIR_PROPOSED
    ]
    if len(strategies) != len(set(strategies)) and current.final_state not in {AutonomousRepairState.REQUIRES_HUMAN_REVIEW, AutonomousRepairState.BLOCKED}:
        raise AssertionError("repair loop oscillation not stopped")
    return True


def assert_repair_loop_preserves_lineage(loop: AutonomousRepairLoopResult | str) -> bool:
    current = get_repair_loop(loop)
    for tx_id in current.transaction_refs:
        tx = get_transaction(tx_id)
        if current.source_transaction_id and tx.transaction_id == current.source_transaction_id:
            raise AssertionError("repair-created transaction overwrote source transaction")
        if current.source_transaction_id and tx.original_transaction_id != current.source_transaction_id:
            raise AssertionError("repair transaction source lineage missing")
        if getattr(tx, "repair_loop_id", "") != current.loop_id:
            raise AssertionError("repair transaction loop lineage missing")
    return True


def _terminal(
    current: AutonomousRepairLoopResult,
    *,
    state: AutonomousRepairState,
    decision: AutonomousRepairDecision,
    reason: str,
    diagnosis: Mapping[str, Any] | None = None,
    repair_strategy: Mapping[str, Any] | None = None,
    invariant_ref: str = "",
) -> AutonomousRepairLoopResult:
    evidence_id = _repair_evidence("terminal", loop_id=current.loop_id, task_id=current.task_id, step_id=current.step_id, trace_id=current.trace_id, state=state.value, reason=reason)
    attempt = _attempt(current, state, decision, reason=reason, evidence_id=evidence_id)
    updated = _replace(
        current,
        diagnosis=dict(diagnosis or current.diagnosis),
        repair_strategy=dict(repair_strategy or current.repair_strategy),
        attempts=(*current.attempts, attempt),
        final_state=state,
        terminal=True,
        evidence_refs=_append(current.evidence_refs, evidence_id),
        invariant_refs=_append(current.invariant_refs, invariant_ref),
    )
    return _store(_with_digest(updated))


def _replace(current: AutonomousRepairLoopResult, **updates: Any) -> AutonomousRepairLoopResult:
    return replace(current, **updates, updated_at=_now())


def _attempt(
    current: AutonomousRepairLoopResult,
    state: AutonomousRepairState,
    decision: AutonomousRepairDecision,
    *,
    strategy: str = "",
    reason: str = "",
    verification_result: Mapping[str, Any] | None = None,
    transaction_id: str = "",
    recovery_attempt_id: str = "",
    evidence_id: str = "",
) -> AutonomousRepairAttempt:
    return AutonomousRepairAttempt(
        attempt_id=_attempt_id(current.loop_id, len(current.attempts) + 1, state.value),
        loop_id=current.loop_id,
        state=state,
        decision=decision,
        strategy=strategy,
        reason=reason,
        verification_result=dict(verification_result or {}),
        transaction_id=transaction_id,
        recovery_attempt_id=recovery_attempt_id,
        evidence_id=evidence_id,
        created_at=_now(),
        updated_at=_now(),
    )


def _strategy_exhausted(current: AutonomousRepairLoopResult, strategy_id: str) -> bool:
    if current.max_attempts <= 0:
        return True
    prior = [attempt for attempt in current.attempts if attempt.strategy == strategy_id]
    return len(prior) >= current.max_attempts


def _last_transaction(current: AutonomousRepairLoopResult) -> RuntimeTransaction | None:
    if not current.transaction_refs:
        return None
    try:
        return get_transaction(current.transaction_refs[-1])
    except Exception:
        return None


def _repair_evidence(
    phase: str,
    *,
    loop_id: str,
    task_id: str,
    step_id: str,
    trace_id: str,
    state: str,
    reason: str,
    transaction_id: str = "",
) -> str:
    try:
        from core.runtime.runtime_evidence_freeze import RuntimeEvidenceKind, create_evidence_record

        kind = getattr(RuntimeEvidenceKind, "REPAIR", RuntimeEvidenceKind.AUDIT)
        return create_evidence_record(
            kind=kind,
            task_id=task_id,
            step_id=step_id,
            trace_id=trace_id,
            transaction_id=transaction_id,
            decision=phase,
            state=state,
            reason=reason,
            refs=[loop_id],
        ).evidence_id
    except Exception:
        return _stable_id("repair_evidence", loop_id, phase, state, reason)


def _with_digest(loop: AutonomousRepairLoopResult) -> AutonomousRepairLoopResult:
    payload = loop.to_dict()
    payload.pop("normalized_digest", None)
    return replace(loop, normalized_digest=_digest(payload))


def _store(loop: AutonomousRepairLoopResult) -> AutonomousRepairLoopResult:
    _LOOPS[loop.loop_id] = loop
    if loop.terminal or loop.final_state in TERMINAL_REPAIR_STATES:
        try:
            from core.runtime.runtime_memory_engine import append_runtime_memory, memory_records_for_repair_loop

            for record in memory_records_for_repair_loop(loop):
                append_runtime_memory(record)
        except Exception:
            pass
    return loop


def _latest_violation_ref() -> str:
    try:
        from core.runtime.runtime_constitution_freeze import list_runtime_invariant_violations

        violations = list_runtime_invariant_violations()
        if violations:
            return violations[-1].invariant.value
    except Exception:
        pass
    return ""


def _prediction_refs_for_repair(current: AutonomousRepairLoopResult, strategy: Mapping[str, Any]) -> tuple[str, ...]:
    refs = _text_tuple(strategy.get("prediction_refs"))
    if refs:
        return refs
    try:
        from core.runtime.runtime_prediction_engine import predict_repair_outcome

        prediction = predict_repair_outcome(
            {
                "task_id": current.task_id,
                "step_id": current.step_id,
                "trace_id": current.trace_id,
                "source_transaction_id": current.source_transaction_id,
                "source_replay_run_id": current.source_replay_run_id,
                "source_recovery_attempt_id": current.source_recovery_attempt_id,
                "source_repair_loop_id": current.loop_id,
                "failure_signature": current.source_failure_id,
                "repair_strategy": strategy.get("strategy_id") or "",
            }
        )
        return (prediction.prediction_id,)
    except Exception:
        return ()


def _result_ok(result: Mapping[str, Any] | None) -> bool:
    if not isinstance(result, Mapping):
        return False
    if result.get("ok") is False or result.get("allowed") is False:
        return False
    return bool(result.get("ok") or result.get("allowed") or result.get("verification_ok") or result.get("committed"))


def _append(values: Any, *items: Any) -> tuple[str, ...]:
    existing = list(_text_tuple(values))
    for item in items:
        for text in _text_tuple(item):
            if text and text not in existing:
                existing.append(text)
    return tuple(existing)


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


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _attempt_id(loop_id: str, ordinal: int, state: str) -> str:
    return _stable_id("repair_attempt", loop_id, ordinal, state)


def _stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}:{hashlib.sha256(repr(parts).encode('utf-8', errors='replace')).hexdigest()[:16]}"


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized = {}
        for key in sorted(value):
            if key in {"created_at", "updated_at", "timestamp", "started_at", "finished_at"}:
                continue
            normalized[str(key)] = _normalize_value(value[key])
        return normalized
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
