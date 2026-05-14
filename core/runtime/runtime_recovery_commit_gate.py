from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_recovery_dry_run_executor import (
    DRY_RUN_BLOCKED,
    DRY_RUN_DEFERRED,
    DRY_RUN_SIMULATED,
    RuntimeRecoveryDryRunReport,
)


COMMIT_ALLOWED = "commit_allowed"
COMMIT_BLOCKED = "commit_blocked"
COMMIT_DEFERRED = "commit_deferred"


class RuntimeRecoveryCommitGateReport:
    SCHEMA = "zero.runtime.recovery_commit_gate.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def commit_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("commit_summary", {}))

    def dry_run_commit_authorization(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("dry_run_commit_authorization", {}))

    def rollback_commit_gate(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("rollback_commit_gate", {}))

    def replay_commit_gate(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("replay_commit_gate", {}))

    def unsafe_simulation_rejection(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("unsafe_simulation_rejection", {}))

    def confirmation_enforcement(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("confirmation_enforcement", {}))

    def final_execution_readiness(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("final_execution_readiness", {}))

    def blocked_deferred_propagation(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("blocked_deferred_propagation", {}))

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


class RuntimeRecoveryCommitGate:
    """Authorization-only commit gate over dry-run recovery reports."""

    def evaluate(
        self,
        source: Any,
        *,
        manual_confirmation_provided: bool = False,
    ) -> RuntimeRecoveryCommitGateReport:
        dry_run = self._dry_run_report(source)
        unsafe_rejection = self.reject_unsafe_simulation(dry_run)
        dry_run_authorization = self.authorize_dry_run_commit(
            dry_run,
            unsafe_rejection=unsafe_rejection,
        )
        rollback_gate = self.gate_rollback_commit(
            dry_run,
            unsafe_rejection=unsafe_rejection,
        )
        replay_gate = self.gate_replay_commit(
            dry_run,
            unsafe_rejection=unsafe_rejection,
        )
        confirmation = self.enforce_confirmation(
            dry_run,
            manual_confirmation_provided=manual_confirmation_provided,
            unsafe_rejection=unsafe_rejection,
        )
        blocked_deferred = self.propagate_blocked_deferred(dry_run)
        final_readiness = self.evaluate_final_execution_readiness(
            dry_run_authorization=dry_run_authorization,
            rollback_gate=rollback_gate,
            replay_gate=replay_gate,
            unsafe_rejection=unsafe_rejection,
            confirmation_enforcement=confirmation,
            blocked_deferred_propagation=blocked_deferred,
        )
        commit_summary = self._commit_summary(final_readiness, blocked_deferred)
        payload = {
            "ok": True,
            "schema": RuntimeRecoveryCommitGateReport.SCHEMA,
            "mode": "commit_gate_authorization_only",
            "read_only": True,
            "deterministic": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "invokes_scheduler": False,
            "adds_persistence": False,
            "uses_network": False,
            "source": {
                "dry_run_fingerprint": dry_run.fingerprint,
            },
            "commit_summary": commit_summary,
            "dry_run_commit_authorization": dry_run_authorization,
            "rollback_commit_gate": rollback_gate,
            "replay_commit_gate": replay_gate,
            "unsafe_simulation_rejection": unsafe_rejection,
            "confirmation_enforcement": confirmation,
            "blocked_deferred_propagation": blocked_deferred,
            "final_execution_readiness": final_readiness,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeRecoveryCommitGateReport(payload)

    def authorize_dry_run_commit(
        self,
        dry_run: RuntimeRecoveryDryRunReport | Any,
        *,
        unsafe_rejection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = self._dry_run_report(dry_run)
        unsafe = self._safe_mapping(unsafe_rejection) if unsafe_rejection is not None else self.reject_unsafe_simulation(report)
        summary = report.dry_run_summary()
        status = self._safe_text(summary.get("status"))
        missing_evidence = self._missing_dry_run_evidence(report)
        blocked = bool(unsafe.get("rejected", False)) or missing_evidence or status == DRY_RUN_BLOCKED
        deferred = status == DRY_RUN_DEFERRED
        result = {
            "gate": "dry_run_commit_authorization",
            "state": self._gate_state(blocked=blocked, deferred=deferred),
            "commit_allowed": not blocked and not deferred,
            "requires_manual_confirmation": not blocked and not deferred,
            "dry_run_status": status,
            "missing_evidence": missing_evidence,
            "reason": self._reason(
                blocked=blocked,
                deferred=deferred,
                blocked_reason="dry_run_commit_blocked",
                deferred_reason="dry_run_commit_deferred",
                allowed_reason="dry_run_commit_authorized",
            ),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def gate_rollback_commit(
        self,
        dry_run: RuntimeRecoveryDryRunReport | Any,
        *,
        unsafe_rejection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = self._dry_run_report(dry_run)
        unsafe = self._safe_mapping(unsafe_rejection) if unsafe_rejection is not None else self.reject_unsafe_simulation(report)
        simulations = report.rollback_dry_runs()
        statuses = self._simulation_statuses(simulations)
        missing_evidence = self._missing_dry_run_evidence(report)
        blocked = bool(unsafe.get("rejected", False)) or missing_evidence or DRY_RUN_BLOCKED in statuses
        deferred = DRY_RUN_DEFERRED in statuses
        result = {
            "gate": "rollback_commit_gate",
            "state": self._gate_state(blocked=blocked, deferred=deferred),
            "commit_allowed": not blocked and not deferred,
            "requires_manual_confirmation": not blocked and not deferred,
            "rollback_dry_run_count": len(simulations),
            "blocked_count": statuses.count(DRY_RUN_BLOCKED),
            "deferred_count": statuses.count(DRY_RUN_DEFERRED),
            "reason": self._reason(
                blocked=blocked,
                deferred=deferred,
                blocked_reason="rollback_commit_blocked",
                deferred_reason="rollback_commit_deferred",
                allowed_reason="rollback_commit_authorized",
            ),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def gate_replay_commit(
        self,
        dry_run: RuntimeRecoveryDryRunReport | Any,
        *,
        unsafe_rejection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = self._dry_run_report(dry_run)
        unsafe = self._safe_mapping(unsafe_rejection) if unsafe_rejection is not None else self.reject_unsafe_simulation(report)
        simulations = report.replay_dry_runs()
        statuses = self._simulation_statuses(simulations)
        missing_evidence = self._missing_dry_run_evidence(report)
        blocked = bool(unsafe.get("rejected", False)) or missing_evidence or DRY_RUN_BLOCKED in statuses
        deferred = DRY_RUN_DEFERRED in statuses or not simulations
        result = {
            "gate": "replay_commit_gate",
            "state": self._gate_state(blocked=blocked, deferred=deferred),
            "commit_allowed": not blocked and not deferred,
            "requires_manual_confirmation": not blocked and not deferred,
            "replay_dry_run_count": len(simulations),
            "blocked_count": statuses.count(DRY_RUN_BLOCKED),
            "deferred_count": statuses.count(DRY_RUN_DEFERRED),
            "reason": self._reason(
                blocked=blocked,
                deferred=deferred,
                blocked_reason="replay_commit_blocked",
                deferred_reason="replay_commit_deferred",
                allowed_reason="replay_commit_authorized",
            ),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def reject_unsafe_simulation(self, dry_run: RuntimeRecoveryDryRunReport | Any) -> dict[str, Any]:
        report = self._dry_run_report(dry_run)
        payload = report.payload
        violations = []
        if not bool(payload.get("read_only", False)):
            violations.append("dry_run_not_read_only")
        for flag in ("executes_recovery", "executes_rollback", "executes_repair"):
            if bool(payload.get(flag, False)):
                violations.append(flag)
        summary = report.dry_run_summary()
        if bool(summary.get("would_execute_anything", False)) or bool(summary.get("executes_action", False)):
            violations.append("dry_run_summary_executes_action")
        for item in self._all_simulations(report):
            if bool(item.get("would_execute", False)) or bool(item.get("executes_action", False)):
                violations.append(f"unsafe_simulation:{self._safe_text(item.get('dry_run_id'))}")
        result = {
            "gate": "unsafe_simulation_rejection",
            "state": COMMIT_BLOCKED if violations else COMMIT_ALLOWED,
            "commit_allowed": not violations,
            "requires_manual_confirmation": False,
            "rejected": bool(violations),
            "violation_count": len(violations),
            "violations": sorted(set(violations)),
            "reason": "unsafe_simulation_rejected" if violations else "simulation_is_authorization_only",
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def enforce_confirmation(
        self,
        dry_run: RuntimeRecoveryDryRunReport | Any,
        *,
        manual_confirmation_provided: bool = False,
        unsafe_rejection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = self._dry_run_report(dry_run)
        unsafe = self._safe_mapping(unsafe_rejection) if unsafe_rejection is not None else self.reject_unsafe_simulation(report)
        confirmation = report.confirmation_simulation()
        confirmation_ready = bool(confirmation.get("confirmation_ready", False))
        missing_count = self._safe_int(confirmation.get("missing_confirmation_count"), 0)
        blocked = bool(unsafe.get("rejected", False)) or not confirmation_ready or missing_count > 0
        requires_manual_confirmation = not blocked and not bool(manual_confirmation_provided)
        result = {
            "gate": "confirmation_enforcement",
            "state": COMMIT_BLOCKED if blocked or requires_manual_confirmation else COMMIT_ALLOWED,
            "commit_allowed": not blocked and not requires_manual_confirmation,
            "requires_manual_confirmation": requires_manual_confirmation,
            "manual_confirmation_provided": bool(manual_confirmation_provided),
            "confirmation_ready": confirmation_ready,
            "missing_confirmation_count": missing_count,
            "reason": self._confirmation_reason(
                blocked=blocked,
                requires_manual_confirmation=requires_manual_confirmation,
            ),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def evaluate_final_execution_readiness(
        self,
        *,
        dry_run_authorization: dict[str, Any],
        rollback_gate: dict[str, Any],
        replay_gate: dict[str, Any],
        unsafe_rejection: dict[str, Any],
        confirmation_enforcement: dict[str, Any],
        blocked_deferred_propagation: dict[str, Any],
    ) -> dict[str, Any]:
        gates = [
            self._safe_mapping(dry_run_authorization),
            self._safe_mapping(rollback_gate),
            self._safe_mapping(replay_gate),
            self._safe_mapping(unsafe_rejection),
            self._safe_mapping(confirmation_enforcement),
        ]
        blocked_deferred = self._safe_mapping(blocked_deferred_propagation)
        blocked = any(not bool(gate.get("commit_allowed", False)) for gate in gates)
        deferred = self._safe_int(blocked_deferred.get("deferred_count"), 0) > 0
        blocked = blocked or self._safe_int(blocked_deferred.get("blocked_count"), 0) > 0
        result = {
            "gate": "final_execution_readiness",
            "state": self._gate_state(blocked=blocked, deferred=deferred),
            "commit_allowed": not blocked and not deferred,
            "requires_manual_confirmation": bool(
                self._safe_mapping(confirmation_enforcement).get("requires_manual_confirmation", False)
            ),
            "authorization_only": True,
            "may_enter_real_execution_stage": not blocked and not deferred,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "reason": self._reason(
                blocked=blocked,
                deferred=deferred,
                blocked_reason="final_execution_readiness_blocked",
                deferred_reason="final_execution_readiness_deferred",
                allowed_reason="final_execution_readiness_authorized",
            ),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def propagate_blocked_deferred(self, dry_run: RuntimeRecoveryDryRunReport | Any) -> dict[str, Any]:
        report = self._dry_run_report(dry_run)
        simulations = report.blocked_deferred_dry_runs()
        blocked = [
            self._safe_text(item.get("contract_id"))
            for item in simulations
            if self._safe_text(item.get("status")) == DRY_RUN_BLOCKED
        ]
        deferred = [
            self._safe_text(item.get("contract_id"))
            for item in simulations
            if self._safe_text(item.get("status")) == DRY_RUN_DEFERRED
        ]
        result = {
            "gate": "blocked_deferred_propagation",
            "state": self._gate_state(blocked=bool(blocked), deferred=bool(deferred)),
            "commit_allowed": not blocked and not deferred,
            "requires_manual_confirmation": False,
            "blocked_count": len(blocked),
            "deferred_count": len(deferred),
            "blocked_contracts": sorted(blocked),
            "deferred_contracts": sorted(deferred),
            "reason": self._reason(
                blocked=bool(blocked),
                deferred=bool(deferred),
                blocked_reason="blocked_dry_runs_propagated",
                deferred_reason="deferred_dry_runs_propagated",
                allowed_reason="no_blocked_or_deferred_dry_runs",
            ),
            "action": "none",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def _dry_run_report(self, source: Any) -> RuntimeRecoveryDryRunReport:
        if isinstance(source, RuntimeRecoveryDryRunReport):
            return RuntimeRecoveryDryRunReport(source.payload)
        return RuntimeRecoveryDryRunReport({})

    def _commit_summary(
        self,
        final_readiness: dict[str, Any],
        blocked_deferred: dict[str, Any],
    ) -> dict[str, Any]:
        summary = {
            "state": self._safe_text(final_readiness.get("state")),
            "commit_allowed": bool(final_readiness.get("commit_allowed", False)),
            "requires_manual_confirmation": bool(final_readiness.get("requires_manual_confirmation", False)),
            "blocked_count": self._safe_int(blocked_deferred.get("blocked_count"), 0),
            "deferred_count": self._safe_int(blocked_deferred.get("deferred_count"), 0),
            "authorization_only": True,
            "executes_action": False,
        }
        summary["fingerprint"] = self._fingerprint(summary)
        return summary

    def _all_simulations(self, report: RuntimeRecoveryDryRunReport) -> list[dict[str, Any]]:
        simulations = []
        simulations.extend(report.replay_dry_runs())
        simulations.extend(report.rollback_dry_runs())
        simulations.extend(report.failed_recovery_dry_runs())
        simulations.extend(report.blocked_deferred_dry_runs())
        simulations.extend(report.sequence_simulation())
        guard = report.guard_simulation()
        confirmation = report.confirmation_simulation()
        if guard:
            simulations.append(guard)
        if confirmation:
            simulations.append(confirmation)
        return [
            copy.deepcopy(item)
            for item in simulations
            if isinstance(item, dict)
        ]

    def _missing_dry_run_evidence(self, report: RuntimeRecoveryDryRunReport) -> bool:
        payload = report.payload
        return (
            self._safe_text(payload.get("schema")) != RuntimeRecoveryDryRunReport.SCHEMA
            or not report.fingerprint
            or not report.dry_run_summary()
        )

    def _simulation_statuses(self, simulations: list[dict[str, Any]]) -> list[str]:
        return [
            self._safe_text(item.get("status"))
            for item in simulations
            if isinstance(item, dict)
        ]

    def _gate_state(self, *, blocked: bool, deferred: bool) -> str:
        if blocked:
            return COMMIT_BLOCKED
        if deferred:
            return COMMIT_DEFERRED
        return COMMIT_ALLOWED

    def _reason(
        self,
        *,
        blocked: bool,
        deferred: bool,
        blocked_reason: str,
        deferred_reason: str,
        allowed_reason: str,
    ) -> str:
        if blocked:
            return blocked_reason
        if deferred:
            return deferred_reason
        return allowed_reason

    def _confirmation_reason(
        self,
        *,
        blocked: bool,
        requires_manual_confirmation: bool,
    ) -> str:
        if blocked:
            return "confirmation_requirements_blocked"
        if requires_manual_confirmation:
            return "manual_confirmation_required"
        return "manual_confirmation_satisfied"

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

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


def gate_runtime_recovery_commit(
    source: Any,
    *,
    manual_confirmation_provided: bool = False,
) -> RuntimeRecoveryCommitGateReport:
    return RuntimeRecoveryCommitGate().evaluate(
        source,
        manual_confirmation_provided=manual_confirmation_provided,
    )


__all__ = [
    "COMMIT_ALLOWED",
    "COMMIT_BLOCKED",
    "COMMIT_DEFERRED",
    "RuntimeRecoveryCommitGate",
    "RuntimeRecoveryCommitGateReport",
    "gate_runtime_recovery_commit",
]
