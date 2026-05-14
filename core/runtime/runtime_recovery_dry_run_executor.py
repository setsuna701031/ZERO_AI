from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_recovery_execution_contract import (
    CONTRACT_STATUS_APPROVED,
    CONTRACT_STATUS_BLOCKED,
    CONTRACT_STATUS_DEFERRED,
    RuntimeRecoveryExecutionContractReport,
)
from core.runtime.runtime_recovery_execution_review import (
    REVIEW_READY,
    RuntimeRecoveryExecutionReviewReport,
    RuntimeRecoveryExecutionReviewer,
)


DRY_RUN_SIMULATED = "simulated"
DRY_RUN_BLOCKED = "blocked"
DRY_RUN_DEFERRED = "deferred"


class RuntimeRecoveryDryRunReport:
    SCHEMA = "zero.runtime.recovery_dry_run.v1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = self._json_safe(payload)

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return str(self._payload.get("fingerprint") or "")

    def dry_run_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("dry_run_summary", {}))

    def replay_dry_runs(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("replay_dry_runs", []))

    def rollback_dry_runs(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("rollback_dry_runs", []))

    def failed_recovery_dry_runs(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("failed_recovery_dry_runs", []))

    def blocked_deferred_dry_runs(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("blocked_deferred_dry_runs", []))

    def sequence_simulation(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._payload.get("sequence_simulation", []))

    def guard_simulation(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("guard_simulation", {}))

    def confirmation_simulation(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload.get("confirmation_simulation", {}))

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


class RuntimeRecoveryDryRunExecutor:
    """Simulation-only executor over reviewed recovery execution contracts."""

    def __init__(
        self,
        *,
        reviewer: RuntimeRecoveryExecutionReviewer | None = None,
    ) -> None:
        self.reviewer = reviewer if reviewer is not None else RuntimeRecoveryExecutionReviewer()

    def dry_run(self, source: Any) -> RuntimeRecoveryDryRunReport:
        context = self._context(source)
        contract_report = context["contract"]
        review_report = context["review"]
        replay_dry_runs = self.simulate_replay_execution(contract_report, review_report)
        rollback_dry_runs = self.simulate_rollback_execution(contract_report, review_report)
        failed_recovery_dry_runs = self.simulate_failed_recovery_execution(contract_report, review_report)
        blocked_deferred_dry_runs = self.handle_blocked_deferred_dry_runs(contract_report, review_report)
        sequence_simulation = self.simulate_execution_sequence(
            replay_dry_runs=replay_dry_runs,
            failed_recovery_dry_runs=failed_recovery_dry_runs,
            rollback_dry_runs=rollback_dry_runs,
            blocked_deferred_dry_runs=blocked_deferred_dry_runs,
        )
        guard_simulation = self.simulate_guard_risk(contract_report, review_report)
        confirmation_simulation = self.simulate_confirmation_gate(contract_report, review_report)
        dry_run_summary = self._dry_run_summary(
            sequence_simulation=sequence_simulation,
            guard_simulation=guard_simulation,
            confirmation_simulation=confirmation_simulation,
        )
        payload = {
            "ok": True,
            "schema": RuntimeRecoveryDryRunReport.SCHEMA,
            "mode": "dry_run_simulation_only",
            "read_only": True,
            "executes_recovery": False,
            "executes_rollback": False,
            "executes_repair": False,
            "source": {
                "execution_contract_fingerprint": contract_report.fingerprint,
                "execution_review_fingerprint": review_report.fingerprint,
            },
            "dry_run_summary": dry_run_summary,
            "replay_dry_runs": replay_dry_runs,
            "rollback_dry_runs": rollback_dry_runs,
            "failed_recovery_dry_runs": failed_recovery_dry_runs,
            "blocked_deferred_dry_runs": blocked_deferred_dry_runs,
            "sequence_simulation": sequence_simulation,
            "guard_simulation": guard_simulation,
            "confirmation_simulation": confirmation_simulation,
        }
        payload["fingerprint"] = self._fingerprint(payload)
        return RuntimeRecoveryDryRunReport(payload)

    def simulate_replay_execution(
        self,
        contract: RuntimeRecoveryExecutionContractReport | Any,
        review: RuntimeRecoveryExecutionReviewReport | None = None,
    ) -> list[dict[str, Any]]:
        contract_report = self._contract_report(contract)
        review_report = self._review_report(review, contract_report)
        replay_review = review_report.replay_integrity_review()
        return [
            self._simulation_from_contract(
                item,
                simulation_type="replay",
                review_state=self._safe_text(replay_review.get("state")),
                simulated_action="simulate_replay_reconstruction",
            )
            for item in contract_report.replay_contracts()
        ]

    def simulate_rollback_execution(
        self,
        contract: RuntimeRecoveryExecutionContractReport | Any,
        review: RuntimeRecoveryExecutionReviewReport | None = None,
    ) -> list[dict[str, Any]]:
        contract_report = self._contract_report(contract)
        review_report = self._review_report(review, contract_report)
        summary_state = self._safe_text(review_report.review_summary().get("state"))
        simulations = [
            self._simulation_from_contract(
                item,
                simulation_type="rollback",
                review_state=summary_state,
                simulated_action="simulate_rollback_sequence",
            )
            for item in contract_report.rollback_contracts()
        ]
        return sorted(
            simulations,
            key=lambda item: (
                self._safe_int(item.get("metadata", {}).get("replay_order"), 0),
                self._safe_text(item.get("contract_id")),
            ),
        )

    def simulate_failed_recovery_execution(
        self,
        contract: RuntimeRecoveryExecutionContractReport | Any,
        review: RuntimeRecoveryExecutionReviewReport | None = None,
    ) -> list[dict[str, Any]]:
        contract_report = self._contract_report(contract)
        review_report = self._review_report(review, contract_report)
        summary_state = self._safe_text(review_report.review_summary().get("state"))
        return [
            self._simulation_from_contract(
                item,
                simulation_type="failed_execution_recovery",
                review_state=summary_state,
                simulated_action="simulate_failed_execution_recovery",
            )
            for item in contract_report.failed_execution_contracts()
        ]

    def handle_blocked_deferred_dry_runs(
        self,
        contract: RuntimeRecoveryExecutionContractReport | Any,
        review: RuntimeRecoveryExecutionReviewReport | None = None,
    ) -> list[dict[str, Any]]:
        contract_report = self._contract_report(contract)
        review_report = self._review_report(review, contract_report)
        explanations = review_report.blocked_deferred_review().get("explanations")
        if not isinstance(explanations, list):
            explanations = []
        explanation_index = {
            self._safe_text(item.get("contract_id")): self._safe_text(item.get("reason"))
            for item in explanations
            if isinstance(item, dict)
        }
        simulations = []
        for item in contract_report.blocked_contracts():
            if not isinstance(item, dict):
                continue
            simulation = self._simulation_from_contract(
                item,
                simulation_type="blocked_or_deferred",
                review_state=self._safe_text(
                    "deferred" if item.get("status") == CONTRACT_STATUS_DEFERRED else "blocked"
                ),
                simulated_action="simulate_blocked_or_deferred_explanation",
            )
            simulation["explanation"] = explanation_index.get(
                self._safe_text(item.get("contract_id")),
                self._safe_text(item.get("approval_reason")),
            )
            simulation["fingerprint"] = self._fingerprint(simulation)
            simulations.append(simulation)
        return sorted(simulations, key=lambda item: self._safe_text(item.get("contract_id")))

    def simulate_execution_sequence(
        self,
        *,
        replay_dry_runs: list[dict[str, Any]],
        failed_recovery_dry_runs: list[dict[str, Any]],
        rollback_dry_runs: list[dict[str, Any]],
        blocked_deferred_dry_runs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        sequence = []
        for item in self._safe_simulation_list(blocked_deferred_dry_runs):
            sequence.append(self._sequence_item(item, "blocked_or_deferred"))
        for item in self._safe_simulation_list(replay_dry_runs):
            sequence.append(self._sequence_item(item, "replay"))
        for item in self._safe_simulation_list(failed_recovery_dry_runs):
            sequence.append(self._sequence_item(item, "failed_execution_recovery"))
        for item in self._safe_simulation_list(rollback_dry_runs):
            sequence.append(self._sequence_item(item, "rollback"))
        ordered = []
        for index, item in enumerate(sequence):
            item["sequence_order"] = index
            item["fingerprint"] = self._fingerprint(item)
            ordered.append(item)
        return ordered

    def simulate_guard_risk(
        self,
        contract: RuntimeRecoveryExecutionContractReport | Any,
        review: RuntimeRecoveryExecutionReviewReport | None = None,
    ) -> dict[str, Any]:
        contract_report = self._contract_report(contract)
        review_report = self._review_report(review, contract_report)
        risk = review_report.risk_summary()
        result = {
            "simulation": "guard_risk",
            "status": DRY_RUN_SIMULATED if risk.get("all_guards_ok") else DRY_RUN_BLOCKED,
            "guard_failure_count": self._safe_int(risk.get("guard_failure_count"), 0),
            "executable_contract_count": self._safe_int(risk.get("executable_contract_count"), 0),
            "all_executable_false": bool(risk.get("all_executable_false", False)),
            "all_guards_ok": bool(risk.get("all_guards_ok", False)),
            "simulated_action": "simulate_guard_and_risk_checks",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def simulate_confirmation_gate(
        self,
        contract: RuntimeRecoveryExecutionContractReport | Any,
        review: RuntimeRecoveryExecutionReviewReport | None = None,
    ) -> dict[str, Any]:
        contract_report = self._contract_report(contract)
        review_report = self._review_report(review, contract_report)
        confirmation = review_report.confirmation_review()
        ready = self._safe_text(confirmation.get("state")) == REVIEW_READY
        result = {
            "simulation": "confirmation_gate",
            "status": DRY_RUN_SIMULATED if ready else DRY_RUN_BLOCKED,
            "confirmation_ready": ready,
            "missing_confirmation_count": self._safe_int(confirmation.get("missing_confirmation_count"), 0),
            "executable_contract_count": self._safe_int(confirmation.get("executable_contract_count"), 0),
            "simulated_action": "simulate_confirmation_gate",
            "executes_action": False,
        }
        result["fingerprint"] = self._fingerprint(result)
        return result

    def _context(self, source: Any) -> dict[str, RuntimeRecoveryExecutionContractReport | RuntimeRecoveryExecutionReviewReport]:
        if isinstance(source, RuntimeRecoveryExecutionReviewReport):
            review = RuntimeRecoveryExecutionReviewReport(source.payload)
            contract = RuntimeRecoveryExecutionContractReport({})
            return {"contract": contract, "review": review}
        contract = self._contract_report(source)
        review = self.reviewer.review(contract)
        return {"contract": contract, "review": review}

    def _simulation_from_contract(
        self,
        contract: dict[str, Any],
        *,
        simulation_type: str,
        review_state: str,
        simulated_action: str,
    ) -> dict[str, Any]:
        status = self._safe_text(contract.get("status"))
        if status == CONTRACT_STATUS_APPROVED and review_state == REVIEW_READY:
            dry_run_status = DRY_RUN_SIMULATED
        elif status == CONTRACT_STATUS_DEFERRED or review_state == "deferred":
            dry_run_status = DRY_RUN_DEFERRED
        else:
            dry_run_status = DRY_RUN_BLOCKED
        simulation = {
            "dry_run_id": f"dry-run:{self._safe_text(contract.get('contract_id'))}",
            "contract_id": self._safe_text(contract.get("contract_id")),
            "contract_type": self._safe_text(contract.get("contract_type")),
            "simulation_type": simulation_type,
            "status": dry_run_status,
            "contract_status": status,
            "review_state": review_state,
            "simulated_action": simulated_action,
            "would_execute": False,
            "executes_action": False,
            "metadata": self._safe_mapping(contract.get("metadata")),
        }
        simulation["fingerprint"] = self._fingerprint(simulation)
        return simulation

    def _sequence_item(self, simulation: dict[str, Any], stage_type: str) -> dict[str, Any]:
        return {
            "sequence_order": 0,
            "stage_type": stage_type,
            "dry_run_id": self._safe_text(simulation.get("dry_run_id")),
            "contract_id": self._safe_text(simulation.get("contract_id")),
            "status": self._safe_text(simulation.get("status")),
            "simulated_action": self._safe_text(simulation.get("simulated_action")),
            "would_execute": False,
            "executes_action": False,
        }

    def _dry_run_summary(
        self,
        *,
        sequence_simulation: list[dict[str, Any]],
        guard_simulation: dict[str, Any],
        confirmation_simulation: dict[str, Any],
    ) -> dict[str, Any]:
        statuses = [
            self._safe_text(item.get("status"))
            for item in sequence_simulation
            if isinstance(item, dict)
        ]
        blocked_count = statuses.count(DRY_RUN_BLOCKED)
        deferred_count = statuses.count(DRY_RUN_DEFERRED)
        simulated_count = statuses.count(DRY_RUN_SIMULATED)
        if blocked_count or guard_simulation.get("status") == DRY_RUN_BLOCKED or confirmation_simulation.get("status") == DRY_RUN_BLOCKED:
            status = DRY_RUN_BLOCKED
        elif deferred_count:
            status = DRY_RUN_DEFERRED
        else:
            status = DRY_RUN_SIMULATED
        summary = {
            "status": status,
            "sequence_count": len(sequence_simulation),
            "simulated_count": simulated_count,
            "deferred_count": deferred_count,
            "blocked_count": blocked_count,
            "simulation_only": True,
            "would_execute_anything": False,
            "executes_action": False,
        }
        summary["fingerprint"] = self._fingerprint(summary)
        return summary

    def _contract_report(self, source: Any) -> RuntimeRecoveryExecutionContractReport:
        if isinstance(source, RuntimeRecoveryExecutionContractReport):
            return RuntimeRecoveryExecutionContractReport(source.payload)
        return RuntimeRecoveryExecutionContractReport({})

    def _review_report(
        self,
        review: RuntimeRecoveryExecutionReviewReport | None,
        contract: RuntimeRecoveryExecutionContractReport,
    ) -> RuntimeRecoveryExecutionReviewReport:
        if isinstance(review, RuntimeRecoveryExecutionReviewReport):
            return RuntimeRecoveryExecutionReviewReport(review.payload)
        return self.reviewer.review(contract)

    def _safe_simulation_list(self, value: Any) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(item)
            for item in value
            if isinstance(item, dict)
        ] if isinstance(value, list) else []

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


def dry_run_runtime_recovery(source: Any) -> RuntimeRecoveryDryRunReport:
    return RuntimeRecoveryDryRunExecutor().dry_run(source)


__all__ = [
    "DRY_RUN_BLOCKED",
    "DRY_RUN_DEFERRED",
    "DRY_RUN_SIMULATED",
    "RuntimeRecoveryDryRunExecutor",
    "RuntimeRecoveryDryRunReport",
    "dry_run_runtime_recovery",
]
