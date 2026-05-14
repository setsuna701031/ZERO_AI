from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_recovery_plan import RuntimeRecoveryPlanReport
from core.runtime.runtime_recovery_policy import POLICY_ALLOW, POLICY_BLOCK, POLICY_WARN


APPROVAL_APPROVE = "approve"
APPROVAL_DEFER = "defer"
APPROVAL_REJECT = "reject"


class RuntimeRecoveryApprovalReport:
    SCHEMA = "zero.runtime.recovery_approval.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def recovery_approval(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("recovery_approval", {}))

    def replay_approval(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_approval", {}))

    def rollback_approval(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("rollback_approval", {}))

    def failed_execution_approval(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("failed_execution_approval", {}))

    def consistency_check(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("consistency_check", {}))

    def approval_reasons(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("approval_reasons", []))

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


class RuntimeRecoveryApprovalEvaluator:
    """Read-only approval gates over recovery plan reports."""

    def evaluate(self, source: Any) -> RuntimeRecoveryApprovalReport:
        plan = self._plan_report(source)
        plan_payload = plan.payload
        consistency_check = self.check_policy_plan_consistency(plan)
        replay_approval = self.gate_replay_approval(
            plan,
            consistency_check=consistency_check,
        )
        rollback_approval = self.gate_rollback_approval(
            plan,
            replay_approval=replay_approval,
            consistency_check=consistency_check,
        )
        failed_execution_approval = self.gate_failed_execution_approval(
            plan,
            replay_approval=replay_approval,
            consistency_check=consistency_check,
        )
        recovery_approval = self.approve_recovery_plan(
            plan,
            consistency_check=consistency_check,
            replay_approval=replay_approval,
            rollback_approval=rollback_approval,
            failed_execution_approval=failed_execution_approval,
        )
        approval_reasons = self.report_approval_reasons(
            consistency_check=consistency_check,
            replay_approval=replay_approval,
            rollback_approval=rollback_approval,
            failed_execution_approval=failed_execution_approval,
            recovery_approval=recovery_approval,
        )
        payload = {
            "ok": True,
            "schema": RuntimeRecoveryApprovalReport.SCHEMA,
            "mode": "approval_only",
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "source": {
                "plan_fingerprint": plan.fingerprint,
                "policy_fingerprint": self._safe_text(
                    self._safe_mapping(plan_payload.get("source")).get("policy_fingerprint")
                ),
                "reasoning_fingerprint": self._safe_text(
                    self._safe_mapping(plan_payload.get("source")).get("reasoning_fingerprint")
                ),
            },
            "consistency_check": consistency_check,
            "replay_approval": replay_approval,
            "rollback_approval": rollback_approval,
            "failed_execution_approval": failed_execution_approval,
            "recovery_approval": recovery_approval,
            "approval_reasons": approval_reasons,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeRecoveryApprovalReport(payload)

    def approve_recovery_plan(
        self,
        plan: RuntimeRecoveryPlanReport | Any,
        *,
        consistency_check: dict[str, Any] | None = None,
        replay_approval: dict[str, Any] | None = None,
        rollback_approval: dict[str, Any] | None = None,
        failed_execution_approval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan_report = self._plan_report(plan)
        consistency_check = self._safe_mapping(consistency_check) if consistency_check is not None else self.check_policy_plan_consistency(plan_report)
        replay_approval = self._safe_mapping(replay_approval) if replay_approval is not None else self.gate_replay_approval(plan_report, consistency_check=consistency_check)
        rollback_approval = self._safe_mapping(rollback_approval) if rollback_approval is not None else self.gate_rollback_approval(plan_report, replay_approval=replay_approval, consistency_check=consistency_check)
        failed_execution_approval = self._safe_mapping(failed_execution_approval) if failed_execution_approval is not None else self.gate_failed_execution_approval(plan_report, replay_approval=replay_approval, consistency_check=consistency_check)

        approval_states = [
            self._safe_text(replay_approval.get("state")),
            self._safe_text(rollback_approval.get("state")),
            self._safe_text(failed_execution_approval.get("state")),
        ]
        if self._has_isolation(plan_report):
            state = APPROVAL_REJECT
            reason = "unsafe_recovery_isolated_lineage"
        elif consistency_check.get("state") == APPROVAL_REJECT:
            state = APPROVAL_REJECT
            reason = "policy_plan_consistency_rejected"
        elif APPROVAL_REJECT in approval_states:
            state = APPROVAL_REJECT
            reason = "one_or_more_approval_gates_rejected"
        elif APPROVAL_DEFER in approval_states:
            state = APPROVAL_DEFER
            reason = "one_or_more_approval_gates_deferred"
        elif self._has_action_plan(plan_report):
            state = APPROVAL_APPROVE
            reason = "recovery_plan_approval_granted"
        else:
            state = APPROVAL_DEFER
            reason = "no_recovery_action_plan"

        result = {
            "gate": "recovery_plan",
            "state": state,
            "reason": reason,
            "approval_can_be_granted": state == APPROVAL_APPROVE,
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def gate_replay_approval(
        self,
        plan: RuntimeRecoveryPlanReport | Any,
        *,
        consistency_check: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan_report = self._plan_report(plan)
        consistency_check = self._safe_mapping(consistency_check) if consistency_check is not None else self.check_policy_plan_consistency(plan_report)
        replay_plans = plan_report.replay_reconstruction_plans()
        decisions = self._policy_decisions(replay_plans)
        if self._has_isolation(plan_report):
            state = APPROVAL_REJECT
            reason = "unsafe_lineage_blocks_replay_approval"
        elif consistency_check.get("state") == APPROVAL_REJECT:
            state = APPROVAL_REJECT
            reason = "policy_plan_consistency_blocks_replay_approval"
        elif not replay_plans:
            state = APPROVAL_DEFER
            reason = "no_replay_plan"
        elif POLICY_BLOCK in decisions:
            state = APPROVAL_REJECT
            reason = "replay_plan_policy_blocked"
        elif POLICY_WARN in decisions:
            state = APPROVAL_DEFER
            reason = "replay_plan_policy_warning"
        else:
            state = APPROVAL_APPROVE
            reason = "replay_approval_granted"
        result = {
            "gate": "replay",
            "state": state,
            "reason": reason,
            "plan_count": len(replay_plans),
            "approval_can_be_granted": state == APPROVAL_APPROVE,
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def gate_rollback_approval(
        self,
        plan: RuntimeRecoveryPlanReport | Any,
        *,
        replay_approval: dict[str, Any] | None = None,
        consistency_check: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan_report = self._plan_report(plan)
        consistency_check = self._safe_mapping(consistency_check) if consistency_check is not None else self.check_policy_plan_consistency(plan_report)
        replay_approval = self._safe_mapping(replay_approval) if replay_approval is not None else self.gate_replay_approval(plan_report, consistency_check=consistency_check)
        rollback_plans = plan_report.rollback_plans()
        decisions = self._policy_decisions(rollback_plans)
        if self._has_isolation(plan_report):
            state = APPROVAL_REJECT
            reason = "unsafe_lineage_blocks_rollback_approval"
        elif consistency_check.get("state") == APPROVAL_REJECT:
            state = APPROVAL_REJECT
            reason = "policy_plan_consistency_blocks_rollback_approval"
        elif replay_approval.get("state") == APPROVAL_REJECT:
            state = APPROVAL_REJECT
            reason = "replay_gate_blocks_rollback_approval"
        elif not rollback_plans:
            state = APPROVAL_DEFER
            reason = "no_rollback_plan"
        elif POLICY_BLOCK in decisions:
            state = APPROVAL_REJECT
            reason = "rollback_plan_policy_blocked"
        elif POLICY_WARN in decisions or replay_approval.get("state") == APPROVAL_DEFER:
            state = APPROVAL_DEFER
            reason = "rollback_approval_deferred"
        else:
            state = APPROVAL_APPROVE
            reason = "rollback_approval_granted"
        result = {
            "gate": "rollback",
            "state": state,
            "reason": reason,
            "plan_count": len(rollback_plans),
            "approval_can_be_granted": state == APPROVAL_APPROVE,
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def gate_failed_execution_approval(
        self,
        plan: RuntimeRecoveryPlanReport | Any,
        *,
        replay_approval: dict[str, Any] | None = None,
        consistency_check: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan_report = self._plan_report(plan)
        consistency_check = self._safe_mapping(consistency_check) if consistency_check is not None else self.check_policy_plan_consistency(plan_report)
        replay_approval = self._safe_mapping(replay_approval) if replay_approval is not None else self.gate_replay_approval(plan_report, consistency_check=consistency_check)
        failed_plans = plan_report.failed_execution_plans()
        decisions = self._policy_decisions(failed_plans)
        if self._has_isolation(plan_report):
            state = APPROVAL_REJECT
            reason = "unsafe_lineage_blocks_failed_execution_approval"
        elif consistency_check.get("state") == APPROVAL_REJECT:
            state = APPROVAL_REJECT
            reason = "policy_plan_consistency_blocks_failed_execution_approval"
        elif replay_approval.get("state") == APPROVAL_REJECT:
            state = APPROVAL_REJECT
            reason = "replay_gate_blocks_failed_execution_approval"
        elif not failed_plans:
            state = APPROVAL_DEFER
            reason = "no_failed_execution_plan"
        elif POLICY_BLOCK in decisions:
            state = APPROVAL_REJECT
            reason = "failed_execution_plan_policy_blocked"
        elif POLICY_WARN in decisions or replay_approval.get("state") == APPROVAL_DEFER:
            state = APPROVAL_DEFER
            reason = "failed_execution_approval_deferred"
        else:
            state = APPROVAL_APPROVE
            reason = "failed_execution_approval_granted"
        result = {
            "gate": "failed_execution_recovery",
            "state": state,
            "reason": reason,
            "plan_count": len(failed_plans),
            "approval_can_be_granted": state == APPROVAL_APPROVE,
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def check_policy_plan_consistency(self, plan: RuntimeRecoveryPlanReport | Any) -> dict[str, Any]:
        plan_report = self._plan_report(plan)
        payload = plan_report.payload
        issues = []
        if payload.get("schema") != RuntimeRecoveryPlanReport.SCHEMA:
            issues.append(self._issue("invalid_plan_schema", "recovery approval requires a recovery plan report"))
        if not bool(payload.get("read_only", False)):
            issues.append(self._issue("plan_not_read_only", "recovery plan must be read-only"))
        for flag_name in ("executes_recovery", "executes_rollback", "executes_repair"):
            if bool(payload.get(flag_name, False)):
                issues.append(self._issue("plan_execution_flag_set", f"{flag_name} must be false", flag=flag_name))

        action_plans = (
            plan_report.replay_reconstruction_plans()
            + plan_report.rollback_plans()
            + plan_report.failed_execution_plans()
        )
        isolation_plans = plan_report.lineage_isolation_plans()
        if isolation_plans and action_plans:
            issues.append(self._issue("isolation_with_action_plans", "lineage isolation cannot coexist with action approval plans"))

        for plan_item in self._all_plan_items(plan_report):
            self._append_plan_item_issues(plan_item, issues)

        plan_index = {
            self._safe_text(item.get("plan_id")): item
            for item in self._all_plan_items(plan_report)
            if self._safe_text(item.get("plan_id"))
        }
        for sequence_item in plan_report.recovery_sequence():
            if not isinstance(sequence_item, dict):
                continue
            plan_id = self._safe_text(sequence_item.get("plan_id"))
            if plan_id not in plan_index:
                issues.append(self._issue("sequence_plan_missing", "recovery sequence references an unknown plan", plan_id=plan_id))
            if self._safe_text(sequence_item.get("action")) != "none" or bool(sequence_item.get("executes_action", False)):
                issues.append(self._issue("sequence_executes_action", "recovery sequence must not execute actions", plan_id=plan_id))

        state = APPROVAL_APPROVE if not issues else APPROVAL_REJECT
        result = {
            "gate": "policy_plan_consistency",
            "state": state,
            "reason": "policy_plan_consistent" if not issues else "policy_plan_mismatch",
            "issue_count": len(issues),
            "issues": issues,
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def report_approval_reasons(
        self,
        *,
        consistency_check: dict[str, Any],
        replay_approval: dict[str, Any],
        rollback_approval: dict[str, Any],
        failed_execution_approval: dict[str, Any],
        recovery_approval: dict[str, Any],
    ) -> list[dict[str, Any]]:
        reasons = []
        for gate in (
            consistency_check,
            replay_approval,
            rollback_approval,
            failed_execution_approval,
            recovery_approval,
        ):
            reason = {
                "gate": self._safe_text(gate.get("gate")),
                "state": self._safe_text(gate.get("state")),
                "reason": self._safe_text(gate.get("reason")),
                "action": "none",
                "executes_action": False,
            }
            reason["fingerprint"] = self._fingerprint(reason)
            reasons.append(reason)
        return reasons

    def _plan_report(self, source: Any) -> RuntimeRecoveryPlanReport:
        if isinstance(source, RuntimeRecoveryPlanReport):
            return RuntimeRecoveryPlanReport(source.payload)
        return RuntimeRecoveryPlanReport({})

    def _all_plan_items(self, plan: RuntimeRecoveryPlanReport) -> list[dict[str, Any]]:
        return (
            plan.lineage_isolation_plans()
            + plan.replay_reconstruction_plans()
            + plan.failed_execution_plans()
            + plan.rollback_plans()
        )

    def _append_plan_item_issues(self, plan_item: Any, issues: list[dict[str, Any]]) -> None:
        if not isinstance(plan_item, dict):
            issues.append(self._issue("invalid_plan_item", "plan item must be a mapping"))
            return
        plan_id = self._safe_text(plan_item.get("plan_id"))
        decision = self._safe_text(plan_item.get("policy_decision"))
        plan_type = self._safe_text(plan_item.get("plan_type"))
        if plan_type == "lineage_isolation":
            valid_decisions = {POLICY_BLOCK}
        else:
            valid_decisions = {POLICY_ALLOW, POLICY_WARN}
        if decision not in valid_decisions:
            issues.append(
                self._issue(
                    "policy_plan_decision_mismatch",
                    "plan policy decision is not valid for its plan type",
                    plan_id=plan_id,
                    policy_decision=decision,
                )
            )
        if self._safe_text(plan_item.get("action")) != "none" or bool(plan_item.get("executes_action", False)):
            issues.append(self._issue("plan_executes_action", "plan item must not execute actions", plan_id=plan_id))
        stages = plan_item.get("stages")
        if not isinstance(stages, list):
            stages = []
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            if self._safe_text(stage.get("action")) != "none" or bool(stage.get("executes_action", False)):
                issues.append(self._issue("stage_executes_action", "plan stage must not execute actions", plan_id=plan_id))

    def _has_isolation(self, plan: RuntimeRecoveryPlanReport) -> bool:
        return bool(plan.lineage_isolation_plans())

    def _has_action_plan(self, plan: RuntimeRecoveryPlanReport) -> bool:
        return bool(
            plan.replay_reconstruction_plans()
            or plan.rollback_plans()
            or plan.failed_execution_plans()
        )

    def _policy_decisions(self, plans: Any) -> set[str]:
        if not isinstance(plans, list):
            return set()
        return {
            self._safe_text(item.get("policy_decision"))
            for item in plans
            if isinstance(item, dict)
        }

    def _issue(self, issue_type: str, message: str, **metadata: Any) -> dict[str, Any]:
        return {
            "type": issue_type,
            "message": message,
            **copy.deepcopy(metadata),
        }

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def _safe_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

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


def approve_runtime_recovery_plan(source: Any) -> RuntimeRecoveryApprovalReport:
    return RuntimeRecoveryApprovalEvaluator().evaluate(source)


__all__ = [
    "APPROVAL_APPROVE",
    "APPROVAL_DEFER",
    "APPROVAL_REJECT",
    "RuntimeRecoveryApprovalEvaluator",
    "RuntimeRecoveryApprovalReport",
    "approve_runtime_recovery_plan",
]
