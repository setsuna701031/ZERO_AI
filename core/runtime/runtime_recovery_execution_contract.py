from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_recovery_approval import (
    APPROVAL_APPROVE,
    APPROVAL_DEFER,
    APPROVAL_REJECT,
    RuntimeRecoveryApprovalEvaluator,
    RuntimeRecoveryApprovalReport,
)
from core.runtime.runtime_recovery_plan import RuntimeRecoveryPlanReport


CONTRACT_STATUS_APPROVED = "approved"
CONTRACT_STATUS_BLOCKED = "blocked"
CONTRACT_STATUS_DEFERRED = "deferred"


class RuntimeRecoveryExecutionContractReport:
    SCHEMA = "zero.runtime.recovery_execution_contract.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def recovery_contract(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("recovery_contract", {}))

    def replay_contracts(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("replay_contracts", []))

    def rollback_contracts(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("rollback_contracts", []))

    def failed_execution_contracts(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("failed_execution_contracts", []))

    def blocked_contracts(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("blocked_contracts", []))

    def contract_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("contract_summary", {}))

    def approval_snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("approval_snapshot", {}))

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


class RuntimeRecoveryExecutionContractBuilder:
    """Converts recovery approval and plan reports into inert execution contracts."""

    def __init__(
        self,
        *,
        approval_evaluator: RuntimeRecoveryApprovalEvaluator | None = None,
    ) -> None:
        self.approval_evaluator = approval_evaluator if approval_evaluator is not None else RuntimeRecoveryApprovalEvaluator()

    def build(self, source: Any) -> RuntimeRecoveryExecutionContractReport:
        context = self._context(source)
        plan = context["plan"]
        approval = context["approval"]
        recovery_contract = self.create_approved_recovery_contract(plan, approval)
        replay_contracts = self.create_replay_execution_contracts(plan, approval)
        rollback_contracts = self.create_rollback_execution_contracts(plan, approval)
        failed_execution_contracts = self.create_failed_execution_recovery_contracts(plan, approval)
        blocked_contracts = self.handle_rejected_or_deferred_approval(
            plan,
            approval,
            replay_contracts=replay_contracts,
            rollback_contracts=rollback_contracts,
            failed_execution_contracts=failed_execution_contracts,
        )
        contract_summary = self._contract_summary(
            recovery_contract=recovery_contract,
            replay_contracts=replay_contracts,
            rollback_contracts=rollback_contracts,
            failed_execution_contracts=failed_execution_contracts,
            blocked_contracts=blocked_contracts,
        )
        payload = {
            "ok": True,
            "schema": RuntimeRecoveryExecutionContractReport.SCHEMA,
            "mode": "contract_generation_only",
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "source": {
                "plan_fingerprint": plan.fingerprint,
                "approval_fingerprint": approval.fingerprint,
            },
            "approval_snapshot": self._approval_snapshot(approval),
            "recovery_contract": recovery_contract,
            "replay_contracts": replay_contracts,
            "rollback_contracts": rollback_contracts,
            "failed_execution_contracts": failed_execution_contracts,
            "blocked_contracts": blocked_contracts,
            "contract_summary": contract_summary,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeRecoveryExecutionContractReport(payload)

    def create_approved_recovery_contract(
        self,
        plan: RuntimeRecoveryPlanReport | Any,
        approval: RuntimeRecoveryApprovalReport | Any,
    ) -> dict[str, Any]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        recovery_approval = approval_report.recovery_approval()
        approval_state = self._safe_text(recovery_approval.get("state"))
        status = self._contract_status(approval_state)
        contract = {
            "contract_id": "contract:recovery",
            "contract_type": "recovery",
            "status": status,
            "approval_state": approval_state,
            "approval_reason": self._safe_text(recovery_approval.get("reason")),
            "approval_can_be_granted": bool(recovery_approval.get("approval_can_be_granted", False)),
            "executable": False,
            "requires_confirmation": True,
            "source_plan_fingerprint": plan_report.fingerprint,
            "source_approval_fingerprint": approval_report.fingerprint,
            "approval_reasons": approval_report.approval_reasons(),
            "risk": self.contract_risk_metadata(
                contract_type="recovery",
                approval_state=approval_state,
            ),
            "action": "none",
            "executes_action": False,
        }
        contract["fingerprint"] = self._fingerprint(contract)
        return contract

    def create_replay_execution_contracts(
        self,
        plan: RuntimeRecoveryPlanReport | Any,
        approval: RuntimeRecoveryApprovalReport | Any,
    ) -> list[dict[str, Any]]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        gate = approval_report.replay_approval()
        return self._contracts_from_plans(
            plan_report.replay_reconstruction_plans(),
            contract_type="replay",
            gate=gate,
            approval_report=approval_report,
        )

    def create_rollback_execution_contracts(
        self,
        plan: RuntimeRecoveryPlanReport | Any,
        approval: RuntimeRecoveryApprovalReport | Any,
    ) -> list[dict[str, Any]]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        gate = approval_report.rollback_approval()
        return self._contracts_from_plans(
            plan_report.rollback_plans(),
            contract_type="rollback",
            gate=gate,
            approval_report=approval_report,
        )

    def create_failed_execution_recovery_contracts(
        self,
        plan: RuntimeRecoveryPlanReport | Any,
        approval: RuntimeRecoveryApprovalReport | Any,
    ) -> list[dict[str, Any]]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        gate = approval_report.failed_execution_approval()
        return self._contracts_from_plans(
            plan_report.failed_execution_plans(),
            contract_type="failed_execution_recovery",
            gate=gate,
            approval_report=approval_report,
        )

    def handle_rejected_or_deferred_approval(
        self,
        plan: RuntimeRecoveryPlanReport | Any,
        approval: RuntimeRecoveryApprovalReport | Any,
        *,
        replay_contracts: list[dict[str, Any]] | None = None,
        rollback_contracts: list[dict[str, Any]] | None = None,
        failed_execution_contracts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        contracts = []
        action_contracts = (
            self._safe_contract_list(replay_contracts)
            + self._safe_contract_list(rollback_contracts)
            + self._safe_contract_list(failed_execution_contracts)
        )
        for gate in (
            approval_report.replay_approval(),
            approval_report.rollback_approval(),
            approval_report.failed_execution_approval(),
            approval_report.recovery_approval(),
        ):
            state = self._safe_text(gate.get("state"))
            if state == APPROVAL_APPROVE:
                continue
            contract = {
                "contract_id": f"contract:block:{self._safe_text(gate.get('gate'))}",
                "contract_type": "approval_block",
                "status": self._contract_status(state),
                "approval_state": state,
                "approval_reason": self._safe_text(gate.get("reason")),
                "executable": False,
                "requires_confirmation": True,
                "source_plan_fingerprint": plan_report.fingerprint,
                "source_approval_fingerprint": approval_report.fingerprint,
                "risk": self.contract_risk_metadata(
                    contract_type="approval_block",
                    approval_state=state,
                ),
                "action": "none",
                "executes_action": False,
            }
            contract["fingerprint"] = self._fingerprint(contract)
            contracts.append(contract)
        for contract in action_contracts:
            if self._safe_text(contract.get("status")) in {CONTRACT_STATUS_BLOCKED, CONTRACT_STATUS_DEFERRED}:
                blocked = copy.deepcopy(contract)
                blocked["contract_id"] = f"contract:block:{self._safe_text(contract.get('contract_id'))}"
                blocked["contract_type"] = "action_contract_block"
                blocked["fingerprint"] = self._fingerprint(blocked)
                contracts.append(blocked)
        return sorted(
            contracts,
            key=lambda item: self._safe_text(item.get("contract_id")),
        )

    def contract_risk_metadata(self, *, contract_type: str, approval_state: str) -> dict[str, Any]:
        metadata = {
            "risk_profile": "execution_contract_only",
            "contract_type": self._safe_text(contract_type),
            "approval_state": self._safe_text(approval_state),
            "executable_default": False,
            "requires_confirmation": True,
            "guards": {
                "no_runtime_execution": True,
                "no_rollback_execution": True,
                "no_repair_execution": True,
                "no_scheduler_invocation": True,
                "no_persistence": True,
                "no_networking": True,
            },
        }
        metadata["fingerprint"] = self._fingerprint(metadata)
        return metadata

    def _context(self, source: Any) -> dict[str, RuntimeRecoveryPlanReport | RuntimeRecoveryApprovalReport]:
        if isinstance(source, RuntimeRecoveryPlanReport):
            plan = RuntimeRecoveryPlanReport(source.payload)
            approval = self.approval_evaluator.evaluate(plan)
            return {"plan": plan, "approval": approval}
        if isinstance(source, RuntimeRecoveryApprovalReport):
            approval = RuntimeRecoveryApprovalReport(source.payload)
            plan = RuntimeRecoveryPlanReport({})
            return {"plan": plan, "approval": approval}
        plan = RuntimeRecoveryPlanReport({})
        approval = self.approval_evaluator.evaluate(plan)
        return {"plan": plan, "approval": approval}

    def _contracts_from_plans(
        self,
        plans: list[dict[str, Any]],
        *,
        contract_type: str,
        gate: dict[str, Any],
        approval_report: RuntimeRecoveryApprovalReport,
    ) -> list[dict[str, Any]]:
        approval_state = self._safe_text(gate.get("state"))
        status = self._contract_status(approval_state)
        contracts = []
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            contract = {
                "contract_id": f"contract:{contract_type}:{self._safe_text(plan.get('plan_id'))}",
                "contract_type": contract_type,
                "status": status,
                "approval_state": approval_state,
                "approval_reason": self._safe_text(gate.get("reason")),
                "approval_can_be_granted": bool(gate.get("approval_can_be_granted", False)),
                "source_plan_id": self._safe_text(plan.get("plan_id")),
                "source_plan_type": self._safe_text(plan.get("plan_type")),
                "policy_decision": self._safe_text(plan.get("policy_decision")),
                "executable": False,
                "requires_confirmation": True,
                "metadata": self._contract_metadata(contract_type, plan),
                "approval_reasons": approval_report.approval_reasons(),
                "risk": self.contract_risk_metadata(
                    contract_type=contract_type,
                    approval_state=approval_state,
                ),
                "action": "none",
                "executes_action": False,
            }
            contract["fingerprint"] = self._fingerprint(contract)
            contracts.append(contract)
        return sorted(
            contracts,
            key=lambda item: self._safe_text(item.get("contract_id")),
        )

    def _contract_metadata(self, contract_type: str, plan: dict[str, Any]) -> dict[str, Any]:
        metadata = {
            "plan_id": self._safe_text(plan.get("plan_id")),
            "plan_type": self._safe_text(plan.get("plan_type")),
            "classification": self._safe_text(plan.get("classification")),
            "stage_count": len(plan.get("stages")) if isinstance(plan.get("stages"), list) else 0,
        }
        if contract_type == "rollback":
            metadata.update(
                {
                    "rollback_id": self._safe_text(plan.get("rollback_id")),
                    "execution_id": self._safe_text(plan.get("execution_id")),
                    "replay_order": self._safe_int(plan.get("replay_order"), 0),
                }
            )
        if contract_type == "replay":
            metadata.update(
                {
                    "replay_safety": self._safe_text(plan.get("replay_safety")),
                    "trust_score": self._safe_int(plan.get("trust_score"), 0),
                }
            )
        if contract_type == "failed_execution_recovery":
            metadata.update(
                {
                    "failed_execution_id": self._safe_text(plan.get("failed_execution_id")),
                    "status": self._safe_text(plan.get("status")),
                    "phase": self._safe_text(plan.get("phase")),
                }
            )
        metadata["fingerprint"] = self._fingerprint(metadata)
        return metadata

    def _approval_snapshot(self, approval: RuntimeRecoveryApprovalReport) -> dict[str, Any]:
        recovery_approval = approval.recovery_approval()
        snapshot = {
            "approval_state": self._safe_text(recovery_approval.get("state")),
            "approval_reason": self._safe_text(recovery_approval.get("reason")),
            "approval_can_be_granted": bool(recovery_approval.get("approval_can_be_granted", False)),
            "approval_reasons": approval.approval_reasons(),
        }
        snapshot["fingerprint"] = self._fingerprint(snapshot)
        return snapshot

    def _contract_summary(
        self,
        *,
        recovery_contract: dict[str, Any],
        replay_contracts: list[dict[str, Any]],
        rollback_contracts: list[dict[str, Any]],
        failed_execution_contracts: list[dict[str, Any]],
        blocked_contracts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        all_contracts = (
            [copy.deepcopy(recovery_contract)]
            + self._safe_contract_list(replay_contracts)
            + self._safe_contract_list(rollback_contracts)
            + self._safe_contract_list(failed_execution_contracts)
            + self._safe_contract_list(blocked_contracts)
        )
        summary = {
            "contract_count": len(all_contracts),
            "replay_contract_count": len(replay_contracts),
            "rollback_contract_count": len(rollback_contracts),
            "failed_execution_contract_count": len(failed_execution_contracts),
            "blocked_contract_count": len(blocked_contracts),
            "approved_count": sum(1 for item in all_contracts if item.get("status") == CONTRACT_STATUS_APPROVED),
            "deferred_count": sum(1 for item in all_contracts if item.get("status") == CONTRACT_STATUS_DEFERRED),
            "blocked_count": sum(1 for item in all_contracts if item.get("status") == CONTRACT_STATUS_BLOCKED),
            "all_executable_false": all(not bool(item.get("executable", False)) for item in all_contracts),
            "all_require_confirmation": all(bool(item.get("requires_confirmation", False)) for item in all_contracts),
        }
        summary["fingerprint"] = self._fingerprint(summary)
        return summary

    def _contract_status(self, approval_state: str) -> str:
        if approval_state == APPROVAL_APPROVE:
            return CONTRACT_STATUS_APPROVED
        if approval_state == APPROVAL_DEFER:
            return CONTRACT_STATUS_DEFERRED
        return CONTRACT_STATUS_BLOCKED

    def _plan_report(self, source: Any) -> RuntimeRecoveryPlanReport:
        if isinstance(source, RuntimeRecoveryPlanReport):
            return RuntimeRecoveryPlanReport(source.payload)
        return RuntimeRecoveryPlanReport({})

    def _approval_report(self, source: Any) -> RuntimeRecoveryApprovalReport:
        if isinstance(source, RuntimeRecoveryApprovalReport):
            return RuntimeRecoveryApprovalReport(source.payload)
        return self.approval_evaluator.evaluate(source)

    def _safe_contract_list(self, value: Any) -> list[dict[str, Any]]:
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


def build_runtime_recovery_execution_contract(source: Any) -> RuntimeRecoveryExecutionContractReport:
    return RuntimeRecoveryExecutionContractBuilder().build(source)


__all__ = [
    "CONTRACT_STATUS_APPROVED",
    "CONTRACT_STATUS_BLOCKED",
    "CONTRACT_STATUS_DEFERRED",
    "RuntimeRecoveryExecutionContractBuilder",
    "RuntimeRecoveryExecutionContractReport",
    "build_runtime_recovery_execution_contract",
]
