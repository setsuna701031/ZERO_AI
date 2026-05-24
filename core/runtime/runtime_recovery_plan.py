from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


RECOVERY_STATUS_PLANNED = "planned"
RECOVERY_STATUS_ROLLBACK_REQUIRED = "rollback_required"
RECOVERY_STATUS_UNRECOVERABLE = "unrecoverable"

ROLLBACK_REQUIRING_FAILURE_TYPES = {
    "mutation_failed",
    "patch_apply_failed",
    "transaction_failed",
    "seal_mismatch",
    "integrity_mismatch",
    "unsafe_mutation",
    "partial_apply",
    "write_failure",
}

UNRECOVERABLE_FAILURE_TYPES = {
    "approval_denied",
    "unsafe_action_blocked",
    "policy_blocked",
    "scope_violation",
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_recovery_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _string(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text or default


@dataclass(frozen=True)
class RuntimeRecoveryFailure:
    failure_type: str
    message: str = ""
    source: str = "runtime"
    status: str = "failed"
    source_session_id: str = ""
    task_id: str = ""
    step_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_type": self.failure_type,
            "message": self.message,
            "source": self.source,
            "status": self.status,
            "source_session_id": self.source_session_id,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class RuntimeRecoveryAction:
    action_id: str
    action_type: str
    reason: str
    required: bool = True
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "reason": self.reason,
            "required": self.required,
            "payload": copy.deepcopy(self.payload),
            "status": self.status,
        }


@dataclass(frozen=True)
class RuntimeRecoveryPlan:
    plan_id: str
    recovery_id: str
    source_session_id: str
    source_failure: RuntimeRecoveryFailure
    status: str
    rollback_required: bool
    replay_required: bool
    verification_required: bool
    actions: list[RuntimeRecoveryAction] = field(default_factory=list)
    replay_reference: dict[str, Any] = field(default_factory=dict)
    rollback_reference: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "source_failure": self.source_failure.to_dict(),
            "status": self.status,
            "rollback_required": self.rollback_required,
            "replay_required": self.replay_required,
            "verification_required": self.verification_required,
            "actions": [action.to_dict() for action in self.actions],
            "replay_reference": copy.deepcopy(self.replay_reference),
            "rollback_reference": copy.deepcopy(self.rollback_reference),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class RuntimeRecoveryPlanReport:
    ok: bool
    plan: RuntimeRecoveryPlan
    status: str
    rollback_required: bool
    replay_required: bool
    verification_required: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["plan"] = self.plan.to_dict()
        return payload


class RuntimeRecoveryPlanEvaluator:
    def evaluate(
        self,
        *,
        recovery_id: str,
        source_failure: Any,
        source_session_id: str = "",
        task_id: str = "",
        replay_reference: dict[str, Any] | None = None,
        rollback_reference: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryPlanReport:
        plan = build_runtime_recovery_plan(
            recovery_id=recovery_id,
            source_failure=source_failure,
            source_session_id=source_session_id,
            task_id=task_id,
            replay_reference=replay_reference,
            rollback_reference=rollback_reference,
            metadata=metadata,
        )

        return RuntimeRecoveryPlanReport(
            ok=plan.status != RECOVERY_STATUS_UNRECOVERABLE,
            plan=plan,
            status=plan.status,
            rollback_required=plan.rollback_required,
            replay_required=plan.replay_required,
            verification_required=plan.verification_required,
            errors=[] if plan.status != RECOVERY_STATUS_UNRECOVERABLE else ["runtime_recovery_unrecoverable"],
            warnings=[],
            metadata=copy.deepcopy(plan.metadata),
        )


def normalize_runtime_failure(
    source_failure: Any,
    *,
    source_session_id: str = "",
    task_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> RuntimeRecoveryFailure:
    if isinstance(source_failure, RuntimeRecoveryFailure):
        merged_metadata = source_failure.metadata
        if metadata:
            merged_metadata = {**merged_metadata, **dict(metadata)}
        return RuntimeRecoveryFailure(
            failure_type=source_failure.failure_type,
            message=source_failure.message,
            source=source_failure.source,
            status=source_failure.status,
            source_session_id=source_failure.source_session_id or source_session_id,
            task_id=source_failure.task_id or task_id,
            step_id=source_failure.step_id,
            payload=source_failure.payload,
            metadata=merged_metadata,
            observed_at=source_failure.observed_at,
        )

    payload = _copy_dict(source_failure)
    failure_type = _string(
        payload.get("failure_type")
        or payload.get("type")
        or payload.get("reason")
        or payload.get("error_type"),
        "runtime_failure",
    )
    message = _string(
        payload.get("failure_message")
        or payload.get("message")
        or payload.get("error")
        or payload.get("reason"),
        failure_type,
    )
    resolved_source_session_id = _string(
        payload.get("source_session_id") or payload.get("session_id"),
        source_session_id,
    )
    resolved_task_id = _string(payload.get("task_id"), task_id)

    return RuntimeRecoveryFailure(
        failure_type=failure_type,
        message=message,
        source=_string(payload.get("source"), "runtime"),
        status=_string(payload.get("status"), "failed"),
        source_session_id=resolved_source_session_id,
        task_id=resolved_task_id,
        step_id=_string(payload.get("step_id") or payload.get("step_index")),
        payload=payload,
        metadata={**_copy_dict(payload.get("metadata")), **dict(metadata or {})},
    )


def build_runtime_recovery_plan(
    *,
    recovery_id: str,
    source_failure: Any,
    source_session_id: str = "",
    task_id: str = "",
    replay_reference: dict[str, Any] | None = None,
    rollback_reference: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeRecoveryPlan:
    failure = normalize_runtime_failure(
        source_failure,
        source_session_id=source_session_id,
        task_id=task_id,
        metadata=metadata,
    )

    failure_type = failure.failure_type.strip().lower()

    rollback_required = bool(
        failure_type in ROLLBACK_REQUIRING_FAILURE_TYPES
        or failure.payload.get("rollback_required") is True
        or failure.metadata.get("rollback_required") is True
    )

    unrecoverable = bool(
        failure_type in UNRECOVERABLE_FAILURE_TYPES
        or failure.payload.get("unrecoverable") is True
        or failure.metadata.get("unrecoverable") is True
    )

    replay_required = not unrecoverable
    verification_required = not unrecoverable

    status = RECOVERY_STATUS_PLANNED

    if rollback_required:
        status = RECOVERY_STATUS_ROLLBACK_REQUIRED

    if unrecoverable:
        status = RECOVERY_STATUS_UNRECOVERABLE

    seed = {
        "recovery_id": recovery_id,
        "source_session_id": failure.source_session_id,
        "failure": failure.to_dict(),
    }

    plan_id = "runtime-recovery-plan-" + stable_recovery_fingerprint(seed)[:16]

    actions: list[RuntimeRecoveryAction] = [
        RuntimeRecoveryAction(
            action_id=f"{plan_id}-detect",
            action_type="detect_failure",
            reason="capture source runtime failure",
            payload={"failure_type": failure.failure_type, "source": failure.source},
            status="completed",
        ),
        RuntimeRecoveryAction(
            action_id=f"{plan_id}-plan",
            action_type="build_recovery_plan",
            reason="derive recovery route from failure metadata",
            payload={"rollback_required": rollback_required, "unrecoverable": unrecoverable},
            status="completed",
        ),
    ]

    if replay_required:
        actions.append(
            RuntimeRecoveryAction(
                action_id=f"{plan_id}-replay",
                action_type="attach_replay_evidence",
                reason="replay evidence is required before recovery verification",
                payload=copy.deepcopy(replay_reference or {}),
            )
        )

    if rollback_required:
        actions.append(
            RuntimeRecoveryAction(
                action_id=f"{plan_id}-rollback",
                action_type="prepare_rollback",
                reason="failure can leave partial runtime mutation state",
                payload=copy.deepcopy(rollback_reference or {"mode": "manual_or_governed_rollback"}),
            )
        )

    if verification_required:
        actions.append(
            RuntimeRecoveryAction(
                action_id=f"{plan_id}-verify",
                action_type="verify_recovery",
                reason="recovery chain must be verified before continuation",
            )
        )

    if unrecoverable:
        actions.append(
            RuntimeRecoveryAction(
                action_id=f"{plan_id}-stop",
                action_type="mark_unrecoverable",
                reason="policy or approval state prevents automatic recovery",
                status="completed",
            )
        )

    return RuntimeRecoveryPlan(
        plan_id=plan_id,
        recovery_id=str(recovery_id or plan_id),
        source_session_id=failure.source_session_id or str(source_session_id or ""),
        source_failure=failure,
        status=status,
        rollback_required=rollback_required,
        replay_required=replay_required,
        verification_required=verification_required,
        actions=actions,
        replay_reference=copy.deepcopy(replay_reference or {}),
        rollback_reference=copy.deepcopy(rollback_reference or {}),
        metadata=copy.deepcopy(metadata or {}),
    )


def evaluate_runtime_recovery_plan(
    *,
    recovery_id: str,
    source_failure: Any,
    source_session_id: str = "",
    task_id: str = "",
    replay_reference: dict[str, Any] | None = None,
    rollback_reference: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeRecoveryPlanReport:
    return RuntimeRecoveryPlanEvaluator().evaluate(
        recovery_id=recovery_id,
        source_failure=source_failure,
        source_session_id=source_session_id,
        task_id=task_id,
        replay_reference=replay_reference,
        rollback_reference=rollback_reference,
        metadata=metadata,
    )


def runtime_recovery_plan_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    to_dict = getattr(value, "to_dict", None)

    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return payload

    if isinstance(value, dict):
        return copy.deepcopy(value)

    return {
        "plan_id": _string(getattr(value, "plan_id", "")),
        "status": _string(getattr(value, "status", "")),
    }


class RuntimeRecoveryPlanReportCompat:
    """Read-only compatibility report for the recovery planner API."""

    SCHEMA = "zero.runtime.recovery_plan.compat.v1"

    def __init__(self, payload: Any = None, **kwargs: Any) -> None:
        if isinstance(payload, dict) and not kwargs:
            normalized = copy.deepcopy(payload)
        else:
            normalized = self._payload_from_kwargs(payload, kwargs)
        normalized.setdefault("schema", self.SCHEMA)
        normalized.setdefault("read_only", True)
        normalized.setdefault("executes_recovery", False)
        normalized.setdefault("executes_rollback", False)
        normalized.setdefault("executes_repair", False)
        normalized.setdefault("rollback_plans", [])
        normalized.setdefault("replay_reconstruction_plans", [])
        normalized.setdefault("failed_execution_plans", [])
        normalized.setdefault("lineage_isolation_plans", [])
        normalized.setdefault("recovery_sequence", [])
        normalized["fingerprint"] = stable_recovery_fingerprint(
            {key: value for key, value in normalized.items() if key != "fingerprint"}
        )
        self._payload = self._json_safe(normalized)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def to_dict(self) -> dict[str, Any]:
        return self.payload

    def rollback_plans(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("rollback_plans", []))

    def replay_reconstruction_plans(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("replay_reconstruction_plans", []))

    def failed_execution_plans(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("failed_execution_plans", []))

    def lineage_isolation_plans(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("lineage_isolation_plans", []))

    def recovery_sequence(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("recovery_sequence", []))

    def _payload_from_kwargs(self, plan: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        plan_payload = runtime_recovery_plan_to_dict(plan or kwargs.get("plan"))
        return {
            "ok": bool(kwargs.get("ok", True)),
            "plan": plan_payload,
            "status": str(kwargs.get("status") or plan_payload.get("status") or ""),
            "rollback_required": bool(kwargs.get("rollback_required", False)),
            "replay_required": bool(kwargs.get("replay_required", False)),
            "verification_required": bool(kwargs.get("verification_required", False)),
            "errors": copy.deepcopy(kwargs.get("errors", [])),
            "warnings": copy.deepcopy(kwargs.get("warnings", [])),
            "metadata": copy.deepcopy(kwargs.get("metadata", {})),
        }

    def _json_safe(self, payload: Any) -> dict[str, Any]:
        encoded = json.dumps(payload if isinstance(payload, dict) else {}, default=str, sort_keys=True)
        return json.loads(encoded)


RuntimeRecoveryPlanReport = RuntimeRecoveryPlanReportCompat


class _RuntimeRecoveryPolicyEvaluatorCompat:
    def __init__(
        self,
        *,
        reasoner: Any = None,
        replay_trust_threshold: int = 90,
        replay_warn_threshold: int = 75,
    ) -> None:
        if reasoner is None:
            from core.runtime.runtime_recovery_reasoning import RuntimeRecoveryReasoner

            reasoner = RuntimeRecoveryReasoner()
        self.reasoner = reasoner
        self.replay_trust_threshold = int(replay_trust_threshold)
        self.replay_warn_threshold = int(replay_warn_threshold)

    def evaluate(self, source: Any) -> Any:
        return _RuntimeRecoveryPolicyReportCompat(
            self.reasoner.reason(source),
            replay_trust_threshold=self.replay_trust_threshold,
            replay_warn_threshold=self.replay_warn_threshold,
        )


class _RuntimeRecoveryPolicyReportCompat:
    def __init__(
        self,
        reasoning: Any,
        *,
        replay_trust_threshold: int = 90,
        replay_warn_threshold: int = 75,
    ) -> None:
        self.reasoning = reasoning
        self.replay_trust_threshold = int(replay_trust_threshold)
        self.replay_warn_threshold = int(replay_warn_threshold)
        payload = self._build_payload(reasoning)
        payload["fingerprint"] = stable_recovery_fingerprint(payload)
        self._payload = payload

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def to_dict(self) -> dict[str, Any]:
        return self.payload

    def lineage_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("lineage_policy", {}))

    def trust_threshold_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("trust_threshold_policy", {}))

    def replay_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_policy", {}))

    def rollback_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("rollback_policy", {}))

    def failed_execution_policy(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("failed_execution_policy", {}))

    def action_classification(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("action_classification", {}))

    def policy_decisions(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("policy_decisions", []))

    def _build_payload(self, reasoning: Any) -> dict[str, Any]:
        reason_payload = getattr(reasoning, "payload", {})
        if not isinstance(reason_payload, dict):
            reason_payload = {}
        lineage = reasoning.lineage_trust() if hasattr(reasoning, "lineage_trust") else {}
        replay_trust = reasoning.replay_trust() if hasattr(reasoning, "replay_trust") else {}
        replay_safety = reasoning.replay_safety() if hasattr(reasoning, "replay_safety") else {}
        rollback_candidates = (
            reasoning.rollback_candidates() if hasattr(reasoning, "rollback_candidates") else []
        )
        failed = (
            reasoning.failed_execution_recovery()
            if hasattr(reasoning, "failed_execution_recovery")
            else {}
        )
        missing_evidence = replay_trust.get("classification") == "missing_evidence"
        unsafe_lineage = lineage.get("classification") not in {"trusted", "partial"}

        lineage_policy = {
            "policy": "lineage",
            "decision": "block" if missing_evidence or unsafe_lineage else "allow",
            "reason": "missing_evidence" if missing_evidence else "unsafe_lineage" if unsafe_lineage else "lineage_safe",
        }
        score = int(replay_trust.get("score", 0) or 0)
        threshold_decision = "allow"
        if missing_evidence:
            threshold_decision = "block"
        elif score < self.replay_trust_threshold:
            threshold_decision = "warn" if score >= self.replay_warn_threshold else "block"
        trust_threshold_policy = {
            "policy": "trust_threshold",
            "decision": threshold_decision,
            "score": score,
            "required_score": self.replay_trust_threshold,
        }
        replay_decision = "block" if lineage_policy["decision"] == "block" else threshold_decision
        replay_policy = {
            "policy": "replay",
            "decision": replay_decision,
            "reason": "replay_allowed_with_policy_warning" if replay_decision == "warn" else "replay_blocked" if replay_decision == "block" else "replay_allowed",
            "replay_safety": replay_safety.get("classification", ""),
        }
        rollback_policy = {
            "policy": "rollback",
            "decision": "block" if replay_decision == "block" else "allow",
            "candidate_count": 0 if replay_decision == "block" else len(rollback_candidates),
            "allowed_count": 0 if replay_decision == "block" else len(rollback_candidates),
            "candidates": [
                {**copy.deepcopy(candidate), "decision": "allow", "executes_action": False}
                for candidate in rollback_candidates
            ]
            if replay_decision != "block"
            else [],
        }
        failed_candidates = copy.deepcopy(failed.get("candidates", [])) if isinstance(failed, dict) else []
        failed_policy = {
            "policy": "failed_execution",
            "decision": "block" if replay_decision == "block" else "allow",
            "failed_execution_count": int(failed.get("failed_execution_count", 0) or 0) if isinstance(failed, dict) else 0,
            "candidate_count": 0 if replay_decision == "block" else len(failed_candidates),
            "candidates": [
                {**candidate, "decision": "allow", "executes_action": False}
                for candidate in failed_candidates
                if isinstance(candidate, dict)
            ]
            if replay_decision != "block"
            else [],
        }
        classification = "block" if replay_decision == "block" else "allow"
        decisions = [lineage_policy, trust_threshold_policy, replay_policy, rollback_policy, failed_policy]
        return {
            "ok": True,
            "schema": "zero.runtime.recovery_policy.compat.v1",
            "read_only": True,
            "reasoning": copy.deepcopy(reason_payload),
            "lineage_policy": lineage_policy,
            "trust_threshold_policy": trust_threshold_policy,
            "replay_policy": replay_policy,
            "rollback_policy": rollback_policy,
            "failed_execution_policy": failed_policy,
            "action_classification": {"classification": classification},
            "policy_decisions": decisions,
        }


class RuntimeRecoveryPlanner:
    """Compatibility planner facade over replay reconstruction and policy reports."""

    def __init__(self, *, policy_evaluator: Any = None) -> None:
        self.policy_evaluator = (
            policy_evaluator if policy_evaluator is not None else _RuntimeRecoveryPolicyEvaluatorCompat()
        )

    def plan(self, source: Any) -> RuntimeRecoveryPlanReport:
        policy = self._policy_report(source)
        payload = policy.payload if hasattr(policy, "payload") else {}
        rollback_plans = self._rollback_plans(policy)
        replay_plans = self._replay_plans(policy)
        failed_plans = self._failed_execution_plans(policy)
        isolation_plans = self._lineage_isolation_plans(policy)
        sequence = self._recovery_sequence(
            replay_plans=replay_plans,
            rollback_plans=rollback_plans,
            failed_plans=failed_plans,
            isolation_plans=isolation_plans,
        )
        report_payload = {
            "ok": not bool(isolation_plans),
            "schema": RuntimeRecoveryPlanReport.SCHEMA,
            "read_only": True,
            "source_policy_fingerprint": getattr(policy, "fingerprint", ""),
            "policy": payload,
            "rollback_plans": rollback_plans,
            "replay_reconstruction_plans": replay_plans,
            "failed_execution_plans": failed_plans,
            "lineage_isolation_plans": isolation_plans,
            "recovery_sequence": sequence,
        }
        return RuntimeRecoveryPlanReport(report_payload)

    def _policy_report(self, source: Any) -> Any:
        if hasattr(source, "lineage_policy") and hasattr(source, "replay_policy"):
            return source
        return self.policy_evaluator.evaluate(source)

    def _rollback_plans(self, policy: Any) -> list[dict[str, Any]]:
        rollback = policy.rollback_policy()
        if rollback.get("decision") != "allow":
            return []
        candidates = rollback.get("candidates") if isinstance(rollback.get("candidates"), list) else []
        plans = []
        for index, candidate in enumerate(candidates):
            execution_id = _string(candidate.get("execution_id"), f"rollback:{index}") if isinstance(candidate, dict) else f"rollback:{index}"
            plan = {
                "plan_id": f"rollback:{execution_id}",
                "plan_type": "rollback",
                "classification": "runtime_recovery_rollback",
                "policy_decision": "allow",
                "execution_id": execution_id,
                "rollback_id": _string(candidate.get("rollback_id") if isinstance(candidate, dict) else "", "rollback"),
                "replay_order": index,
                "stages": ["prepare_rollback", "verify_rollback"],
                "action": "none",
                "executes_action": False,
            }
            plans.append(plan)
        return plans

    def _replay_plans(self, policy: Any) -> list[dict[str, Any]]:
        replay = policy.replay_policy()
        if replay.get("decision") == "block":
            return []
        return [
            {
                "plan_id": "replay:reconstruction",
                "plan_type": "replay_reconstruction",
                "classification": "runtime_recovery_replay",
                "policy_decision": replay.get("decision", "allow"),
                "replay_safety": replay.get("replay_safety", "replay_safe"),
                "trust_score": policy.trust_threshold_policy().get("score", 0),
                "stages": ["collect_evidence", "reconstruct_state", "verify_replay"],
                "action": "none",
                "executes_action": False,
            }
        ]

    def _failed_execution_plans(self, policy: Any) -> list[dict[str, Any]]:
        failed = policy.failed_execution_policy()
        if failed.get("decision") != "allow":
            return []
        plans = []
        for candidate in failed.get("candidates", []) if isinstance(failed.get("candidates"), list) else []:
            if not isinstance(candidate, dict):
                continue
            failed_id = _string(candidate.get("failed_execution_id"))
            if not failed_id:
                continue
            plans.append(
                {
                    "plan_id": f"failed-execution:{failed_id}",
                    "plan_type": "failed_execution_recovery",
                    "classification": "runtime_failed_execution_recovery",
                    "policy_decision": "allow",
                    "failed_execution_id": failed_id,
                    "status": _string(candidate.get("status"), "failed"),
                    "phase": _string(candidate.get("phase")),
                    "stages": ["classify_failure", "verify_recovery"],
                    "action": "none",
                    "executes_action": False,
                }
            )
        return plans

    def _lineage_isolation_plans(self, policy: Any) -> list[dict[str, Any]]:
        lineage = policy.lineage_policy()
        if lineage.get("decision") != "block":
            return []
        missing = lineage.get("reason") == "missing_evidence"
        return [
            {
                "plan_id": "lineage:isolation",
                "plan_type": "lineage_isolation",
                "classification": "missing_evidence_isolation_plan" if missing else "unsafe_lineage_isolation_plan",
                "policy_decision": "block",
                "reason": lineage.get("reason", "unsafe_lineage"),
                "action": "none",
                "executes_action": False,
            }
        ]

    def _recovery_sequence(
        self,
        *,
        replay_plans: list[dict[str, Any]],
        rollback_plans: list[dict[str, Any]],
        failed_plans: list[dict[str, Any]],
        isolation_plans: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        sequence: list[dict[str, Any]] = []
        for plan in isolation_plans:
            sequence.append({**copy.deepcopy(plan), "stage_type": "lineage_isolation"})
        for plan in replay_plans:
            sequence.append({**copy.deepcopy(plan), "stage_type": "replay_reconstruction"})
        for plan in rollback_plans:
            sequence.append({**copy.deepcopy(plan), "stage_type": "rollback"})
        for plan in failed_plans:
            sequence.append({**copy.deepcopy(plan), "stage_type": "failed_execution_recovery"})
        for index, item in enumerate(sequence):
            item["sequence_order"] = index
            item.setdefault("action", "none")
            item.setdefault("executes_action", False)
        return sequence


__all__ = [
    "RECOVERY_STATUS_PLANNED",
    "RECOVERY_STATUS_ROLLBACK_REQUIRED",
    "RECOVERY_STATUS_UNRECOVERABLE",
    "RuntimeRecoveryAction",
    "RuntimeRecoveryFailure",
    "RuntimeRecoveryPlan",
    "RuntimeRecoveryPlanReport",
    "RuntimeRecoveryPlanEvaluator",
    "RuntimeRecoveryPlanner",
    "build_runtime_recovery_plan",
    "evaluate_runtime_recovery_plan",
    "runtime_recovery_plan_to_dict",
    "normalize_runtime_failure",
    "stable_recovery_fingerprint",
    "utc_timestamp",
]
