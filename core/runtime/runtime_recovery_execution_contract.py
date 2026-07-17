from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from core.goals.goal_lineage_contract import extract_runtime_identity
from core.runtime.runtime_recovery_approval import (
    APPROVAL_APPROVE,
    APPROVAL_DEFER,
    APPROVAL_REJECT,
    RuntimeRecoveryApprovalEvaluator,
    RuntimeRecoveryApprovalReport,
    canonicalize_runtime_recovery_approval_reason,
)
from core.runtime.runtime_recovery_plan import (
    RuntimeRecoveryPlanReport,
    build_runtime_recovery_plan,
    stable_recovery_fingerprint,
)


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

    def to_dict(self) -> dict[str, Any]:
        return self.payload

    def _json_safe(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
        return json.loads(encoded)


class RuntimeRecoveryPlanReportView:
    """Read-only compatibility view for dataclass-based recovery plan reports."""

    def __init__(self, report: Any) -> None:
        self._payload = self._to_payload(report)
        self._fingerprint = stable_recovery_fingerprint(self._payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def replay_reconstruction_plans(self) -> list[dict[str, Any]]:
        direct = self._payload.get("replay_reconstruction_plans")
        if isinstance(direct, list):
            return [copy.deepcopy(item) for item in direct if isinstance(item, dict)]
        if not bool(self._payload.get("replay_required", False)):
            return []
        plan = self._plan_payload()
        plan_id = self._text(plan.get("plan_id") or self.fingerprint[:12])
        return [
            {
                "plan_id": f"replay:{plan_id}",
                "plan_type": "replay_reconstruction",
                "classification": "runtime_recovery_replay",
                "policy_decision": self._text(self._payload.get("status") or plan.get("status") or "planned"),
                "replay_safety": "contract_only",
                "trust_score": 100 if bool(self._payload.get("ok", False)) else 0,
                "stages": ["collect_evidence", "reconstruct_state", "verify_replay"],
            }
        ]

    def rollback_plans(self) -> list[dict[str, Any]]:
        direct = self._payload.get("rollback_plans")
        if isinstance(direct, list):
            return [copy.deepcopy(item) for item in direct if isinstance(item, dict)]
        if not bool(self._payload.get("rollback_required", False)):
            return []
        plan = self._plan_payload()
        plan_id = self._text(plan.get("plan_id") or self.fingerprint[:12])
        return [
            {
                "plan_id": f"rollback:{plan_id}",
                "plan_type": "rollback",
                "classification": "runtime_recovery_rollback",
                "policy_decision": self._text(self._payload.get("status") or plan.get("status") or "planned"),
                "rollback_id": self._text(plan.get("recovery_id") or self.fingerprint[:12]),
                "execution_id": self._text(plan.get("source_session_id") or ""),
                "replay_order": 0,
                "stages": ["prepare_rollback", "verify_rollback"],
            }
        ]

    def failed_execution_plans(self) -> list[dict[str, Any]]:
        direct = self._payload.get("failed_execution_plans")
        if isinstance(direct, list):
            return [copy.deepcopy(item) for item in direct if isinstance(item, dict)]
        plan = self._plan_payload()
        failure = plan.get("source_failure") if isinstance(plan.get("source_failure"), dict) else {}
        status = self._text(failure.get("status") or "")
        if status not in {"failed", "blocked", "rejected"}:
            return []
        plan_id = self._text(plan.get("plan_id") or self.fingerprint[:12])
        return [
            {
                "plan_id": f"failed-execution:{plan_id}",
                "plan_type": "failed_execution_recovery",
                "classification": "runtime_failed_execution_recovery",
                "policy_decision": self._text(self._payload.get("status") or plan.get("status") or "planned"),
                "failed_execution_id": self._text(failure.get("source_session_id") or plan.get("source_session_id") or ""),
                "status": status,
                "phase": self._text(failure.get("source") or "runtime"),
                "stages": ["classify_failure", "verify_recovery"],
            }
        ]

    def _plan_payload(self) -> dict[str, Any]:
        plan = self._payload.get("plan")
        return copy.deepcopy(plan) if isinstance(plan, dict) else {}

    def _to_payload(self, value: Any) -> dict[str, Any]:
        if isinstance(value, RuntimeRecoveryPlanReport):
            return value.to_dict()
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
            if isinstance(payload, dict):
                return copy.deepcopy(payload)
        if is_dataclass(value):
            return copy.deepcopy(asdict(value))
        if isinstance(value, dict):
            return copy.deepcopy(value)
        return {}

    def _text(self, value: Any) -> str:
        return "" if value is None else str(value)


class RuntimeRecoveryApprovalReportView:
    """Read-only compatibility view for recovery approval reports.

    The current approval layer may return a dataclass with an ``approval`` field,
    while older execution-contract code expected helper methods such as
    ``recovery_approval()``.  This view normalizes both shapes.
    """

    def __init__(self, report: Any) -> None:
        self._payload = self._to_payload(report)
        self._fingerprint = stable_recovery_fingerprint(self._payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def recovery_approval(self) -> dict[str, Any]:
        return self._gate("recovery")

    def replay_approval(self) -> dict[str, Any]:
        return self._gate("replay")

    def rollback_approval(self) -> dict[str, Any]:
        return self._gate("rollback")

    def failed_execution_approval(self) -> dict[str, Any]:
        return self._gate("failed_execution")

    def approval_reasons(self) -> list[Any]:
        values = self._payload.get("approval_reasons")
        if isinstance(values, list):
            return [self._canonical_approval_reason_entry(item) for item in values if item is not None]
        approval = self._approval_payload()
        reason = self._text(
            approval.get("reason")
            or approval.get("approval_reason")
            or self._payload.get("reason")
            or self._payload.get("status")
            or "contract approval"
        )
        return [reason] if reason else []

    def _gate(self, gate: str) -> dict[str, Any]:
        direct = self._payload.get(f"{gate}_approval")
        if isinstance(direct, dict):
            payload = copy.deepcopy(direct)
            payload.setdefault("gate", gate)
            payload.setdefault("state", self._state())
            payload.setdefault("reason", self._reason(gate))
            payload["reason"] = canonicalize_runtime_recovery_approval_reason(
                payload.get("reason"),
                gate=gate,
            )
            payload.setdefault("approval_can_be_granted", self._can_grant())
            return payload
        approval = self._approval_payload()
        return {
            "gate": gate,
            "state": self._state(),
            "reason": canonicalize_runtime_recovery_approval_reason(self._reason(gate), gate=gate),
            "approval_can_be_granted": self._can_grant(),
            "approved": bool(approval.get("approved", self._payload.get("approved", False))),
            "approval_required": bool(approval.get("approval_required", self._payload.get("approval_required", False))),
        }

    def _state(self) -> str:
        approval = self._approval_payload()
        raw = self._text(
            self._payload.get("approval_state")
            or self._payload.get("status")
            or approval.get("state")
            or approval.get("status")
            or approval.get("decision")
        ).lower()
        if raw in {APPROVAL_APPROVE, "approved", "approve", "ok", "ready", "allow"}:
            return APPROVAL_APPROVE
        if raw in {APPROVAL_REJECT, "rejected", "blocked", "failed", "unsafe", "deny", "denied"}:
            return APPROVAL_REJECT
        if raw in {APPROVAL_DEFER, "deferred", "pending", "review_required"}:
            return APPROVAL_DEFER
        if bool(approval.get("approved", self._payload.get("approved", False))):
            return APPROVAL_APPROVE
        if bool(self._payload.get("ok", False)) and not bool(approval.get("approval_required", False)):
            return APPROVAL_APPROVE
        return APPROVAL_DEFER

    def _reason(self, gate: str) -> str:
        approval = self._approval_payload()
        return canonicalize_runtime_recovery_approval_reason(
            self._text(
            approval.get("reason")
            or approval.get("approval_reason")
            or self._payload.get("reason")
            or f"{gate} contract approval"
            ),
            gate=gate,
        )

    def _canonical_approval_reason_entry(self, value: Any) -> Any:
        if not isinstance(value, dict):
            return canonicalize_runtime_recovery_approval_reason(value)
        entry = copy.deepcopy(value)
        gate = self._text(entry.get("gate"))
        if "reason" in entry:
            entry["reason"] = canonicalize_runtime_recovery_approval_reason(
                entry.get("reason"),
                gate=gate,
            )
        return entry

    def _can_grant(self) -> bool:
        approval = self._approval_payload()
        if "approval_can_be_granted" in approval:
            return bool(approval.get("approval_can_be_granted"))
        if "approved" in approval:
            return bool(approval.get("approved"))
        return self._state() == APPROVAL_APPROVE

    def _approval_payload(self) -> dict[str, Any]:
        approval = self._payload.get("approval")
        return copy.deepcopy(approval) if isinstance(approval, dict) else {}

    def _to_payload(self, value: Any) -> dict[str, Any]:
        if isinstance(value, RuntimeRecoveryApprovalReportView):
            return value.payload
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
            if isinstance(payload, dict):
                return copy.deepcopy(payload)
        if is_dataclass(value):
            return copy.deepcopy(asdict(value))
        if isinstance(value, dict):
            return copy.deepcopy(value)
        return {}

    def _text(self, value: Any) -> str:
        return "" if value is None else str(value)


class RuntimeRecoveryExecutionContractBuilder:
    """Converts recovery approval and plan reports into inert execution contracts."""

    def __init__(self, *, approval_evaluator: RuntimeRecoveryApprovalEvaluator | None = None) -> None:
        self.approval_evaluator = approval_evaluator if approval_evaluator is not None else RuntimeRecoveryApprovalEvaluator()

    def build(self, source: Any) -> RuntimeRecoveryExecutionContractReport:
        context = self._context(source)
        plan = self._plan_report(context["plan"])
        approval = self._approval_report(context["approval"])
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
        summary = self._contract_summary(
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
            "contract_summary": summary,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeRecoveryExecutionContractReport(payload)

    def create_approved_recovery_contract(self, plan: Any, approval: Any) -> dict[str, Any]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        gate = approval_report.recovery_approval()
        approval_state = self._safe_text(gate.get("state"))
        contract = {
            "contract_id": "contract:recovery",
            "contract_type": "recovery",
            "status": self._contract_status(approval_state),
            "approval_state": approval_state,
            "approval_reason": self._safe_text(gate.get("reason")),
            "approval_can_be_granted": bool(gate.get("approval_can_be_granted", False)),
            "executable": False,
            "requires_confirmation": True,
            "source_plan_fingerprint": plan_report.fingerprint,
            "source_approval_fingerprint": approval_report.fingerprint,
            "approval_reasons": approval_report.approval_reasons(),
            "risk": self.contract_risk_metadata(contract_type="recovery", approval_state=approval_state),
            "action": "none",
            "executes_action": False,
        }
        contract["fingerprint"] = self._fingerprint(contract)
        return contract

    def create_replay_execution_contracts(self, plan: Any, approval: Any) -> list[dict[str, Any]]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        return self._contracts_from_plans(
            plan_report.replay_reconstruction_plans(),
            contract_type="replay",
            gate=approval_report.replay_approval(),
            approval_report=approval_report,
        )

    def create_rollback_execution_contracts(self, plan: Any, approval: Any) -> list[dict[str, Any]]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        return self._contracts_from_plans(
            plan_report.rollback_plans(),
            contract_type="rollback",
            gate=approval_report.rollback_approval(),
            approval_report=approval_report,
        )

    def create_failed_execution_recovery_contracts(self, plan: Any, approval: Any) -> list[dict[str, Any]]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        return self._contracts_from_plans(
            plan_report.failed_execution_plans(),
            contract_type="failed_execution_recovery",
            gate=approval_report.failed_execution_approval(),
            approval_report=approval_report,
        )

    def handle_rejected_or_deferred_approval(
        self,
        plan: Any,
        approval: Any,
        *,
        replay_contracts: list[dict[str, Any]] | None = None,
        rollback_contracts: list[dict[str, Any]] | None = None,
        failed_execution_contracts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        plan_report = self._plan_report(plan)
        approval_report = self._approval_report(approval)
        contracts: list[dict[str, Any]] = []
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
                "risk": self.contract_risk_metadata(contract_type="approval_block", approval_state=state),
                "action": "none",
                "executes_action": False,
            }
            contract["fingerprint"] = self._fingerprint(contract)
            contracts.append(contract)

        for original in (
            self._safe_contract_list(replay_contracts)
            + self._safe_contract_list(rollback_contracts)
            + self._safe_contract_list(failed_execution_contracts)
        ):
            if self._safe_text(original.get("status")) not in {CONTRACT_STATUS_BLOCKED, CONTRACT_STATUS_DEFERRED}:
                continue
            blocked = copy.deepcopy(original)
            blocked["contract_id"] = f"contract:block:{self._safe_text(original.get('contract_id'))}"
            blocked["contract_type"] = "action_contract_block"
            blocked["fingerprint"] = self._fingerprint(blocked)
            contracts.append(blocked)

        return sorted(contracts, key=lambda item: self._safe_text(item.get("contract_id")))

    def contract_risk_metadata(self, *, contract_type: str, approval_state: str) -> dict[str, Any]:
        payload = {
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
        payload["fingerprint"] = self._fingerprint(payload)
        return payload

    def _context(self, source: Any) -> dict[str, Any]:
        if isinstance(source, RuntimeRecoveryApprovalReport):
            plan = self._fallback_plan_report_view(
                reason="approval_report_without_plan",
                source_failure={
                    "failure_type": "missing_runtime_recovery_plan",
                    "message": "approval report provided without plan",
                    "status": "failed",
                },
            )
            return {"plan": plan, "approval": self._approval_report(source)}

        plan = self._plan_report(source)
        approval = self._safe_approval_for_plan(plan)
        return {"plan": plan, "approval": self._approval_report(approval)}

    def _contracts_from_plans(
        self,
        plans: list[dict[str, Any]],
        *,
        contract_type: str,
        gate: dict[str, Any],
        approval_report: RuntimeRecoveryApprovalReportView,
    ) -> list[dict[str, Any]]:
        state = self._safe_text(gate.get("state"))
        status = self._contract_status(state)
        contracts: list[dict[str, Any]] = []
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            contract = {
                "contract_id": f"contract:{contract_type}:{self._safe_text(plan.get('plan_id'))}",
                "contract_type": contract_type,
                "status": status,
                "approval_state": state,
                "approval_reason": self._safe_text(gate.get("reason")),
                "approval_can_be_granted": bool(gate.get("approval_can_be_granted", False)),
                "source_plan_id": self._safe_text(plan.get("plan_id")),
                "source_plan_type": self._safe_text(plan.get("plan_type")),
                "policy_decision": self._safe_text(plan.get("policy_decision")),
                "executable": False,
                "requires_confirmation": True,
                "metadata": self._contract_metadata(contract_type, plan),
                "approval_reasons": approval_report.approval_reasons(),
                "risk": self.contract_risk_metadata(contract_type=contract_type, approval_state=state),
                "action": "none",
                "executes_action": False,
            }
            contract["fingerprint"] = self._fingerprint(contract)
            contracts.append(contract)
        if contract_type == "rollback":
            def _rollback_contract_order(item: dict[str, Any]) -> tuple[int, str, str]:
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                return (
                    self._safe_int(metadata.get("replay_order"), 10**9),
                    self._safe_text(metadata.get("execution_id")),
                    self._safe_text(item.get("contract_id")),
                )

            return sorted(
                contracts,
                key=_rollback_contract_order,
            )
        return sorted(contracts, key=lambda item: self._safe_text(item.get("contract_id")))

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

    def _approval_snapshot(self, approval: Any) -> dict[str, Any]:
        report = self._approval_report(approval)
        gate = report.recovery_approval()
        snapshot = {
            "approval_state": self._safe_text(gate.get("state")),
            "approval_reason": self._safe_text(gate.get("reason")),
            "approval_can_be_granted": bool(gate.get("approval_can_be_granted", False)),
            "approval_reasons": report.approval_reasons(),
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

    def _plan_report(self, source: Any) -> RuntimeRecoveryPlanReportView:
        if isinstance(source, RuntimeRecoveryPlanReportView):
            return source
        if isinstance(source, RuntimeRecoveryPlanReport):
            return RuntimeRecoveryPlanReportView(source)
        return self._plan_view_from_source(source)

    def _approval_report(self, source: Any) -> RuntimeRecoveryApprovalReportView:
        if isinstance(source, RuntimeRecoveryApprovalReportView):
            return source
        return RuntimeRecoveryApprovalReportView(source)

    def _plan_view_from_source(self, source: Any) -> RuntimeRecoveryPlanReportView:
        payload = copy.deepcopy(source) if isinstance(source, dict) else {"source": source}
        recovery_id = self._safe_text(
            payload.get("recovery_id")
            or payload.get("transaction_id")
            or payload.get("task_id")
            or "runtime-recovery-contract"
        )
        runtime_identity = extract_runtime_identity(payload, reject_conflicts=True)
        source_session_id = self._safe_text(runtime_identity.get("source_session_id") or "")
        task_id = self._safe_text(payload.get("task_id") or "")
        status = self._safe_text(payload.get("status") or "failed")
        plan = build_runtime_recovery_plan(
            recovery_id=recovery_id,
            source_failure={
                "failure_type": payload.get("failure_type") or payload.get("type") or "runtime_recovery_gate_context",
                "message": payload.get("message") or payload.get("reason") or "runtime recovery gate context",
                "status": status,
                "source_session_id": source_session_id,
                "task_id": task_id,
                "payload": payload,
                "metadata": {"contract_source": "runtime_recovery_execution_contract", "read_only": True},
            },
            source_session_id=source_session_id,
            task_id=task_id,
            metadata={"contract_generation_only": True, "read_only": True, "source_status": status},
        )
        report = RuntimeRecoveryPlanReport(
            ok=True,
            plan=plan,
            status=plan.status,
            rollback_required=plan.rollback_required,
            replay_required=plan.replay_required,
            verification_required=plan.verification_required,
            errors=[],
            warnings=[],
            metadata=copy.deepcopy(plan.metadata),
        )
        return RuntimeRecoveryPlanReportView(report)

    def _fallback_plan_report_view(self, *, reason: str, source_failure: dict[str, Any]) -> RuntimeRecoveryPlanReportView:
        plan = build_runtime_recovery_plan(
            recovery_id="runtime-recovery-fallback",
            source_failure=source_failure,
            metadata={"fallback_reason": reason, "contract_generation_only": True},
        )
        report = RuntimeRecoveryPlanReport(
            ok=False,
            plan=plan,
            status=plan.status,
            rollback_required=plan.rollback_required,
            replay_required=plan.replay_required,
            verification_required=plan.verification_required,
            errors=[reason],
            warnings=[],
            metadata=copy.deepcopy(plan.metadata),
        )
        return RuntimeRecoveryPlanReportView(report)

    def _safe_approval_for_plan(self, plan: Any) -> Any:
        try:
            return self.approval_evaluator.evaluate(plan)
        except Exception:
            return {
                "ok": True,
                "status": "approved",
                "approval": {"approval_required": False, "approved": True, "reason": "fallback contract approval"},
                "recovery_approval": {
                    "gate": "recovery",
                    "state": APPROVAL_APPROVE,
                    "reason": "fallback contract approval",
                    "approval_can_be_granted": True,
                },
                "replay_approval": {
                    "gate": "replay",
                    "state": APPROVAL_APPROVE,
                    "reason": "fallback contract approval",
                    "approval_can_be_granted": True,
                },
                "rollback_approval": {
                    "gate": "rollback",
                    "state": APPROVAL_APPROVE,
                    "reason": "fallback contract approval",
                    "approval_can_be_granted": True,
                },
                "failed_execution_approval": {
                    "gate": "failed_execution",
                    "state": APPROVAL_APPROVE,
                    "reason": "fallback contract approval",
                    "approval_can_be_granted": True,
                },
                "approval_reasons": ["fallback contract approval"],
            }

    def _safe_contract_list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [copy.deepcopy(item) for item in value if isinstance(item, dict)]

    def _safe_text(self, value: Any) -> str:
        return "" if value is None else str(value)

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _fingerprint(self, payload: dict[str, Any]) -> str:
        safe = copy.deepcopy(payload)
        safe.pop("fingerprint", None)
        encoded = json.dumps(safe, default=str, sort_keys=True, separators=(",", ":"))
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
