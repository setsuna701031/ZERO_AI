from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_recovery_policy import (
    POLICY_ALLOW,
    POLICY_BLOCK,
    POLICY_WARN,
    RuntimeRecoveryPolicyEvaluator,
    RuntimeRecoveryPolicyReport,
)
from core.runtime.runtime_recovery_reasoning import (
    RuntimeRecoveryReasoningReport,
)


PLAN_ALLOWED_DECISIONS = {POLICY_ALLOW, POLICY_WARN}


class RuntimeRecoveryPlanReport:
    SCHEMA = "zero.runtime.recovery_plan.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

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

    def recommendations(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("recommendations", []))

    def _json_safe(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        encoded = json.dumps(
            payload,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return json.loads(encoded)


class RuntimeRecoveryPlanner:
    """Deterministic recovery plan generation from recovery policy outputs."""

    def __init__(
        self,
        *,
        policy_evaluator: RuntimeRecoveryPolicyEvaluator | None = None,
    ) -> None:
        self.policy_evaluator = policy_evaluator if policy_evaluator is not None else RuntimeRecoveryPolicyEvaluator()

    def plan(self, source: Any) -> RuntimeRecoveryPlanReport:
        context = self._context(source)
        policy = context["policy"]
        reasoning = context["reasoning"]
        lineage_isolation_plans = self.generate_lineage_isolation_plans(policy, reasoning)
        replay_reconstruction_plans = self.generate_replay_reconstruction_plans(policy, reasoning)
        rollback_plans = self.generate_rollback_plans(policy, reasoning)
        failed_execution_plans = self.generate_failed_execution_recovery_plans(policy, reasoning)
        recovery_sequence = self.generate_replay_safe_sequence(
            lineage_isolation_plans=lineage_isolation_plans,
            replay_reconstruction_plans=replay_reconstruction_plans,
            failed_execution_plans=failed_execution_plans,
            rollback_plans=rollback_plans,
        )
        recommendations = self.generate_recovery_step_recommendations(recovery_sequence)
        payload = {
            "ok": True,
            "schema": RuntimeRecoveryPlanReport.SCHEMA,
            "mode": "planning_only",
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "source": {
                "policy_fingerprint": policy.fingerprint,
                "reasoning_fingerprint": reasoning.fingerprint,
            },
            "lineage_isolation_plans": lineage_isolation_plans,
            "replay_reconstruction_plans": replay_reconstruction_plans,
            "failed_execution_plans": failed_execution_plans,
            "rollback_plans": rollback_plans,
            "recovery_sequence": recovery_sequence,
            "recommendations": recommendations,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeRecoveryPlanReport(payload)

    def generate_rollback_plans(
        self,
        policy: RuntimeRecoveryPolicyReport | Any,
        reasoning: RuntimeRecoveryReasoningReport | None = None,
    ) -> list[dict[str, Any]]:
        policy_report = self._policy_report(policy)
        reasoning_report = self._reasoning_report(reasoning if reasoning is not None else policy)
        rollback_policy = policy_report.rollback_policy()
        policy_candidates = self._candidate_index(rollback_policy.get("candidates"))
        plans = []
        for candidate in reasoning_report.rollback_candidates():
            if not isinstance(candidate, dict):
                continue
            candidate_id = self._safe_text(candidate.get("candidate_id"))
            policy_candidate = policy_candidates.get(candidate_id, {})
            decision = self._safe_text(policy_candidate.get("decision"))
            if decision not in PLAN_ALLOWED_DECISIONS:
                continue
            plan = {
                "plan_id": f"plan:{candidate_id}",
                "plan_type": "rollback",
                "classification": "rollback_plan",
                "policy_decision": decision,
                "candidate_id": candidate_id,
                "execution_id": self._safe_text(candidate.get("execution_id")),
                "rollback_id": self._safe_text(candidate.get("rollback_id")),
                "replay_order": self._safe_int(candidate.get("replay_order"), 0),
                "stages": self._plan_stages(
                    [
                        "verify_replay_context",
                        "review_rollback_candidate",
                        "hold_for_external_authorization",
                    ]
                ),
                "action": "none",
                "executes_action": False,
            }
            plan["fingerprint"] = self._fingerprint(plan)
            plans.append(plan)
        return sorted(
            plans,
            key=lambda item: (
                self._safe_int(item.get("replay_order"), 0),
                self._safe_text(item.get("plan_id")),
            ),
        )

    def generate_replay_reconstruction_plans(
        self,
        policy: RuntimeRecoveryPolicyReport | Any,
        reasoning: RuntimeRecoveryReasoningReport | None = None,
    ) -> list[dict[str, Any]]:
        policy_report = self._policy_report(policy)
        reasoning_report = self._reasoning_report(reasoning if reasoning is not None else policy)
        replay_policy = policy_report.replay_policy()
        decision = self._safe_text(replay_policy.get("decision"))
        if decision not in PLAN_ALLOWED_DECISIONS:
            return []
        replay_safety = reasoning_report.replay_safety()
        replay_trust = reasoning_report.replay_trust()
        plan = {
            "plan_id": "plan:replay_reconstruction",
            "plan_type": "replay_reconstruction",
            "classification": "replay_reconstruction_plan",
            "policy_decision": decision,
            "replay_safety": self._safe_text(replay_safety.get("classification")),
            "trust_score": self._safe_int(replay_trust.get("score"), 0),
            "stages": self._plan_stages(
                [
                    "validate_replay_policy",
                    "reconstruct_replay_state",
                    "review_replay_candidates",
                ]
            ),
            "action": "none",
            "executes_action": False,
        }
        plan["fingerprint"] = self._fingerprint(plan)
        return [plan]

    def generate_failed_execution_recovery_plans(
        self,
        policy: RuntimeRecoveryPolicyReport | Any,
        reasoning: RuntimeRecoveryReasoningReport | None = None,
    ) -> list[dict[str, Any]]:
        policy_report = self._policy_report(policy)
        reasoning_report = self._reasoning_report(reasoning if reasoning is not None else policy)
        failed_policy = policy_report.failed_execution_policy()
        policy_candidates = self._candidate_index(failed_policy.get("candidates"))
        failed_reasoning = reasoning_report.failed_execution_recovery()
        raw_candidates = failed_reasoning.get("candidates")
        if not isinstance(raw_candidates, list):
            raw_candidates = []
        plans = []
        for candidate in raw_candidates:
            if not isinstance(candidate, dict):
                continue
            candidate_id = self._safe_text(candidate.get("candidate_id"))
            policy_candidate = policy_candidates.get(candidate_id, {})
            decision = self._safe_text(policy_candidate.get("decision"))
            if decision not in PLAN_ALLOWED_DECISIONS:
                continue
            plan = {
                "plan_id": f"plan:{candidate_id}",
                "plan_type": "failed_execution_recovery",
                "classification": "failed_execution_recovery_plan",
                "policy_decision": decision,
                "candidate_id": candidate_id,
                "failed_execution_id": self._safe_text(candidate.get("failed_execution_id")),
                "status": self._safe_text(candidate.get("status")),
                "phase": self._safe_text(candidate.get("phase")),
                "stages": self._plan_stages(
                    [
                        "isolate_failed_execution",
                        "reconstruct_failed_replay_context",
                        "recommend_manual_recovery_review",
                    ]
                ),
                "action": "none",
                "executes_action": False,
            }
            plan["fingerprint"] = self._fingerprint(plan)
            plans.append(plan)
        return sorted(plans, key=lambda item: self._safe_text(item.get("plan_id")))

    def generate_lineage_isolation_plans(
        self,
        policy: RuntimeRecoveryPolicyReport | Any,
        reasoning: RuntimeRecoveryReasoningReport | None = None,
    ) -> list[dict[str, Any]]:
        policy_report = self._policy_report(policy)
        reasoning_report = self._reasoning_report(reasoning if reasoning is not None else policy)
        lineage_policy = policy_report.lineage_policy()
        replay_policy = policy_report.replay_policy()
        if self._safe_text(lineage_policy.get("decision")) != POLICY_BLOCK:
            return []
        lineage = reasoning_report.lineage_trust()
        replay_trust = reasoning_report.replay_trust()
        missing_evidence = self._safe_text(replay_trust.get("classification")) == "missing_evidence"
        plan = {
            "plan_id": "plan:lineage_isolation",
            "plan_type": "lineage_isolation",
            "classification": "missing_evidence_isolation_plan" if missing_evidence else "unsafe_lineage_isolation_plan",
            "policy_decision": POLICY_BLOCK,
            "lineage_classification": self._safe_text(lineage.get("classification")),
            "replay_policy_reason": self._safe_text(replay_policy.get("reason")),
            "stages": self._plan_stages(
                [
                    "isolate_lineage_chain",
                    "block_recovery_action_plans",
                    "recommend_evidence_review",
                ]
            ),
            "action": "none",
            "executes_action": False,
        }
        plan["fingerprint"] = self._fingerprint(plan)
        return [plan]

    def generate_replay_safe_sequence(
        self,
        *,
        lineage_isolation_plans: list[dict[str, Any]],
        replay_reconstruction_plans: list[dict[str, Any]],
        failed_execution_plans: list[dict[str, Any]],
        rollback_plans: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        sequence = []
        for plan in self._safe_plan_list(lineage_isolation_plans):
            sequence.append(self._sequence_item(plan, "lineage_isolation"))
        for plan in self._safe_plan_list(replay_reconstruction_plans):
            sequence.append(self._sequence_item(plan, "replay_reconstruction"))
        for plan in self._safe_plan_list(failed_execution_plans):
            sequence.append(self._sequence_item(plan, "failed_execution_recovery"))
        for plan in self._safe_plan_list(rollback_plans):
            sequence.append(self._sequence_item(plan, "rollback"))
        ordered = []
        for index, item in enumerate(sequence):
            item["sequence_order"] = index
            item["fingerprint"] = self._fingerprint(item)
            ordered.append(item)
        return ordered

    def generate_recovery_step_recommendations(
        self,
        recovery_sequence: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        recommendations = []
        for item in self._safe_plan_list(recovery_sequence):
            recommendation = {
                "recommendation_id": f"recommend:{self._safe_text(item.get('plan_id'))}",
                "sequence_order": self._safe_int(item.get("sequence_order"), 0),
                "plan_id": self._safe_text(item.get("plan_id")),
                "plan_type": self._safe_text(item.get("plan_type")),
                "recommendation": self._recommendation_for(item),
                "action": "none",
                "executes_action": False,
            }
            recommendation["fingerprint"] = self._fingerprint(recommendation)
            recommendations.append(recommendation)
        return sorted(
            recommendations,
            key=lambda item: (
                self._safe_int(item.get("sequence_order"), 0),
                self._safe_text(item.get("recommendation_id")),
            ),
        )

    def _context(self, source: Any) -> dict[str, RuntimeRecoveryPolicyReport | RuntimeRecoveryReasoningReport]:
        if isinstance(source, RuntimeRecoveryPolicyReport):
            policy = RuntimeRecoveryPolicyReport(source.payload)
            reasoning = RuntimeRecoveryReasoningReport({})
            return {"policy": policy, "reasoning": reasoning}
        if isinstance(source, RuntimeRecoveryReasoningReport):
            reasoning = RuntimeRecoveryReasoningReport(source.payload)
            policy = self.policy_evaluator.evaluate(reasoning)
            return {"policy": policy, "reasoning": reasoning}
        reasoning = self.policy_evaluator.reasoner.reason(source)
        policy = self.policy_evaluator.evaluate(reasoning)
        return {"policy": policy, "reasoning": reasoning}

    def _policy_report(self, source: Any) -> RuntimeRecoveryPolicyReport:
        if isinstance(source, RuntimeRecoveryPolicyReport):
            return RuntimeRecoveryPolicyReport(source.payload)
        return self.policy_evaluator.evaluate(source)

    def _reasoning_report(self, source: Any) -> RuntimeRecoveryReasoningReport:
        if isinstance(source, RuntimeRecoveryReasoningReport):
            return RuntimeRecoveryReasoningReport(source.payload)
        return self.policy_evaluator.reasoner.reason(source)

    def _candidate_index(self, candidates: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(candidates, list):
            return {}
        return {
            self._safe_text(candidate.get("candidate_id")): copy.deepcopy(candidate)
            for candidate in candidates
            if isinstance(candidate, dict) and self._safe_text(candidate.get("candidate_id"))
        }

    def _plan_stages(self, stage_names: list[str]) -> list[dict[str, Any]]:
        stages = []
        for index, stage_name in enumerate(stage_names):
            stage = {
                "stage_order": index,
                "stage": stage_name,
                "action": "none",
                "executes_action": False,
            }
            stage["fingerprint"] = self._fingerprint(stage)
            stages.append(stage)
        return stages

    def _sequence_item(self, plan: dict[str, Any], stage_type: str) -> dict[str, Any]:
        return {
            "sequence_order": 0,
            "stage_type": stage_type,
            "plan_id": self._safe_text(plan.get("plan_id")),
            "plan_type": self._safe_text(plan.get("plan_type")),
            "policy_decision": self._safe_text(plan.get("policy_decision")),
            "action": "none",
            "executes_action": False,
        }

    def _recommendation_for(self, sequence_item: dict[str, Any]) -> str:
        stage_type = self._safe_text(sequence_item.get("stage_type"))
        if stage_type == "lineage_isolation":
            return "review isolated lineage before considering recovery"
        if stage_type == "replay_reconstruction":
            return "review reconstructed replay context before candidate selection"
        if stage_type == "failed_execution_recovery":
            return "review failed execution recovery candidate without executing repair"
        if stage_type == "rollback":
            return "review rollback candidate without executing rollback"
        return "review recovery plan item"

    def _safe_plan_list(self, value: Any) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in value
            if isinstance(item, dict)
        ] if isinstance(value, list) else []

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        safe = copy.deepcopy(payload)
        safe.pop("fingerprint", None)
        encoded = json.dumps(
            safe,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def plan_runtime_recovery(source: Any) -> RuntimeRecoveryPlanReport:
    return RuntimeRecoveryPlanner().plan(source)


__all__ = [
    "RuntimeRecoveryPlanReport",
    "RuntimeRecoveryPlanner",
    "plan_runtime_recovery",
]
