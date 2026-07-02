from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.runtime.runtime_persistence_service import RuntimePersistenceService
from core.runtime.aer_runtime_recovery_planner import build_recovery_plan
from core.runtime.aer_runtime_recovery_validation import RECOVERY_ELIGIBILITY_CONTRACT
from core.runtime.runtime_evidence_chain import build_runtime_evidence_record
from core.runtime.runtime_recovery_dry_run_executor import dry_run_runtime_recovery
from core.runtime.runtime_recovery_observer import observe_runtime_recovery


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_supervisor_bridge_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeRecoveryActivationResult:
    ok: bool
    status: str
    activated: bool = False
    no_op: bool = True
    reason: str = ""
    admission: dict[str, Any] = field(default_factory=dict)
    activation_intent: dict[str, Any] = field(default_factory=dict)
    observation_result: dict[str, Any] = field(default_factory=dict)
    dry_run_result: dict[str, Any] = field(default_factory=dict)
    execution_gate_result: dict[str, Any] = field(default_factory=dict)
    recovery_plan_result: dict[str, Any] = field(default_factory=dict)
    real_executor_adapter_contract_result: dict[str, Any] = field(default_factory=dict)
    real_executor_adapter_contract_verification_result: dict[str, Any] = field(default_factory=dict)
    real_executor_import_boundary_result: dict[str, Any] = field(default_factory=dict)
    real_executor_factory_boundary_result: dict[str, Any] = field(default_factory=dict)
    real_executor_instance_contract_result: dict[str, Any] = field(default_factory=dict)
    real_executor_instance_contract_verification_result: dict[str, Any] = field(default_factory=dict)
    real_executor_instance_creation_boundary_result: dict[str, Any] = field(default_factory=dict)
    real_executor_instance_factory_contract_result: dict[str, Any] = field(default_factory=dict)
    real_executor_instance_factory_contract_verification_result: dict[str, Any] = field(default_factory=dict)
    executor_binding_result: dict[str, Any] = field(default_factory=dict)
    executor_wiring_result: dict[str, Any] = field(default_factory=dict)
    executor_invocation_guard_result: dict[str, Any] = field(default_factory=dict)
    executor_invocation_result: dict[str, Any] = field(default_factory=dict)
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "activated": self.activated,
            "no_op": self.no_op,
            "reason": self.reason,
            "admission": copy.deepcopy(self.admission),
            "activation_intent": copy.deepcopy(self.activation_intent),
            "observation_result": copy.deepcopy(self.observation_result),
            "dry_run_result": copy.deepcopy(self.dry_run_result),
            "execution_gate_result": copy.deepcopy(self.execution_gate_result),
            "recovery_plan_result": copy.deepcopy(self.recovery_plan_result),
            "real_executor_adapter_contract_result": copy.deepcopy(self.real_executor_adapter_contract_result),
            "real_executor_adapter_contract_verification_result": copy.deepcopy(self.real_executor_adapter_contract_verification_result),
            "real_executor_import_boundary_result": copy.deepcopy(self.real_executor_import_boundary_result),
            "real_executor_factory_boundary_result": copy.deepcopy(self.real_executor_factory_boundary_result),
            "real_executor_instance_contract_result": copy.deepcopy(self.real_executor_instance_contract_result),
            "real_executor_instance_contract_verification_result": copy.deepcopy(self.real_executor_instance_contract_verification_result),
            "real_executor_instance_creation_boundary_result": copy.deepcopy(self.real_executor_instance_creation_boundary_result),
            "real_executor_instance_factory_contract_result": copy.deepcopy(self.real_executor_instance_factory_contract_result),
            "real_executor_instance_factory_contract_verification_result": copy.deepcopy(self.real_executor_instance_factory_contract_verification_result),
            "executor_binding_result": copy.deepcopy(self.executor_binding_result),
            "executor_wiring_result": copy.deepcopy(self.executor_wiring_result),
            "executor_invocation_guard_result": copy.deepcopy(self.executor_invocation_guard_result),
            "executor_invocation_result": copy.deepcopy(self.executor_invocation_result),
            "evidence_records": copy.deepcopy(self.evidence_records),
            "recovery_execution_allowed": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "dry_run_only": True,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeSupervisorBridgeResult:
    ok: bool
    bridge_id: str
    current_tick: int
    watchdog_lease_result: dict[str, Any] = field(default_factory=dict)
    supervisor_cases: list[dict[str, Any]] = field(default_factory=list)
    recovery_results: list[dict[str, Any]] = field(default_factory=list)
    recovery_activation_result: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "bridge_id": self.bridge_id,
            "runtime_phase": "runtime_supervisor_bridge",
            "current_tick": self.current_tick,
            "watchdog_lease_result": copy.deepcopy(self.watchdog_lease_result),
            "supervisor_cases": copy.deepcopy(self.supervisor_cases),
            "recovery_results": copy.deepcopy(self.recovery_results),
            "recovery_activation_result": copy.deepcopy(self.recovery_activation_result),
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class RuntimeSupervisorBridgeEvent:
    event_id: str
    event_type: str
    bridge_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "bridge_id": self.bridge_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_supervisor_bridge",
        }


class RuntimeSupervisorBridgeRejected(RuntimeError):
    pass


class RuntimeSupervisorBridge:
    """
    Mainline bridge for the governed runtime fabric.

    Canonical flow:
        watchdog_lease_bridge.tick()
          -> incidents
          -> supervisor.process_many()
          -> recovery_orchestrator.consume_ready()

    This bridge does not own watchdog, lease, supervisor, or recovery internals.
    It only wires the lifecycle together and produces an auditable bridge result.
    """

    def __init__(
        self,
        *,
        watchdog_lease_bridge: Any,
        supervisor: Any,
        recovery_orchestrator: Any = None,
        storage_path: str | Path | None = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        if watchdog_lease_bridge is None:
            raise RuntimeSupervisorBridgeRejected("watchdog_lease_bridge_required")
        if supervisor is None:
            raise RuntimeSupervisorBridgeRejected("runtime_supervisor_required")

        self.watchdog_lease_bridge = watchdog_lease_bridge
        self.supervisor = supervisor
        self.recovery_orchestrator = recovery_orchestrator
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.persistence_service = RuntimePersistenceService(
            workspace_root=(self.storage_path.parent if self.storage_path is not None else "workspace"),
            source="runtime_supervisor_bridge",
        )
        self.journal = journal
        self.audit = audit
        self._results: list[RuntimeSupervisorBridgeResult] = []
        self._events: list[RuntimeSupervisorBridgeEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeSupervisorBridge":
        root = Path(workspace_root)
        bridge_dir = root / "runtime_supervisor_bridge"
        bridge_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=bridge_dir / "runtime_supervisor_bridge.json", **kwargs)

    def tick(
        self,
        *,
        current_tick: int,
        submit_to_recovery_from_watchdog: bool = False,
        run_recovery_queue: bool = True,
        recovery_limit: int = 10,
        recovery_activation_enabled: bool = False,
        recovery_kill_switch_engaged: bool = False,
        recovery_admission: Any = None,
        recovery_observation_only: bool = True,
        recovery_execution_gate_enabled: bool = False,
        recovery_executor_enabled: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSupervisorBridgeResult:
        """
        Run one governed supervisor bridge cycle.

        submit_to_recovery_from_watchdog should normally remain False here.
        The supervisor is the authority that decides recover/takeover/freeze.
        """

        bridge_id = "runtime-supervisor-bridge-" + stable_supervisor_bridge_fingerprint(
            {
                "current_tick": current_tick,
                "sequence": len(self._results) + 1,
            }
        )[:16]

        watchdog_lease_result = self.watchdog_lease_bridge.tick(
            current_tick=current_tick,
            submit_to_recovery=submit_to_recovery_from_watchdog,
        )
        incidents = watchdog_lease_result.get("incidents", [])
        if not isinstance(incidents, list):
            incidents = []

        self._append_event(
            "runtime_supervisor_bridge_watchdog_lease_tick",
            bridge_id=bridge_id,
            payload={"watchdog_lease_result": copy.deepcopy(watchdog_lease_result)},
        )

        supervisor_cases = []
        if incidents:
            if hasattr(self.supervisor, "process_many"):
                cases = self.supervisor.process_many(
                    [item for item in incidents if isinstance(item, dict)],
                    current_tick=current_tick,
                )
            else:
                cases = [
                    self.supervisor.process_incident(item, current_tick=current_tick)
                    for item in incidents
                    if isinstance(item, dict)
                ]

            for case in cases:
                supervisor_cases.append(case.to_dict() if hasattr(case, "to_dict") else copy.deepcopy(case))

        self._append_event(
            "runtime_supervisor_bridge_supervisor_processed",
            bridge_id=bridge_id,
            payload={"supervisor_cases": copy.deepcopy(supervisor_cases)},
        )

        recovery_results = []
        orchestrator = self.recovery_orchestrator or getattr(self.supervisor, "orchestrator", None)
        if run_recovery_queue and orchestrator is not None and hasattr(orchestrator, "consume_ready"):
            queued_recovery = any(
                str(case.get("status") or "") == "recovery_queued"
                or bool(case.get("recovery_ticket"))
                for case in supervisor_cases
                if isinstance(case, dict)
            )
            if queued_recovery:
                consumed = orchestrator.consume_ready(
                    current_tick=current_tick,
                    limit=recovery_limit,
                )
                for item in consumed:
                    recovery_results.append(item.to_dict() if hasattr(item, "to_dict") else copy.deepcopy(item))

        self._append_event(
            "runtime_supervisor_bridge_recovery_consumed",
            bridge_id=bridge_id,
            payload={"recovery_results": copy.deepcopy(recovery_results)},
        )

        recovery_activation_result = self._evaluate_recovery_activation_hook(
            bridge_id=bridge_id,
            current_tick=current_tick,
            enabled=recovery_activation_enabled,
            kill_switch_engaged=recovery_kill_switch_engaged,
            admission=recovery_admission,
            observation_only=recovery_observation_only,
            execution_gate_enabled=recovery_execution_gate_enabled,
            executor_enabled=recovery_executor_enabled,
            supervisor_cases=supervisor_cases,
            metadata=metadata,
        )
        activation_evidence_records = recovery_activation_result.evidence_records
        if activation_evidence_records:
            self._append_event(
                "runtime_supervisor_bridge_recovery_gate_evidence",
                bridge_id=bridge_id,
                payload={"evidence_records": copy.deepcopy(activation_evidence_records)},
            )

        result = RuntimeSupervisorBridgeResult(
            ok=True,
            bridge_id=bridge_id,
            current_tick=int(current_tick),
            watchdog_lease_result=copy.deepcopy(watchdog_lease_result),
            supervisor_cases=copy.deepcopy(supervisor_cases),
            recovery_results=copy.deepcopy(recovery_results),
            recovery_activation_result=recovery_activation_result.to_dict(),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._results.append(result)
        self.save()
        self._record_external_event(
            {
                "event_type": "runtime_supervisor_bridge_tick_completed",
                "payload": result.to_dict(),
                "timestamp": utc_timestamp(),
                "source": "runtime_supervisor_bridge",
            }
        )
        return copy.deepcopy(result)

    def register_session(
        self,
        session_id: str,
        owner_id: str,
        *,
        task_id: str = "",
        current_tick: int = 0,
        acquire_lease: bool = True,
        ttl_ticks: int | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not hasattr(self.watchdog_lease_bridge, "register_session"):
            raise RuntimeSupervisorBridgeRejected("watchdog_lease_bridge_register_session_unavailable")
        result = self.watchdog_lease_bridge.register_session(
            session_id,
            owner_id,
            task_id=task_id,
            current_tick=current_tick,
            acquire_lease=acquire_lease,
            ttl_ticks=ttl_ticks,
            payload=payload,
            metadata=metadata,
        )
        self._record_external_event(
            {
                "event_type": "runtime_supervisor_bridge_session_registered",
                "payload": copy.deepcopy(result),
                "timestamp": utc_timestamp(),
                "source": "runtime_supervisor_bridge",
            }
        )
        self.save()
        return copy.deepcopy(result)

    def heartbeat(
        self,
        session_id: str,
        owner_id: str,
        *,
        task_id: str = "",
        current_tick: int = 0,
        watchdog_status: str = "running",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not hasattr(self.watchdog_lease_bridge, "heartbeat"):
            raise RuntimeSupervisorBridgeRejected("watchdog_lease_bridge_heartbeat_unavailable")
        result = self.watchdog_lease_bridge.heartbeat(
            session_id,
            owner_id,
            task_id=task_id,
            current_tick=current_tick,
            watchdog_status=watchdog_status,
            payload=payload,
            metadata=metadata,
        )
        self._record_external_event(
            {
                "event_type": "runtime_supervisor_bridge_heartbeat",
                "payload": copy.deepcopy(result),
                "timestamp": utc_timestamp(),
                "source": "runtime_supervisor_bridge",
            }
        )
        self.save()
        return copy.deepcopy(result)

    def latest_result(self) -> RuntimeSupervisorBridgeResult | None:
        if not self._results:
            return None
        return copy.deepcopy(self._results[-1])

    def list_results(self) -> list[RuntimeSupervisorBridgeResult]:
        return [copy.deepcopy(item) for item in self._results]

    def list_events(self) -> list[RuntimeSupervisorBridgeEvent]:
        return [copy.deepcopy(item) for item in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_supervisor_bridge",
            "results": [item.to_dict() for item in self._results[-300:]],
            "events": [item.to_dict() for item in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._results = []
            self._events = []
            return

        payload = self.persistence_service.read_json(
            self.storage_path,
            default={},
        )
        self._results = []
        self._events = []
        if not isinstance(payload, dict):
            return

        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            result = RuntimeSupervisorBridgeResult(
                ok=bool(item.get("ok", False)),
                bridge_id=str(item.get("bridge_id") or ""),
                current_tick=int(item.get("current_tick") or 0),
                watchdog_lease_result=copy.deepcopy(item.get("watchdog_lease_result") if isinstance(item.get("watchdog_lease_result"), dict) else {}),
                supervisor_cases=copy.deepcopy(item.get("supervisor_cases") if isinstance(item.get("supervisor_cases"), list) else []),
                recovery_results=copy.deepcopy(item.get("recovery_results") if isinstance(item.get("recovery_results"), list) else []),
                recovery_activation_result=copy.deepcopy(item.get("recovery_activation_result") if isinstance(item.get("recovery_activation_result"), dict) else {}),
                payload=copy.deepcopy(item.get("payload") if isinstance(item.get("payload"), dict) else {}),
                metadata=copy.deepcopy(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                timestamp=str(item.get("timestamp") or utc_timestamp()),
            )
            if result.bridge_id:
                self._results.append(result)

        for item in payload.get("events") or []:
            if not isinstance(item, dict):
                continue
            event = RuntimeSupervisorBridgeEvent(
                event_id=str(item.get("event_id") or ""),
                event_type=str(item.get("event_type") or ""),
                bridge_id=str(item.get("bridge_id") or ""),
                payload=copy.deepcopy(item.get("payload") if isinstance(item.get("payload"), dict) else {}),
                metadata=copy.deepcopy(item.get("metadata") if isinstance(item.get("metadata"), dict) else {}),
                timestamp=str(item.get("timestamp") or utc_timestamp()),
            )
            if event.event_id:
                self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.persistence_service.write_json(
            self.storage_path,
            self.to_dict(),
            reason="runtime_supervisor_bridge_save",
            metadata={"runtime_supervisor_bridge": True},
        )

    def _evaluate_recovery_activation_hook(
        self,
        *,
        bridge_id: str,
        current_tick: int,
        enabled: bool,
        kill_switch_engaged: bool,
        admission: Any,
        observation_only: bool,
        execution_gate_enabled: bool,
        executor_enabled: bool,
        supervisor_cases: list[dict[str, Any]],
        metadata: dict[str, Any] | None,
    ) -> RuntimeRecoveryActivationResult:
        default_import_boundary_result = {
            "status": "real_executor_import_boundary_disabled",
            "reason": "real executor import boundary disabled by default",
            "recovery_real_executor_enabled": bool(executor_enabled),
            "guard_ready": False,
            "adapter_contract_valid": False,
            "adapter_contract_verified": False,
            "selected_executor_module": "",
            "selected_executor_function_name": "",
            "module": "",
            "callable_name": "",
            "required_input": "recovery_plan_result",
            "input_source": "",
            "import_boundary_ready": False,
            "import_boundary_decision": "disabled",
            "blocked_reason": "disabled",
            "blocked": True,
            "import_check_allowed": False,
            "import_attempted": False,
            "import_lookup_available": False,
            "real_executor_imported": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        default_factory_boundary_result = {
            "status": "real_executor_factory_boundary_disabled",
            "reason": "real executor factory boundary disabled by default",
            "factory_boundary_enabled": False,
            "factory_boundary_ready": False,
            "factory_boundary_decision": "disabled",
            "blocked_reason": "disabled",
            "blocked": True,
            "factory_contract_verified": False,
            "factory_creation_allowed": False,
            "factory_attempted": False,
            "factory_available": False,
            "factory_created": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        default_instance_contract_result = {
            "status": "real_executor_instance_contract_disabled",
            "reason": "real executor instance contract disabled by default",
            "instance_contract_enabled": False,
            "instance_contract_verified": False,
            "instance_contract_ready": False,
            "instance_contract_decision": "disabled",
            "blocked_reason": "disabled",
            "blocked": True,
            "factory_boundary_ready": False,
            "factory_boundary_status": "",
            "factory_contract_verified": False,
            "instance_type": "RuntimeRecoveryExecutor",
            "required_method": "execute_recovery",
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "plan_id": "",
            "instance_creation_allowed": False,
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        default_instance_contract_verification_result = {
            "status": "real_executor_instance_contract_verification_disabled",
            "reason": "real executor instance contract verification disabled by default",
            "verification_contract_version": "zero.runtime.recovery.real_executor_instance_contract_verification.v1",
            "checks": {},
            "missing_or_invalid": [],
            "instance_contract_verified": False,
            "instance_type": "RuntimeRecoveryExecutor",
            "required_method": "execute_recovery",
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        default_instance_creation_boundary_result = {
            "status": "real_executor_instance_creation_boundary_disabled",
            "reason": "real executor instance creation boundary disabled by default",
            "instance_creation_boundary_enabled": False,
            "instance_creation_boundary_ready": False,
            "instance_creation_boundary_decision": "disabled",
            "blocked_reason": "disabled",
            "blocked": True,
            "instance_contract_verified": False,
            "instance_contract_verification_status": "",
            "instance_type": "RuntimeRecoveryExecutor",
            "required_method": "execute_recovery",
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "plan_id": "",
            "instance_creation_allowed": False,
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        default_instance_factory_contract_result = {
            "status": "real_executor_instance_factory_contract_disabled",
            "reason": "real executor instance factory contract disabled by default",
            "factory_contract_enabled": False,
            "factory_contract_verified": False,
            "factory_contract_ready": False,
            "factory_contract_decision": "disabled",
            "blocked_reason": "disabled",
            "blocked": True,
            "instance_creation_boundary_ready": False,
            "instance_creation_boundary_status": "",
            "factory_module": "core.runtime.runtime_recovery_executor",
            "factory_name": "RuntimeRecoveryExecutor",
            "factory_method": "__init__",
            "instance_type": "RuntimeRecoveryExecutor",
            "required_method": "execute_recovery",
            "accepts_input": "recovery_plan_result",
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "creation_contract_version": "zero.runtime.recovery.real_executor_instance_factory_contract.v1",
            "plan_id": "",
            "factory_available": False,
            "factory_attempted": False,
            "factory_created": False,
            "instance_creation_allowed": False,
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        default_instance_factory_contract_verification_result = {
            "status": "real_executor_instance_factory_contract_verification_disabled",
            "reason": "real executor instance factory contract verification disabled by default",
            "verification_contract_version": "zero.runtime.recovery.real_executor_instance_factory_contract_verification.v1",
            "checks": {
                "factory_module": False,
                "factory_name": False,
                "factory_method": False,
                "instance_type": False,
                "required_method": False,
                "accepts_input": False,
                "creation_contract_version": False,
            },
            "missing_or_invalid": [
                "factory_module",
                "factory_name",
                "factory_method",
                "instance_type",
                "required_method",
                "accepts_input",
                "creation_contract_version",
            ],
            "factory_contract_verified": False,
            "factory_module": "core.runtime.runtime_recovery_executor",
            "factory_name": "RuntimeRecoveryExecutor",
            "factory_method": "__init__",
            "instance_type": "RuntimeRecoveryExecutor",
            "required_method": "execute_recovery",
            "accepts_input": "recovery_plan_result",
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "creation_contract_version": "zero.runtime.recovery.real_executor_instance_factory_contract.v1",
            "factory_available": False,
            "factory_attempted": False,
            "factory_created": False,
            "instance_creation_allowed": False,
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        if kill_switch_engaged:
            invocation_guard_result = self._build_executor_invocation_guard_result(
                activation_enabled=enabled,
                kill_switch_engaged=kill_switch_engaged,
                admission_allowed=False,
                observation_result={},
                dry_run_result={},
                execution_gate_result={},
                recovery_plan_result={},
                executor_binding_result={},
                recovery_executor_enabled=executor_enabled,
            )
            evidence_records = [
                self._build_recovery_gate_evidence_record(
                    bridge_id=bridge_id,
                    current_tick=current_tick,
                    stage="kill_switch_blocked",
                    reason="recovery activation blocked by kill switch",
                    metadata=metadata,
                ),
                self._build_recovery_gate_evidence_record(
                    bridge_id=bridge_id,
                    current_tick=current_tick,
                    stage=str(invocation_guard_result.get("status") or "executor_invocation_blocked"),
                    reason=str(invocation_guard_result.get("reason") or "executor invocation guard blocked"),
                    executor_invocation_guard_result=invocation_guard_result,
                    metadata=metadata,
                ),
            ]
            return RuntimeRecoveryActivationResult(
                ok=True,
                status="kill_switch_engaged",
                reason="recovery activation blocked by kill switch",
                real_executor_import_boundary_result=default_import_boundary_result,
                real_executor_factory_boundary_result=default_factory_boundary_result,
                real_executor_instance_contract_result=default_instance_contract_result,
                real_executor_instance_contract_verification_result=default_instance_contract_verification_result,
                real_executor_instance_creation_boundary_result=default_instance_creation_boundary_result,
                real_executor_instance_factory_contract_result=default_instance_factory_contract_result,
                real_executor_instance_factory_contract_verification_result=default_instance_factory_contract_verification_result,
                executor_invocation_guard_result=invocation_guard_result,
                evidence_records=evidence_records,
                metadata=copy.deepcopy(metadata or {}),
            )

        if not enabled:
            invocation_guard_result = self._build_executor_invocation_guard_result(
                activation_enabled=enabled,
                kill_switch_engaged=kill_switch_engaged,
                admission_allowed=False,
                observation_result={},
                dry_run_result={},
                execution_gate_result={},
                recovery_plan_result={},
                executor_binding_result={},
                recovery_executor_enabled=executor_enabled,
            )
            evidence_records = [
                self._build_recovery_gate_evidence_record(
                    bridge_id=bridge_id,
                    current_tick=current_tick,
                    stage="disabled",
                    reason="recovery activation hook disabled",
                    metadata=metadata,
                ),
                self._build_recovery_gate_evidence_record(
                    bridge_id=bridge_id,
                    current_tick=current_tick,
                    stage=str(invocation_guard_result.get("status") or "executor_invocation_blocked"),
                    reason=str(invocation_guard_result.get("reason") or "executor invocation guard blocked"),
                    executor_invocation_guard_result=invocation_guard_result,
                    metadata=metadata,
                ),
            ]
            return RuntimeRecoveryActivationResult(
                ok=True,
                status="disabled",
                reason="recovery activation hook disabled",
                real_executor_import_boundary_result=default_import_boundary_result,
                real_executor_factory_boundary_result=default_factory_boundary_result,
                real_executor_instance_contract_result=default_instance_contract_result,
                real_executor_instance_contract_verification_result=default_instance_contract_verification_result,
                real_executor_instance_creation_boundary_result=default_instance_creation_boundary_result,
                real_executor_instance_factory_contract_result=default_instance_factory_contract_result,
                real_executor_instance_factory_contract_verification_result=default_instance_factory_contract_verification_result,
                executor_invocation_guard_result=invocation_guard_result,
                evidence_records=evidence_records,
                metadata=copy.deepcopy(metadata or {}),
            )

        admission_result = self._normalize_recovery_admission(
            admission,
            bridge_id=bridge_id,
            current_tick=current_tick,
            supervisor_cases=supervisor_cases,
            metadata=metadata,
        )
        if admission_result.get("allowed") is not True:
            invocation_guard_result = self._build_executor_invocation_guard_result(
                activation_enabled=enabled,
                kill_switch_engaged=kill_switch_engaged,
                admission_allowed=False,
                observation_result={},
                dry_run_result={},
                execution_gate_result={},
                recovery_plan_result={},
                executor_binding_result={},
                recovery_executor_enabled=executor_enabled,
            )
            evidence_records = [
                self._build_recovery_gate_evidence_record(
                    bridge_id=bridge_id,
                    current_tick=current_tick,
                    stage="admission_denied",
                    reason=str(admission_result.get("reason") or "recovery activation admission denied"),
                    admission=admission_result,
                    metadata=metadata,
                ),
                self._build_recovery_gate_evidence_record(
                    bridge_id=bridge_id,
                    current_tick=current_tick,
                    stage=str(invocation_guard_result.get("status") or "executor_invocation_blocked"),
                    reason=str(invocation_guard_result.get("reason") or "executor invocation guard blocked"),
                    admission=admission_result,
                    executor_invocation_guard_result=invocation_guard_result,
                    metadata=metadata,
                ),
            ]
            return RuntimeRecoveryActivationResult(
                ok=True,
                status="admission_denied",
                reason=str(admission_result.get("reason") or "recovery activation admission denied"),
                admission=admission_result,
                real_executor_import_boundary_result=default_import_boundary_result,
                real_executor_factory_boundary_result=default_factory_boundary_result,
                real_executor_instance_contract_result=default_instance_contract_result,
                real_executor_instance_contract_verification_result=default_instance_contract_verification_result,
                real_executor_instance_creation_boundary_result=default_instance_creation_boundary_result,
                real_executor_instance_factory_contract_result=default_instance_factory_contract_result,
                real_executor_instance_factory_contract_verification_result=default_instance_factory_contract_verification_result,
                executor_invocation_guard_result=invocation_guard_result,
                evidence_records=evidence_records,
                metadata=copy.deepcopy(metadata or {}),
            )

        activation_intent = {
            "intent_id": "runtime-recovery-activation-intent-" + stable_supervisor_bridge_fingerprint(
                {
                    "bridge_id": bridge_id,
                    "current_tick": current_tick,
                    "supervisor_case_count": len(supervisor_cases),
                }
            )[:16],
            "bridge_id": bridge_id,
            "current_tick": int(current_tick),
            "supervisor_case_count": len(supervisor_cases),
            "observation_only": bool(observation_only),
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
        }
        observation_result = self._observe_recovery_activation_intent(
            activation_intent=activation_intent,
            admission=admission_result,
            reason="recovery activation intent created without recovery execution",
            supervisor_cases=supervisor_cases,
            metadata=metadata,
        )
        dry_run_result = self._dry_run_recovery_observation_result(
            activation_intent=activation_intent,
            admission=admission_result,
            observation_result=observation_result,
            reason="recovery activation intent dry-run completed without recovery execution",
            metadata=metadata,
        )
        execution_gate_result = self._evaluate_recovery_execution_gate(
            activation_intent=activation_intent,
            admission=admission_result,
            dry_run_result=dry_run_result,
            enabled=execution_gate_enabled,
            metadata=metadata,
        )
        observation_summary = observation_result.get("operator_summary") if isinstance(observation_result.get("operator_summary"), dict) else {}
        planning_activation_intent = (
            copy.deepcopy(observation_summary.get("activation_intent_lineage"))
            if isinstance(observation_summary.get("activation_intent_lineage"), dict)
            else copy.deepcopy(execution_gate_result.get("activation_intent_lineage"))
            if isinstance(execution_gate_result.get("activation_intent_lineage"), dict)
            else {}
        )
        observed_admission = observation_summary.get("admission") if isinstance(observation_summary.get("admission"), dict) else {}
        admission_status = self._status_from_mapping(observed_admission)
        observation_status = self._status_from_mapping(observation_result)
        dry_run_status = self._status_from_mapping(dry_run_result)
        gate_status = self._status_from_mapping(execution_gate_result)
        dry_run_passed = self._recovery_dry_run_passed(dry_run_result)
        gate_blocked = gate_status == "execution_gate_blocked"
        eligible_for_descriptive_plan = (
            admission_status == "allowed"
            and bool(observation_result)
            and bool(dry_run_result)
            and bool(execution_gate_result)
            and dry_run_passed
            and not gate_blocked
        )
        planning_reason = (
            "recovery planning result created without recovery execution"
            if eligible_for_descriptive_plan
            else "recovery planning recorded as non-executable because dry-run or gate blocked execution"
        )
        rollback_required = bool(
            dry_run_result.get("rollback_required")
            or execution_gate_result.get("rollback_required")
        )
        rollback_available = bool(
            dry_run_result.get("rollback_available")
            or execution_gate_result.get("rollback_available")
        )
        planner_result = build_recovery_plan(
            {
                "contract": RECOVERY_ELIGIBILITY_CONTRACT,
                "eligible": bool(eligible_for_descriptive_plan),
                "blocked": not bool(eligible_for_descriptive_plan),
                "status": "eligible" if eligible_for_descriptive_plan else "blocked",
                "reason": planning_reason,
                "execution_summary": {
                    "activation_intent_id": planning_activation_intent.get("intent_id"),
                    "admission_status": admission_status,
                    "observation_status": observation_status,
                    "dry_run_status": dry_run_status,
                    "gate_status": gate_status,
                    "source": "runtime_supervisor_bridge",
                },
                "failure_classification": "runtime_recovery_activation_planning",
                "recovery_authorized": bool(eligible_for_descriptive_plan),
                "descriptive_only": True,
            },
            recovery_token="runtime-recovery-plan-" + stable_supervisor_bridge_fingerprint(
                {
                    "intent_id": planning_activation_intent.get("intent_id"),
                    "admission_status": admission_status,
                    "observation_status": observation_status,
                    "dry_run_status": dry_run_status,
                    "gate_status": gate_status,
                }
            )[:24],
            metadata={
                "source": "runtime_supervisor_bridge",
                "planning_reads": ["observation_result", "dry_run_result", "execution_gate_result"],
                **copy.deepcopy(metadata or {}),
            },
        )
        risk_level = "high" if (not dry_run_passed or gate_blocked) else "medium" if gate_status == "execution_gate_observed" else "low"
        planner_boundary = planner_result.get("execution_boundary") if isinstance(planner_result.get("execution_boundary"), dict) else {}
        recovery_plan_executable = bool(
            eligible_for_descriptive_plan
            and (
                planner_result.get("executable_plan") is True
                or planner_boundary.get("execution_allowed") is True
            )
        )
        recovery_plan_result = {
            "plan_id": str(planner_result.get("recovery_token") or ""),
            "status": "recovery_plan_result_created",
            "reason": planning_reason,
            "activation_intent_lineage": planning_activation_intent,
            "admission_status": admission_status,
            "observation_status": observation_status,
            "dry_run_status": dry_run_status,
            "gate_status": gate_status,
            "proposed_actions": list(planner_result.get("plan_steps") or []),
            "risk_level": risk_level,
            "rollback_required": rollback_required,
            "rollback_available": rollback_available,
            "executable_plan": recovery_plan_executable,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "executor_invoked": False,
            "planner_result": copy.deepcopy(planner_result),
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        real_executor_adapter_contract_result = {
            "status": "real_executor_adapter_contract_result_created",
            "executor_candidates": [
                {
                    "module": "core.runtime.runtime_recovery_executor",
                    "callable_name": "execute_recovery",
                    "source_file": "core/runtime/runtime_recovery_executor.py",
                    "interface_kind": "real_recovery_executor",
                },
                {
                    "module": "core.runtime.aer_runtime_recovery_executor",
                    "callable_name": "build_recovery_executor_report",
                    "source_file": "core/runtime/aer_runtime_recovery_executor.py",
                    "interface_kind": "passive_executor_report",
                },
            ],
            "selected_executor_module": "core.runtime.runtime_recovery_executor",
            "selected_executor_function_name": "execute_recovery",
            "module": "core.runtime.runtime_recovery_executor",
            "callable_name": "execute_recovery",
            "accepts_input": "recovery_plan_result",
            "required_input": "recovery_plan_result",
            "rejects_inputs": [
                "observation_result",
                "dry_run_result",
                "execution_gate_result",
            ],
            "forbidden_inputs": [
                "observation_result",
                "dry_run_result",
                "execution_gate_result",
            ],
            "invocation_contract_version": "zero.runtime.recovery.real_executor_adapter_contract.v1",
            "execution_side_effects": [],
            "adapter_contract_verified": False,
            "executable_adapter": False,
            "execution_ready": False,
            "plan_id": recovery_plan_result.get("plan_id"),
            "plan_contract": "RecoveryPlan",
            "input_contract": "RecoveryPlan",
            "input_source": "recovery_plan_result",
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        contract_override = admission_result.get("real_executor_adapter_contract_override")
        if isinstance(contract_override, dict):
            real_executor_adapter_contract_result.update(copy.deepcopy(contract_override))
        rejected_inputs = set(
            str(item)
            for item in real_executor_adapter_contract_result.get("rejects_inputs", [])
            if isinstance(item, str)
        )
        forbidden_inputs = set(
            str(item)
            for item in real_executor_adapter_contract_result.get("forbidden_inputs", [])
            if isinstance(item, str)
        )
        required_forbidden_inputs = {
            "observation_result",
            "dry_run_result",
            "execution_gate_result",
        }
        verification_checks = {
            "module": real_executor_adapter_contract_result.get("module") == "core.runtime.runtime_recovery_executor",
            "callable_name": real_executor_adapter_contract_result.get("callable_name") == "execute_recovery",
            "accepts_input": real_executor_adapter_contract_result.get("accepts_input") == "recovery_plan_result",
            "rejects_inputs": required_forbidden_inputs.issubset(rejected_inputs),
            "forbidden_inputs": required_forbidden_inputs.issubset(forbidden_inputs),
            "execution_side_effects": real_executor_adapter_contract_result.get("execution_side_effects") == [],
        }
        adapter_contract_verified = all(verification_checks.values())
        real_executor_adapter_contract_verification_result = {
            "status": (
                "real_executor_adapter_contract_verified"
                if adapter_contract_verified
                else "real_executor_adapter_contract_verification_failed"
            ),
            "verification_contract_version": "zero.runtime.recovery.real_executor_adapter_contract_verification.v1",
            "checks": copy.deepcopy(verification_checks),
            "missing_or_invalid": [
                name for name, passed in verification_checks.items() if not passed
            ],
            "module": real_executor_adapter_contract_result.get("module"),
            "callable_name": real_executor_adapter_contract_result.get("callable_name"),
            "accepts_input": real_executor_adapter_contract_result.get("accepts_input"),
            "rejects_inputs": list(real_executor_adapter_contract_result.get("rejects_inputs") or []),
            "forbidden_inputs": list(real_executor_adapter_contract_result.get("forbidden_inputs") or []),
            "execution_side_effects": list(real_executor_adapter_contract_result.get("execution_side_effects") or []),
            "adapter_contract_verified": adapter_contract_verified,
            "executable_adapter": False,
            "execution_ready": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        real_executor_adapter_contract_result["adapter_contract_verified"] = adapter_contract_verified
        real_executor_adapter_contract_result["executable_adapter"] = False
        real_executor_adapter_contract_result["execution_ready"] = False
        real_executor_adapter_contract_result["real_executor_invoked"] = False
        real_executor_adapter_contract_result["executor_invoked"] = False
        real_executor_adapter_contract_result["executes_recovery"] = False
        real_executor_adapter_contract_result["runtime_state_mutated"] = False
        executor_module = "core.runtime.aer_runtime_recovery_executor"
        plan_executable = recovery_plan_result.get("executable_plan") is True
        gate_execution_allowed = execution_gate_result.get("recovery_execution_allowed") is True
        executor_lookup_allowed = False
        executor_available = False
        executor_binding_result = {
            "status": "executor_binding_result_created",
            "executor_available": bool(executor_available),
            "executor_name": "aer_runtime_recovery_executor" if executor_available else "",
            "module": executor_module if executor_available else "",
            "required_input": "recovery_plan_result",
            "plan_id": recovery_plan_result.get("plan_id"),
            "executable_plan": plan_executable,
            "execution_allowed": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        if not executor_enabled:
            wiring_status = "executor_wiring_disabled"
            wiring_reason = "recovery executor wiring disabled by default"
        elif not plan_executable:
            wiring_status = "executor_wiring_blocked_non_executable_plan"
            wiring_reason = "recovery executor wiring blocked because recovery_plan_result is non-executable"
        elif not gate_execution_allowed:
            wiring_status = "executor_wiring_blocked_gate_not_allowed"
            wiring_reason = "recovery executor wiring blocked because execution gate did not allow execution"
        elif not executor_available:
            wiring_status = "executor_wiring_blocked_executor_unavailable"
            wiring_reason = "recovery executor wiring blocked because executor module is unavailable"
        else:
            wiring_status = "executor_wiring_ready_not_invoked"
            wiring_reason = "recovery executor wiring ready but executor invocation remains disabled in this phase"
        executor_wiring_result = {
            "status": wiring_status,
            "reason": wiring_reason,
            "recovery_executor_enabled": bool(executor_enabled),
            "executor_lookup_allowed": executor_lookup_allowed,
            "executor_available": bool(executor_available),
            "executor_name": executor_binding_result.get("executor_name"),
            "module": executor_binding_result.get("module"),
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "plan_id": recovery_plan_result.get("plan_id"),
            "executable_plan": plan_executable,
            "gate_status": gate_status,
            "gate_execution_allowed": gate_execution_allowed,
            "execution_allowed": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        invocation_guard_result = self._build_executor_invocation_guard_result(
            activation_enabled=enabled,
            kill_switch_engaged=kill_switch_engaged,
            admission_allowed=admission_status == "allowed",
            observation_result=observation_result,
            dry_run_result=dry_run_result,
            execution_gate_result=execution_gate_result,
            recovery_plan_result=recovery_plan_result,
            executor_binding_result=executor_binding_result,
            recovery_executor_enabled=executor_enabled,
        )
        adapter_contract_valid = bool(
            real_executor_adapter_contract_verification_result.get("adapter_contract_verified") is True
            and real_executor_adapter_contract_result.get("real_executor_invoked") is False
            and real_executor_adapter_contract_result.get("executes_recovery") is False
            and real_executor_adapter_contract_result.get("runtime_state_mutated") is False
        )
        guard_ready = invocation_guard_result.get("invocation_allowed") is True
        import_boundary_ready = bool(executor_enabled and guard_ready and adapter_contract_valid)
        if not executor_enabled:
            import_boundary_status = "real_executor_import_boundary_disabled"
            import_boundary_reason = "real executor import boundary disabled by default"
            import_boundary_decision = "disabled"
            import_boundary_blocked_reason = "disabled"
        elif not guard_ready:
            import_boundary_status = "real_executor_import_boundary_blocked_guard_not_ready"
            import_boundary_reason = "real executor import boundary blocked because invocation guard is not ready"
            import_boundary_decision = "blocked"
            import_boundary_blocked_reason = "guard_blocked"
        elif not adapter_contract_valid:
            import_boundary_status = "real_executor_import_boundary_blocked_adapter_contract_invalid"
            import_boundary_reason = "real executor import boundary blocked because adapter contract is invalid"
            import_boundary_decision = "blocked"
            import_boundary_blocked_reason = "adapter_invalid"
        else:
            import_boundary_status = "real_executor_import_boundary_ready_not_imported"
            import_boundary_reason = "real executor import boundary verified and ready; import remains disabled until the explicit import phase"
            import_boundary_decision = "ready_not_imported"
            import_boundary_blocked_reason = "waiting_import_phase"
        import_check_available = False
        real_executor_import_boundary_result = {
            "status": import_boundary_status,
            "reason": import_boundary_reason,
            "recovery_real_executor_enabled": bool(executor_enabled),
            "guard_ready": guard_ready,
            "adapter_contract_valid": adapter_contract_valid,
            "adapter_contract_verified": real_executor_adapter_contract_result.get("adapter_contract_verified") is True,
            "selected_executor_module": real_executor_adapter_contract_result.get("selected_executor_module"),
            "selected_executor_function_name": real_executor_adapter_contract_result.get("selected_executor_function_name"),
            "module": real_executor_adapter_contract_result.get("module"),
            "callable_name": real_executor_adapter_contract_result.get("callable_name"),
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "import_boundary_ready": import_boundary_ready,
            "import_boundary_decision": import_boundary_decision,
            "blocked_reason": import_boundary_blocked_reason,
            "blocked": True,
            "import_check_allowed": False,
            "import_attempted": False,
            "import_lookup_available": import_check_available,
            "real_executor_imported": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        factory_boundary_ready = bool(import_boundary_ready)
        if not executor_enabled:
            factory_boundary_status = "real_executor_factory_boundary_disabled"
            factory_boundary_reason = "real executor factory boundary disabled because real executor import boundary is disabled"
            factory_boundary_decision = "disabled"
            factory_boundary_blocked_reason = "disabled"
        elif not factory_boundary_ready:
            factory_boundary_status = "real_executor_factory_boundary_blocked_import_boundary_not_ready"
            factory_boundary_reason = "real executor factory boundary blocked because import boundary is not ready"
            factory_boundary_decision = "blocked"
            factory_boundary_blocked_reason = "import_boundary_not_ready"
        else:
            factory_boundary_status = "real_executor_factory_boundary_ready_not_created"
            factory_boundary_reason = "real executor factory boundary ready; factory creation remains disabled until explicit factory phase"
            factory_boundary_decision = "ready_not_created"
            factory_boundary_blocked_reason = "waiting_factory_phase"
        real_executor_factory_boundary_result = {
            "status": factory_boundary_status,
            "reason": factory_boundary_reason,
            "factory_boundary_enabled": bool(executor_enabled),
            "factory_boundary_ready": factory_boundary_ready,
            "factory_boundary_decision": factory_boundary_decision,
            "blocked_reason": factory_boundary_blocked_reason,
            "blocked": True,
            "import_boundary_ready": import_boundary_ready,
            "import_boundary_status": import_boundary_status,
            "adapter_contract_verified": adapter_contract_valid,
            "factory_contract_verified": False,
            "factory_module": "core.runtime.runtime_recovery_executor",
            "factory_name": "execute_recovery",
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "plan_id": recovery_plan_result.get("plan_id"),
            "factory_creation_allowed": False,
            "factory_attempted": False,
            "factory_available": False,
            "factory_created": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        instance_contract_ready = False
        if not executor_enabled:
            instance_contract_status = "real_executor_instance_contract_disabled"
            instance_contract_reason = "real executor instance contract disabled because real executor factory boundary is disabled"
            instance_contract_decision = "disabled"
            instance_contract_blocked_reason = "disabled"
        elif not real_executor_factory_boundary_result.get("factory_boundary_ready"):
            instance_contract_status = "real_executor_instance_contract_blocked_factory_boundary_not_ready"
            instance_contract_reason = "real executor instance contract blocked because factory boundary is not ready"
            instance_contract_decision = "blocked"
            instance_contract_blocked_reason = "factory_boundary_not_ready"
        else:
            instance_contract_status = "real_executor_instance_contract_ready_not_instantiated"
            instance_contract_reason = "real executor instance contract ready; instance creation remains disabled until explicit instance phase"
            instance_contract_decision = "ready_not_instantiated"
            instance_contract_blocked_reason = "waiting_instance_phase"
            instance_contract_ready = True
        real_executor_instance_contract_result = {
            "status": instance_contract_status,
            "reason": instance_contract_reason,
            "instance_contract_enabled": bool(executor_enabled),
            "instance_contract_verified": False,
            "instance_contract_ready": instance_contract_ready,
            "instance_contract_decision": instance_contract_decision,
            "blocked_reason": instance_contract_blocked_reason,
            "blocked": True,
            "factory_boundary_ready": real_executor_factory_boundary_result.get("factory_boundary_ready") is True,
            "factory_boundary_status": real_executor_factory_boundary_result.get("status"),
            "factory_contract_verified": real_executor_factory_boundary_result.get("factory_contract_verified") is True,
            "instance_type": "RuntimeRecoveryExecutor",
            "required_method": "execute_recovery",
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "plan_id": recovery_plan_result.get("plan_id"),
            "instance_creation_allowed": False,
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        instance_verification_checks = {
            "instance_type": real_executor_instance_contract_result.get("instance_type") == "RuntimeRecoveryExecutor",
            "required_method": real_executor_instance_contract_result.get("required_method") == "execute_recovery",
            "required_input": real_executor_instance_contract_result.get("required_input") == "recovery_plan_result",
            "input_source": real_executor_instance_contract_result.get("input_source") == "recovery_plan_result",
            "execution_side_effects": real_executor_instance_contract_result.get("execution_side_effects", []) == [],
        }
        instance_contract_verified = all(instance_verification_checks.values())
        real_executor_instance_contract_verification_result = {
            "status": (
                "real_executor_instance_contract_verified"
                if instance_contract_verified
                else "real_executor_instance_contract_verification_failed"
            ),
            "reason": "real executor instance contract statically verified without importing, instantiating, or invoking executor",
            "verification_contract_version": "zero.runtime.recovery.real_executor_instance_contract_verification.v1",
            "checks": copy.deepcopy(instance_verification_checks),
            "missing_or_invalid": [
                name for name, passed in instance_verification_checks.items() if not passed
            ],
            "instance_contract_verified": instance_contract_verified,
            "instance_type": real_executor_instance_contract_result.get("instance_type"),
            "required_method": real_executor_instance_contract_result.get("required_method"),
            "required_input": real_executor_instance_contract_result.get("required_input"),
            "input_source": real_executor_instance_contract_result.get("input_source"),
            "execution_side_effects": copy.deepcopy(real_executor_instance_contract_result.get("execution_side_effects", [])),
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        instance_creation_boundary_ready = bool(
            executor_enabled
            and real_executor_instance_contract_verification_result.get("instance_contract_verified") is True
        )
        if not executor_enabled:
            instance_creation_boundary_status = "real_executor_instance_creation_boundary_disabled"
            instance_creation_boundary_reason = "real executor instance creation boundary disabled because recovery executor is disabled"
            instance_creation_boundary_decision = "disabled"
            instance_creation_boundary_blocked_reason = "disabled"
        elif real_executor_instance_contract_verification_result.get("instance_contract_verified") is not True:
            instance_creation_boundary_status = "real_executor_instance_creation_boundary_blocked_instance_contract_not_verified"
            instance_creation_boundary_reason = "real executor instance creation boundary blocked because instance contract is not verified"
            instance_creation_boundary_decision = "blocked"
            instance_creation_boundary_blocked_reason = "instance_contract_not_verified"
        else:
            instance_creation_boundary_status = "real_executor_instance_creation_boundary_ready_not_created"
            instance_creation_boundary_reason = "real executor instance creation boundary ready; instance creation remains disabled until explicit instance creation phase"
            instance_creation_boundary_decision = "ready_not_created"
            instance_creation_boundary_blocked_reason = "waiting_instance_creation_phase"
        real_executor_instance_creation_boundary_result = {
            "status": instance_creation_boundary_status,
            "reason": instance_creation_boundary_reason,
            "instance_creation_boundary_enabled": bool(executor_enabled),
            "instance_creation_boundary_ready": instance_creation_boundary_ready,
            "instance_creation_boundary_decision": instance_creation_boundary_decision,
            "blocked_reason": instance_creation_boundary_blocked_reason,
            "blocked": True,
            "instance_contract_verified": real_executor_instance_contract_verification_result.get("instance_contract_verified") is True,
            "instance_contract_verification_status": real_executor_instance_contract_verification_result.get("status"),
            "instance_type": real_executor_instance_contract_verification_result.get("instance_type"),
            "required_method": real_executor_instance_contract_verification_result.get("required_method"),
            "required_input": real_executor_instance_contract_verification_result.get("required_input"),
            "input_source": real_executor_instance_contract_verification_result.get("input_source"),
            "plan_id": recovery_plan_result.get("plan_id"),
            "instance_creation_allowed": False,
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        instance_factory_contract_ready = bool(
            executor_enabled
            and real_executor_instance_creation_boundary_result.get("instance_creation_boundary_ready") is True
        )
        if not executor_enabled:
            instance_factory_contract_status = "real_executor_instance_factory_contract_disabled"
            instance_factory_contract_reason = "real executor instance factory contract disabled because recovery executor is disabled"
            instance_factory_contract_decision = "disabled"
            instance_factory_contract_blocked_reason = "disabled"
        elif real_executor_instance_creation_boundary_result.get("instance_creation_boundary_ready") is not True:
            instance_factory_contract_status = "real_executor_instance_factory_contract_blocked_creation_boundary_not_ready"
            instance_factory_contract_reason = "real executor instance factory contract blocked because instance creation boundary is not ready"
            instance_factory_contract_decision = "blocked"
            instance_factory_contract_blocked_reason = "instance_creation_boundary_not_ready"
        else:
            instance_factory_contract_status = "real_executor_instance_factory_contract_recorded"
            instance_factory_contract_reason = "real executor instance factory contract recorded without creating executor factory or instance"
            instance_factory_contract_decision = "recorded"
            instance_factory_contract_blocked_reason = "waiting_factory_resolution_phase"
        real_executor_instance_factory_contract_result = {
            "status": instance_factory_contract_status,
            "reason": instance_factory_contract_reason,
            "factory_contract_enabled": bool(executor_enabled),
            "factory_contract_verified": instance_factory_contract_ready,
            "factory_contract_ready": instance_factory_contract_ready,
            "factory_contract_decision": instance_factory_contract_decision,
            "blocked_reason": instance_factory_contract_blocked_reason,
            "blocked": True,
            "instance_creation_boundary_ready": real_executor_instance_creation_boundary_result.get("instance_creation_boundary_ready") is True,
            "instance_creation_boundary_status": real_executor_instance_creation_boundary_result.get("status"),
            "factory_module": "core.runtime.runtime_recovery_executor",
            "factory_name": "RuntimeRecoveryExecutor",
            "factory_method": "__init__",
            "instance_type": "RuntimeRecoveryExecutor",
            "required_method": "execute_recovery",
            "accepts_input": "recovery_plan_result",
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result",
            "creation_contract_version": "zero.runtime.recovery.real_executor_instance_factory_contract.v1",
            "plan_id": recovery_plan_result.get("plan_id"),
            "factory_available": False,
            "factory_attempted": False,
            "factory_created": False,
            "instance_creation_allowed": False,
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        factory_contract_verification_checks = {
            "factory_module": real_executor_instance_factory_contract_result.get("factory_module") == "core.runtime.runtime_recovery_executor",
            "factory_name": real_executor_instance_factory_contract_result.get("factory_name") == "RuntimeRecoveryExecutor",
            "factory_method": real_executor_instance_factory_contract_result.get("factory_method") == "__init__",
            "instance_type": real_executor_instance_factory_contract_result.get("instance_type") == "RuntimeRecoveryExecutor",
            "required_method": real_executor_instance_factory_contract_result.get("required_method") == "execute_recovery",
            "accepts_input": real_executor_instance_factory_contract_result.get("accepts_input") == "recovery_plan_result",
            "creation_contract_version": real_executor_instance_factory_contract_result.get("creation_contract_version") == "zero.runtime.recovery.real_executor_instance_factory_contract.v1",
        }
        factory_contract_verified = all(factory_contract_verification_checks.values())
        real_executor_instance_factory_contract_verification_result = {
            "status": (
                "real_executor_instance_factory_contract_verified"
                if factory_contract_verified
                else "real_executor_instance_factory_contract_verification_failed"
            ),
            "reason": "real executor instance factory contract statically verified without creating executor factory or instance",
            "verification_contract_version": "zero.runtime.recovery.real_executor_instance_factory_contract_verification.v1",
            "checks": copy.deepcopy(factory_contract_verification_checks),
            "missing_or_invalid": [
                name for name, passed in factory_contract_verification_checks.items() if not passed
            ],
            "factory_contract_verified": factory_contract_verified,
            "factory_module": real_executor_instance_factory_contract_result.get("factory_module"),
            "factory_name": real_executor_instance_factory_contract_result.get("factory_name"),
            "factory_method": real_executor_instance_factory_contract_result.get("factory_method"),
            "instance_type": real_executor_instance_factory_contract_result.get("instance_type"),
            "required_method": real_executor_instance_factory_contract_result.get("required_method"),
            "accepts_input": real_executor_instance_factory_contract_result.get("accepts_input"),
            "required_input": real_executor_instance_factory_contract_result.get("required_input"),
            "input_source": real_executor_instance_factory_contract_result.get("input_source"),
            "creation_contract_version": real_executor_instance_factory_contract_result.get("creation_contract_version"),
            "factory_available": False,
            "factory_attempted": False,
            "factory_created": False,
            "instance_creation_allowed": False,
            "instance_attempted": False,
            "executor_instance_created": False,
            "real_executor_imported": False,
            "real_executor_instantiated": False,
            "real_executor_invoked": False,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        real_executor_instance_factory_contract_result["factory_contract_verified"] = (
            real_executor_instance_factory_contract_result.get("factory_contract_enabled") is True
            and factory_contract_verified
        )
        real_executor_instance_factory_contract_result["factory_available"] = False
        real_executor_instance_factory_contract_result["factory_attempted"] = False
        real_executor_instance_factory_contract_result["factory_created"] = False
        real_executor_instance_factory_contract_result["executor_instance_created"] = False
        real_executor_instance_factory_contract_result["real_executor_instantiated"] = False
        real_executor_instance_factory_contract_result["real_executor_invoked"] = False
        real_executor_instance_factory_contract_result["executor_invoked"] = False
        real_executor_instance_factory_contract_result["executes_recovery"] = False
        real_executor_instance_factory_contract_result["runtime_state_mutated"] = False


        executor_invocation_result = {}
        if real_executor_import_boundary_result.get("real_executor_imported") is True:
            executor_invocation_result = {
                "status": "executor_invocation_stub_created",
                "input_source": "recovery_plan_result",
                "plan_id": recovery_plan_result.get("plan_id"),
                "stub_invoked": True,
                "real_executor_invoked": False,
                "executor_invoked": False,
                "executes_recovery": False,
                "runtime_state_mutated": False,
                "scheduler_mutation_allowed": False,
                "taskrunner_mutation_allowed": False,
                "operator_mutation_allowed": False,
                "source": "runtime_supervisor_bridge",
                "metadata": copy.deepcopy(metadata or {}),
            }
        evidence_records = [
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage="observation_result_created",
                reason="recovery activation intent observed without recovery execution",
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage="dry_run_result_created",
                reason="recovery activation intent dry-run completed without recovery execution",
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(execution_gate_result.get("status") or "execution_gate_result_created"),
                reason=str(execution_gate_result.get("reason") or "recovery execution gate evaluated without recovery execution"),
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(recovery_plan_result.get("status") or "recovery_plan_result_created"),
                reason=str(recovery_plan_result.get("reason") or "recovery plan result created without recovery execution"),
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage="executor_binding_result_created",
                reason="recovery executor binding recorded without invoking executor",
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                executor_binding_result=executor_binding_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(real_executor_adapter_contract_result.get("status") or "real_executor_adapter_contract_result_created"),
                reason="real recovery executor adapter contract recorded without importing or invoking executor",
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                executor_binding_result=executor_binding_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(real_executor_adapter_contract_verification_result.get("status") or "real_executor_adapter_contract_verification_failed"),
                reason="real recovery executor adapter contract statically verified without importing or invoking executor",
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
                executor_binding_result=executor_binding_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(executor_wiring_result.get("status") or "executor_wiring_result_created"),
                reason=str(executor_wiring_result.get("reason") or "recovery executor wiring recorded without invoking executor"),
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
                executor_binding_result=executor_binding_result,
                executor_wiring_result=executor_wiring_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(invocation_guard_result.get("status") or "executor_invocation_blocked"),
                reason=str(invocation_guard_result.get("reason") or "executor invocation guard blocked"),
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
                executor_binding_result=executor_binding_result,
                executor_wiring_result=executor_wiring_result,
                executor_invocation_guard_result=invocation_guard_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(real_executor_instance_contract_verification_result.get("status") or "real_executor_instance_contract_verification_failed"),
                reason="real executor instance contract statically verified without importing, instantiating, or invoking executor",
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
                real_executor_import_boundary_result=real_executor_import_boundary_result,
                real_executor_factory_boundary_result=real_executor_factory_boundary_result,
                real_executor_instance_contract_result=real_executor_instance_contract_result,
                real_executor_instance_contract_verification_result=real_executor_instance_contract_verification_result,
                real_executor_instance_creation_boundary_result=real_executor_instance_creation_boundary_result,
                real_executor_instance_factory_contract_result=real_executor_instance_factory_contract_result,
                real_executor_instance_factory_contract_verification_result=real_executor_instance_factory_contract_verification_result,
                executor_binding_result=executor_binding_result,
                executor_wiring_result=executor_wiring_result,
                executor_invocation_guard_result=invocation_guard_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(real_executor_instance_creation_boundary_result.get("status") or "real_executor_instance_creation_boundary_blocked"),
                reason=str(real_executor_instance_creation_boundary_result.get("reason") or "real executor instance creation boundary recorded without creating executor instance"),
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
                real_executor_import_boundary_result=real_executor_import_boundary_result,
                real_executor_factory_boundary_result=real_executor_factory_boundary_result,
                real_executor_instance_contract_result=real_executor_instance_contract_result,
                real_executor_instance_contract_verification_result=real_executor_instance_contract_verification_result,
                real_executor_instance_creation_boundary_result=real_executor_instance_creation_boundary_result,
                real_executor_instance_factory_contract_result=real_executor_instance_factory_contract_result,
                real_executor_instance_factory_contract_verification_result=real_executor_instance_factory_contract_verification_result,
                executor_binding_result=executor_binding_result,
                executor_wiring_result=executor_wiring_result,
                executor_invocation_guard_result=invocation_guard_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(real_executor_instance_factory_contract_result.get("status") or "real_executor_instance_factory_contract_disabled"),
                reason=str(real_executor_instance_factory_contract_result.get("reason") or "real executor instance factory contract recorded without creating executor factory or instance"),
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
                real_executor_import_boundary_result=real_executor_import_boundary_result,
                real_executor_factory_boundary_result=real_executor_factory_boundary_result,
                real_executor_instance_contract_result=real_executor_instance_contract_result,
                real_executor_instance_contract_verification_result=real_executor_instance_contract_verification_result,
                real_executor_instance_creation_boundary_result=real_executor_instance_creation_boundary_result,
                real_executor_instance_factory_contract_result=real_executor_instance_factory_contract_result,
                real_executor_instance_factory_contract_verification_result=real_executor_instance_factory_contract_verification_result,
                executor_binding_result=executor_binding_result,
                executor_wiring_result=executor_wiring_result,
                executor_invocation_guard_result=invocation_guard_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(real_executor_instance_factory_contract_verification_result.get("status") or "real_executor_instance_factory_contract_verification_failed"),
                reason="real executor instance factory contract statically verified without creating executor factory or instance",
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
                real_executor_import_boundary_result=real_executor_import_boundary_result,
                real_executor_factory_boundary_result=real_executor_factory_boundary_result,
                real_executor_instance_contract_result=real_executor_instance_contract_result,
                real_executor_instance_contract_verification_result=real_executor_instance_contract_verification_result,
                real_executor_instance_creation_boundary_result=real_executor_instance_creation_boundary_result,
                real_executor_instance_factory_contract_result=real_executor_instance_factory_contract_result,
                real_executor_instance_factory_contract_verification_result=real_executor_instance_factory_contract_verification_result,
                executor_binding_result=executor_binding_result,
                executor_wiring_result=executor_wiring_result,
                executor_invocation_guard_result=invocation_guard_result,
                metadata=metadata,
            ),
            self._build_recovery_gate_evidence_record(
                bridge_id=bridge_id,
                current_tick=current_tick,
                stage=str(real_executor_import_boundary_result.get("status") or "real_executor_import_boundary_blocked"),
                reason=str(real_executor_import_boundary_result.get("reason") or "real executor import boundary recorded without importing executor"),
                activation_intent=activation_intent,
                admission=admission_result,
                observation_result=observation_result,
                dry_run_result=dry_run_result,
                execution_gate_result=execution_gate_result,
                recovery_plan_result=recovery_plan_result,
                real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
                real_executor_import_boundary_result=real_executor_import_boundary_result,
                real_executor_factory_boundary_result=real_executor_factory_boundary_result,
                real_executor_instance_contract_result=real_executor_instance_contract_result,
                real_executor_instance_contract_verification_result=real_executor_instance_contract_verification_result,
                real_executor_instance_creation_boundary_result=real_executor_instance_creation_boundary_result,
                real_executor_instance_factory_contract_result=real_executor_instance_factory_contract_result,
                real_executor_instance_factory_contract_verification_result=real_executor_instance_factory_contract_verification_result,
                executor_binding_result=executor_binding_result,
                executor_wiring_result=executor_wiring_result,
                executor_invocation_guard_result=invocation_guard_result,
                metadata=metadata,
            ),
        ]
        if executor_invocation_result:
            evidence_records.append(
                self._build_recovery_gate_evidence_record(
                    bridge_id=bridge_id,
                    current_tick=current_tick,
                    stage=str(executor_invocation_result.get("status") or "executor_invocation_stub_created"),
                    reason="recovery executor invocation stub recorded without invoking real executor",
                    activation_intent=activation_intent,
                    admission=admission_result,
                    observation_result=observation_result,
                    dry_run_result=dry_run_result,
                    execution_gate_result=execution_gate_result,
                    recovery_plan_result=recovery_plan_result,
                    real_executor_adapter_contract_result=real_executor_adapter_contract_result,
                    real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
                    real_executor_import_boundary_result=real_executor_import_boundary_result,
                    real_executor_factory_boundary_result=real_executor_factory_boundary_result,
                    real_executor_instance_contract_result=real_executor_instance_contract_result,
                    real_executor_instance_contract_verification_result=real_executor_instance_contract_verification_result,
                    real_executor_instance_creation_boundary_result=real_executor_instance_creation_boundary_result,
                    real_executor_instance_factory_contract_result=real_executor_instance_factory_contract_result,
                    real_executor_instance_factory_contract_verification_result=real_executor_instance_factory_contract_verification_result,
                    executor_binding_result=executor_binding_result,
                    executor_wiring_result=executor_wiring_result,
                    executor_invocation_guard_result=invocation_guard_result,
                    executor_invocation_result=executor_invocation_result,
                    metadata=metadata,
                )
            )
        return RuntimeRecoveryActivationResult(
            ok=True,
            status="execution_gate_result_created",
            reason="recovery execution gate evaluated without recovery execution",
            admission=admission_result,
            activation_intent=activation_intent,
            observation_result=observation_result,
            dry_run_result=dry_run_result,
            execution_gate_result=execution_gate_result,
            recovery_plan_result=recovery_plan_result,
            real_executor_adapter_contract_result=real_executor_adapter_contract_result,
            real_executor_adapter_contract_verification_result=real_executor_adapter_contract_verification_result,
            real_executor_import_boundary_result=real_executor_import_boundary_result,
            real_executor_factory_boundary_result=real_executor_factory_boundary_result,
            real_executor_instance_contract_result=real_executor_instance_contract_result,
            real_executor_instance_contract_verification_result=real_executor_instance_contract_verification_result,
            real_executor_instance_creation_boundary_result=real_executor_instance_creation_boundary_result,
            real_executor_instance_factory_contract_result=real_executor_instance_factory_contract_result,
            real_executor_instance_factory_contract_verification_result=real_executor_instance_factory_contract_verification_result,
            executor_binding_result=executor_binding_result,
            executor_wiring_result=executor_wiring_result,
            executor_invocation_guard_result=invocation_guard_result,
            executor_invocation_result=executor_invocation_result,
            evidence_records=evidence_records,
            metadata=copy.deepcopy(metadata or {}),
        )

    def _observe_recovery_activation_intent(
        self,
        *,
        activation_intent: dict[str, Any],
        admission: dict[str, Any],
        reason: str,
        supervisor_cases: list[dict[str, Any]],
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return observe_runtime_recovery(
            {
                "operator_summary": {
                    "ok": True,
                    "status": "observation_ready",
                    "readiness": "ready",
                    "summary": "Runtime Recovery activation intent observed without recovery execution.",
                    "blockers": [],
                    "reason": reason,
                    "admission": copy.deepcopy(admission),
                    "activation_intent_lineage": copy.deepcopy(activation_intent),
                    "supervisor_case_count": len(supervisor_cases),
                    "dry_run_only": True,
                    "executes_recovery": False,
                    "runtime_state_mutated": False,
                    "scheduler_mutation_allowed": False,
                    "taskrunner_mutation_allowed": False,
                    "operator_mutation_allowed": False,
                    "source": "runtime_supervisor_bridge",
                    "metadata": copy.deepcopy(metadata or {}),
                }
            }
        )

    def _build_executor_invocation_guard_result(
        self,
        *,
        activation_enabled: bool,
        kill_switch_engaged: bool,
        admission_allowed: bool,
        observation_result: dict[str, Any],
        dry_run_result: dict[str, Any],
        execution_gate_result: dict[str, Any],
        recovery_plan_result: dict[str, Any],
        executor_binding_result: dict[str, Any],
        recovery_executor_enabled: bool,
    ) -> dict[str, Any]:
        conditions = {
            "recovery_activation_enabled": bool(activation_enabled),
            "kill_switch_not_engaged": not bool(kill_switch_engaged),
            "admission_allowed": bool(admission_allowed),
            "observation_result_exists": bool(observation_result),
            "dry_run_result_passed": self._recovery_dry_run_passed(dry_run_result),
            "execution_gate_allowed": execution_gate_result.get("recovery_execution_allowed") is True,
            "recovery_plan_result_exists": bool(recovery_plan_result),
            "recovery_plan_executable": recovery_plan_result.get("executable_plan") is True,
            "executor_binding_requires_recovery_plan_result": (
                executor_binding_result.get("required_input") == "recovery_plan_result"
            ),
            "recovery_executor_enabled": bool(recovery_executor_enabled),
        }
        invocation_allowed = all(conditions.values())
        missing = [name for name, passed in conditions.items() if not passed]
        return {
            "status": "executor_invocation_ready" if invocation_allowed else "executor_invocation_blocked",
            "reason": (
                "all executor invocation guard conditions satisfied without invoking executor"
                if invocation_allowed
                else "executor invocation guard blocked: " + ",".join(missing)
            ),
            "conditions": conditions,
            "missing_conditions": missing,
            "required_input": "recovery_plan_result",
            "input_source": "recovery_plan_result" if recovery_plan_result else "",
            "plan_id": recovery_plan_result.get("plan_id") if isinstance(recovery_plan_result, dict) else None,
            "invocation_allowed": invocation_allowed,
            "executor_invoked": False,
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "source": "runtime_supervisor_bridge",
        }

    def _dry_run_recovery_observation_result(
        self,
        *,
        activation_intent: dict[str, Any],
        admission: dict[str, Any],
        observation_result: dict[str, Any],
        reason: str,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        report = dry_run_runtime_recovery(
            {
                "activation_intent_lineage": copy.deepcopy(activation_intent),
                "admission": copy.deepcopy(admission),
                "observation_result": copy.deepcopy(observation_result),
                "reason": reason,
                "dry_run_only": True,
                "executes_recovery": False,
                "runtime_state_mutated": False,
                "scheduler_mutation_allowed": False,
                "taskrunner_mutation_allowed": False,
                "operator_mutation_allowed": False,
                "source": "runtime_supervisor_bridge",
                "metadata": copy.deepcopy(metadata or {}),
            }
        )

        if hasattr(report, "payload"):
            payload = report.payload
        elif hasattr(report, "to_dict") and callable(report.to_dict):
            payload = report.to_dict()
        elif isinstance(report, dict):
            payload = report
        else:
            payload = {"result": report}

        if not isinstance(payload, dict):
            payload = {"result": payload}

        normalized = copy.deepcopy(payload)
        normalized.setdefault("read_only", True)
        normalized.setdefault("executes_recovery", False)
        normalized.setdefault("executes_repair", False)
        normalized.setdefault("executes_rollback", False)
        normalized["runtime_state_mutated"] = False
        normalized["scheduler_mutation_allowed"] = False
        normalized["taskrunner_mutation_allowed"] = False
        normalized["operator_mutation_allowed"] = False
        normalized["source"] = "runtime_supervisor_bridge"
        return normalized

    def _evaluate_recovery_execution_gate(
        self,
        *,
        activation_intent: dict[str, Any],
        admission: dict[str, Any],
        dry_run_result: dict[str, Any],
        enabled: bool,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        dry_run_passed = self._recovery_dry_run_passed(dry_run_result)
        base = {
            "gate_id": "runtime-recovery-execution-gate-" + stable_supervisor_bridge_fingerprint(
                {
                    "intent_id": activation_intent.get("intent_id"),
                    "dry_run_fingerprint": dry_run_result.get("fingerprint"),
                    "enabled": bool(enabled),
                }
            )[:16],
            "gate_name": "runtime_recovery_execution_gate",
            "execution_gate_enabled": bool(enabled),
            "activation_intent_lineage": copy.deepcopy(activation_intent),
            "admission": copy.deepcopy(admission),
            "dry_run_passed": dry_run_passed,
            "executes_recovery": False,
            "recovery_execution_allowed": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "executor_invoked": False,
            "source": "runtime_supervisor_bridge",
            "metadata": copy.deepcopy(metadata or {}),
        }
        if not dry_run_passed:
            return {
                **base,
                "ok": True,
                "status": "execution_gate_blocked",
                "reason": "dry-run result did not pass; recovery execution remains blocked",
            }
        if not enabled:
            return {
                **base,
                "ok": True,
                "status": "execution_gate_disabled",
                "reason": "recovery execution gate disabled by default",
            }
        return {
            **base,
            "ok": True,
            "status": "execution_gate_observed",
            "reason": "recovery execution gate observed without invoking recovery executor",
        }

    def _recovery_dry_run_passed(self, dry_run_result: dict[str, Any]) -> bool:
        if not isinstance(dry_run_result, dict):
            return False
        if dry_run_result.get("ok") is False:
            return False
        if dry_run_result.get("blocked") is True or dry_run_result.get("failed") is True:
            return False
        summary = dry_run_result.get("dry_run_summary")
        if isinstance(summary, dict):
            status = str(summary.get("status") or "").lower()
            if status in {"blocked", "failed", "unsafe"}:
                return False
            if summary.get("would_execute_anything") is True:
                return False
        return dry_run_result.get("executes_recovery") is not True

    def _build_recovery_gate_evidence_record(
        self,
        *,
        bridge_id: str,
        current_tick: int,
        stage: str,
        reason: str,
        activation_intent: dict[str, Any] | None = None,
        admission: dict[str, Any] | None = None,
        observation_result: dict[str, Any] | None = None,
        dry_run_result: dict[str, Any] | None = None,
        execution_gate_result: dict[str, Any] | None = None,
        recovery_plan_result: dict[str, Any] | None = None,
        real_executor_adapter_contract_result: dict[str, Any] | None = None,
        real_executor_adapter_contract_verification_result: dict[str, Any] | None = None,
        real_executor_import_boundary_result: dict[str, Any] | None = None,
        real_executor_factory_boundary_result: dict[str, Any] | None = None,
        real_executor_instance_contract_result: dict[str, Any] | None = None,
        real_executor_instance_contract_verification_result: dict[str, Any] | None = None,
        real_executor_instance_creation_boundary_result: dict[str, Any] | None = None,
        real_executor_instance_factory_contract_result: dict[str, Any] | None = None,
        real_executor_instance_factory_contract_verification_result: dict[str, Any] | None = None,
        executor_binding_result: dict[str, Any] | None = None,
        executor_wiring_result: dict[str, Any] | None = None,
        executor_invocation_guard_result: dict[str, Any] | None = None,
        executor_invocation_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        activation_intent = copy.deepcopy(activation_intent or {})
        admission = copy.deepcopy(admission or {})
        observation_result = copy.deepcopy(observation_result or {})
        dry_run_result = copy.deepcopy(dry_run_result or {})
        execution_gate_result = copy.deepcopy(execution_gate_result or {})
        recovery_plan_result = copy.deepcopy(recovery_plan_result or {})
        real_executor_adapter_contract_result = copy.deepcopy(real_executor_adapter_contract_result or {})
        real_executor_adapter_contract_verification_result = copy.deepcopy(real_executor_adapter_contract_verification_result or {})
        real_executor_import_boundary_result = copy.deepcopy(real_executor_import_boundary_result or {})
        real_executor_factory_boundary_result = copy.deepcopy(real_executor_factory_boundary_result or {})
        real_executor_instance_contract_result = copy.deepcopy(real_executor_instance_contract_result or {})
        real_executor_instance_contract_verification_result = copy.deepcopy(real_executor_instance_contract_verification_result or {})
        real_executor_instance_creation_boundary_result = copy.deepcopy(real_executor_instance_creation_boundary_result or {})
        real_executor_instance_factory_contract_result = copy.deepcopy(real_executor_instance_factory_contract_result or {})
        real_executor_instance_factory_contract_verification_result = copy.deepcopy(real_executor_instance_factory_contract_verification_result or {})
        executor_binding_result = copy.deepcopy(executor_binding_result or {})
        executor_wiring_result = copy.deepcopy(executor_wiring_result or {})
        executor_invocation_guard_result = copy.deepcopy(executor_invocation_guard_result or {})
        executor_invocation_result = copy.deepcopy(executor_invocation_result or {})
        admission_status = self._status_from_mapping(admission)
        observation_status = self._status_from_mapping(observation_result)
        dry_run_status = self._status_from_mapping(dry_run_result)
        gate_status = self._status_from_mapping(execution_gate_result)
        planning_status = self._status_from_mapping(recovery_plan_result)
        real_executor_adapter_contract_status = self._status_from_mapping(real_executor_adapter_contract_result)
        real_executor_adapter_contract_verification_status = self._status_from_mapping(real_executor_adapter_contract_verification_result)
        real_executor_import_boundary_status = self._status_from_mapping(real_executor_import_boundary_result)
        real_executor_factory_boundary_status = self._status_from_mapping(real_executor_factory_boundary_result)
        real_executor_instance_contract_status = self._status_from_mapping(real_executor_instance_contract_result)
        real_executor_instance_contract_verification_status = self._status_from_mapping(real_executor_instance_contract_verification_result)
        real_executor_instance_creation_boundary_status = self._status_from_mapping(real_executor_instance_creation_boundary_result)
        real_executor_instance_factory_contract_status = self._status_from_mapping(real_executor_instance_factory_contract_result)
        real_executor_instance_factory_contract_verification_status = self._status_from_mapping(real_executor_instance_factory_contract_verification_result)
        executor_binding_status = self._status_from_mapping(executor_binding_result)
        executor_wiring_status = self._status_from_mapping(executor_wiring_result)
        executor_invocation_guard_status = self._status_from_mapping(executor_invocation_guard_result)
        executor_invocation_status = self._status_from_mapping(executor_invocation_result)
        audit_lineage = {
            "bridge_id": bridge_id,
            "current_tick": int(current_tick),
            "stage": str(stage or ""),
            "activation_intent_lineage": activation_intent,
            "admission_status": admission_status,
            "observation_status": observation_status,
            "dry_run_status": dry_run_status,
            "gate_status": gate_status,
            "planning_status": planning_status,
            "real_executor_adapter_contract_status": real_executor_adapter_contract_status,
            "real_executor_adapter_contract_verification_status": real_executor_adapter_contract_verification_status,
            "real_executor_import_boundary_status": real_executor_import_boundary_status,
            "real_executor_factory_boundary_status": real_executor_factory_boundary_status,
            "real_executor_instance_contract_status": real_executor_instance_contract_status,
            "real_executor_instance_contract_verification_status": real_executor_instance_contract_verification_status,
            "real_executor_instance_creation_boundary_status": real_executor_instance_creation_boundary_status,
            "real_executor_instance_factory_contract_status": real_executor_instance_factory_contract_status,
            "real_executor_instance_factory_contract_verification_status": real_executor_instance_factory_contract_verification_status,
            "executor_binding_status": executor_binding_status,
            "executor_wiring_status": executor_wiring_status,
            "executor_invocation_guard_status": executor_invocation_guard_status,
            "executor_invocation_status": executor_invocation_status,
            "admission": admission,
            "observation": {
                "schema": observation_result.get("schema"),
                "mode": observation_result.get("mode"),
                "status": observation_status,
                "readiness": observation_result.get("readiness"),
            },
            "dry_run": {
                "schema": dry_run_result.get("schema"),
                "mode": dry_run_result.get("mode"),
                "status": dry_run_status,
                "ok": dry_run_result.get("ok"),
            },
            "gate": {
                "status": gate_status,
                "execution_gate_enabled": execution_gate_result.get("execution_gate_enabled"),
                "dry_run_passed": execution_gate_result.get("dry_run_passed"),
                "executor_invoked": execution_gate_result.get("executor_invoked") is True,
            },
            "planning": {
                "plan_id": recovery_plan_result.get("plan_id"),
                "status": planning_status,
                "risk_level": recovery_plan_result.get("risk_level"),
                "proposed_actions": copy.deepcopy(recovery_plan_result.get("proposed_actions") or []),
                "executable_plan": recovery_plan_result.get("executable_plan") is True,
                "executor_invoked": recovery_plan_result.get("executor_invoked") is True,
            },
            "real_executor_adapter_contract": {
                "status": real_executor_adapter_contract_status,
                "executor_candidates": copy.deepcopy(real_executor_adapter_contract_result.get("executor_candidates") or []),
                "selected_executor_module": real_executor_adapter_contract_result.get("selected_executor_module"),
                "selected_executor_function_name": real_executor_adapter_contract_result.get("selected_executor_function_name"),
                "module": real_executor_adapter_contract_result.get("module"),
                "callable_name": real_executor_adapter_contract_result.get("callable_name"),
                "accepts_input": real_executor_adapter_contract_result.get("accepts_input"),
                "required_input": real_executor_adapter_contract_result.get("required_input"),
                "rejects_inputs": copy.deepcopy(real_executor_adapter_contract_result.get("rejects_inputs") or []),
                "forbidden_inputs": copy.deepcopy(real_executor_adapter_contract_result.get("forbidden_inputs") or []),
                "invocation_contract_version": real_executor_adapter_contract_result.get("invocation_contract_version"),
                "execution_side_effects": copy.deepcopy(real_executor_adapter_contract_result.get("execution_side_effects") or []),
                "adapter_contract_verified": real_executor_adapter_contract_result.get("adapter_contract_verified") is True,
                "executable_adapter": real_executor_adapter_contract_result.get("executable_adapter") is True,
                "execution_ready": real_executor_adapter_contract_result.get("execution_ready") is True,
                "input_contract": real_executor_adapter_contract_result.get("input_contract"),
                "input_source": real_executor_adapter_contract_result.get("input_source"),
                "real_executor_invoked": real_executor_adapter_contract_result.get("real_executor_invoked") is True,
                "executor_invoked": real_executor_adapter_contract_result.get("executor_invoked") is True,
                "executes_recovery": real_executor_adapter_contract_result.get("executes_recovery") is True,
                "runtime_state_mutated": real_executor_adapter_contract_result.get("runtime_state_mutated") is True,
            },
            "real_executor_adapter_contract_verification": {
                "status": real_executor_adapter_contract_verification_status,
                "verification_contract_version": real_executor_adapter_contract_verification_result.get("verification_contract_version"),
                "checks": copy.deepcopy(real_executor_adapter_contract_verification_result.get("checks") or {}),
                "missing_or_invalid": copy.deepcopy(real_executor_adapter_contract_verification_result.get("missing_or_invalid") or []),
                "module": real_executor_adapter_contract_verification_result.get("module"),
                "callable_name": real_executor_adapter_contract_verification_result.get("callable_name"),
                "accepts_input": real_executor_adapter_contract_verification_result.get("accepts_input"),
                "rejects_inputs": copy.deepcopy(real_executor_adapter_contract_verification_result.get("rejects_inputs") or []),
                "forbidden_inputs": copy.deepcopy(real_executor_adapter_contract_verification_result.get("forbidden_inputs") or []),
                "execution_side_effects": copy.deepcopy(real_executor_adapter_contract_verification_result.get("execution_side_effects") or []),
                "adapter_contract_verified": real_executor_adapter_contract_verification_result.get("adapter_contract_verified") is True,
                "executable_adapter": real_executor_adapter_contract_verification_result.get("executable_adapter") is True,
                "execution_ready": real_executor_adapter_contract_verification_result.get("execution_ready") is True,
                "real_executor_invoked": real_executor_adapter_contract_verification_result.get("real_executor_invoked") is True,
                "executes_recovery": real_executor_adapter_contract_verification_result.get("executes_recovery") is True,
                "runtime_state_mutated": real_executor_adapter_contract_verification_result.get("runtime_state_mutated") is True,
            },
            "real_executor_import_boundary": {
                "status": real_executor_import_boundary_status,
                "reason": real_executor_import_boundary_result.get("reason"),
                "recovery_real_executor_enabled": real_executor_import_boundary_result.get("recovery_real_executor_enabled") is True,
                "guard_ready": real_executor_import_boundary_result.get("guard_ready") is True,
                "adapter_contract_valid": real_executor_import_boundary_result.get("adapter_contract_valid") is True,
                "adapter_contract_verified": real_executor_import_boundary_result.get("adapter_contract_verified") is True,
                "selected_executor_module": real_executor_import_boundary_result.get("selected_executor_module"),
                "selected_executor_function_name": real_executor_import_boundary_result.get("selected_executor_function_name"),
                "module": real_executor_import_boundary_result.get("module"),
                "callable_name": real_executor_import_boundary_result.get("callable_name"),
                "required_input": real_executor_import_boundary_result.get("required_input"),
                "input_source": real_executor_import_boundary_result.get("input_source"),
                "import_boundary_ready": real_executor_import_boundary_result.get("import_boundary_ready") is True,
                "import_boundary_decision": real_executor_import_boundary_result.get("import_boundary_decision"),
                "blocked_reason": real_executor_import_boundary_result.get("blocked_reason"),
                "blocked": real_executor_import_boundary_result.get("blocked") is True,
                "import_check_allowed": real_executor_import_boundary_result.get("import_check_allowed") is True,
                "import_attempted": real_executor_import_boundary_result.get("import_attempted") is True,
                "import_lookup_available": real_executor_import_boundary_result.get("import_lookup_available") is True,
                "real_executor_imported": real_executor_import_boundary_result.get("real_executor_imported") is True,
                "real_executor_invoked": real_executor_import_boundary_result.get("real_executor_invoked") is True,
                "executes_recovery": real_executor_import_boundary_result.get("executes_recovery") is True,
                "runtime_state_mutated": real_executor_import_boundary_result.get("runtime_state_mutated") is True,
            },
            "real_executor_factory_boundary": {
                "status": real_executor_factory_boundary_status,
                "reason": real_executor_factory_boundary_result.get("reason"),
                "factory_boundary_enabled": real_executor_factory_boundary_result.get("factory_boundary_enabled") is True,
                "factory_boundary_ready": real_executor_factory_boundary_result.get("factory_boundary_ready") is True,
                "factory_boundary_decision": real_executor_factory_boundary_result.get("factory_boundary_decision"),
                "blocked_reason": real_executor_factory_boundary_result.get("blocked_reason"),
                "blocked": real_executor_factory_boundary_result.get("blocked") is True,
                "import_boundary_ready": real_executor_factory_boundary_result.get("import_boundary_ready") is True,
                "import_boundary_status": real_executor_factory_boundary_result.get("import_boundary_status"),
                "adapter_contract_verified": real_executor_factory_boundary_result.get("adapter_contract_verified") is True,
                "factory_contract_verified": real_executor_factory_boundary_result.get("factory_contract_verified") is True,
                "factory_module": real_executor_factory_boundary_result.get("factory_module"),
                "factory_name": real_executor_factory_boundary_result.get("factory_name"),
                "required_input": real_executor_factory_boundary_result.get("required_input"),
                "input_source": real_executor_factory_boundary_result.get("input_source"),
                "plan_id": real_executor_factory_boundary_result.get("plan_id"),
                "factory_creation_allowed": real_executor_factory_boundary_result.get("factory_creation_allowed") is True,
                "factory_attempted": real_executor_factory_boundary_result.get("factory_attempted") is True,
                "factory_available": real_executor_factory_boundary_result.get("factory_available") is True,
                "factory_created": real_executor_factory_boundary_result.get("factory_created") is True,
                "executor_instance_created": real_executor_factory_boundary_result.get("executor_instance_created") is True,
                "real_executor_imported": real_executor_factory_boundary_result.get("real_executor_imported") is True,
                "real_executor_instantiated": real_executor_factory_boundary_result.get("real_executor_instantiated") is True,
                "real_executor_invoked": real_executor_factory_boundary_result.get("real_executor_invoked") is True,
                "executes_recovery": real_executor_factory_boundary_result.get("executes_recovery") is True,
                "runtime_state_mutated": real_executor_factory_boundary_result.get("runtime_state_mutated") is True,
            },
            "real_executor_instance_contract": {
                "status": real_executor_instance_contract_status,
                "reason": real_executor_instance_contract_result.get("reason"),
                "instance_contract_enabled": real_executor_instance_contract_result.get("instance_contract_enabled") is True,
                "instance_contract_verified": real_executor_instance_contract_result.get("instance_contract_verified") is True,
                "instance_contract_ready": real_executor_instance_contract_result.get("instance_contract_ready") is True,
                "instance_contract_decision": real_executor_instance_contract_result.get("instance_contract_decision"),
                "blocked_reason": real_executor_instance_contract_result.get("blocked_reason"),
                "blocked": real_executor_instance_contract_result.get("blocked") is True,
                "factory_boundary_ready": real_executor_instance_contract_result.get("factory_boundary_ready") is True,
                "factory_boundary_status": real_executor_instance_contract_result.get("factory_boundary_status"),
                "factory_contract_verified": real_executor_instance_contract_result.get("factory_contract_verified") is True,
                "instance_type": real_executor_instance_contract_result.get("instance_type"),
                "required_method": real_executor_instance_contract_result.get("required_method"),
                "required_input": real_executor_instance_contract_result.get("required_input"),
                "input_source": real_executor_instance_contract_result.get("input_source"),
                "plan_id": real_executor_instance_contract_result.get("plan_id"),
                "instance_creation_allowed": real_executor_instance_contract_result.get("instance_creation_allowed") is True,
                "instance_attempted": real_executor_instance_contract_result.get("instance_attempted") is True,
                "executor_instance_created": real_executor_instance_contract_result.get("executor_instance_created") is True,
                "real_executor_imported": real_executor_instance_contract_result.get("real_executor_imported") is True,
                "real_executor_instantiated": real_executor_instance_contract_result.get("real_executor_instantiated") is True,
                "real_executor_invoked": real_executor_instance_contract_result.get("real_executor_invoked") is True,
                "executor_invoked": real_executor_instance_contract_result.get("executor_invoked") is True,
                "executes_recovery": real_executor_instance_contract_result.get("executes_recovery") is True,
                "runtime_state_mutated": real_executor_instance_contract_result.get("runtime_state_mutated") is True,
            },
            "real_executor_instance_contract_verification": {
                "status": real_executor_instance_contract_verification_status,
                "reason": real_executor_instance_contract_verification_result.get("reason"),
                "verification_contract_version": real_executor_instance_contract_verification_result.get("verification_contract_version"),
                "checks": copy.deepcopy(real_executor_instance_contract_verification_result.get("checks") or {}),
                "missing_or_invalid": copy.deepcopy(real_executor_instance_contract_verification_result.get("missing_or_invalid") or []),
                "instance_contract_verified": real_executor_instance_contract_verification_result.get("instance_contract_verified") is True,
                "instance_type": real_executor_instance_contract_verification_result.get("instance_type"),
                "required_method": real_executor_instance_contract_verification_result.get("required_method"),
                "required_input": real_executor_instance_contract_verification_result.get("required_input"),
                "input_source": real_executor_instance_contract_verification_result.get("input_source"),
                "execution_side_effects": copy.deepcopy(real_executor_instance_contract_verification_result.get("execution_side_effects") or []),
                "instance_attempted": real_executor_instance_contract_verification_result.get("instance_attempted") is True,
                "executor_instance_created": real_executor_instance_contract_verification_result.get("executor_instance_created") is True,
                "real_executor_instantiated": real_executor_instance_contract_verification_result.get("real_executor_instantiated") is True,
                "real_executor_invoked": real_executor_instance_contract_verification_result.get("real_executor_invoked") is True,
                "executor_invoked": real_executor_instance_contract_verification_result.get("executor_invoked") is True,
                "executes_recovery": real_executor_instance_contract_verification_result.get("executes_recovery") is True,
                "runtime_state_mutated": real_executor_instance_contract_verification_result.get("runtime_state_mutated") is True,
            },
            "real_executor_instance_creation_boundary": {
                "status": real_executor_instance_creation_boundary_status,
                "reason": real_executor_instance_creation_boundary_result.get("reason"),
                "instance_creation_boundary_enabled": real_executor_instance_creation_boundary_result.get("instance_creation_boundary_enabled") is True,
                "instance_creation_boundary_ready": real_executor_instance_creation_boundary_result.get("instance_creation_boundary_ready") is True,
                "instance_creation_boundary_decision": real_executor_instance_creation_boundary_result.get("instance_creation_boundary_decision"),
                "blocked_reason": real_executor_instance_creation_boundary_result.get("blocked_reason"),
                "blocked": real_executor_instance_creation_boundary_result.get("blocked") is True,
                "instance_contract_verified": real_executor_instance_creation_boundary_result.get("instance_contract_verified") is True,
                "instance_contract_verification_status": real_executor_instance_creation_boundary_result.get("instance_contract_verification_status"),
                "instance_type": real_executor_instance_creation_boundary_result.get("instance_type"),
                "required_method": real_executor_instance_creation_boundary_result.get("required_method"),
                "required_input": real_executor_instance_creation_boundary_result.get("required_input"),
                "input_source": real_executor_instance_creation_boundary_result.get("input_source"),
                "plan_id": real_executor_instance_creation_boundary_result.get("plan_id"),
                "instance_creation_allowed": real_executor_instance_creation_boundary_result.get("instance_creation_allowed") is True,
                "instance_attempted": real_executor_instance_creation_boundary_result.get("instance_attempted") is True,
                "executor_instance_created": real_executor_instance_creation_boundary_result.get("executor_instance_created") is True,
                "real_executor_imported": real_executor_instance_creation_boundary_result.get("real_executor_imported") is True,
                "real_executor_instantiated": real_executor_instance_creation_boundary_result.get("real_executor_instantiated") is True,
                "real_executor_invoked": real_executor_instance_creation_boundary_result.get("real_executor_invoked") is True,
                "executor_invoked": real_executor_instance_creation_boundary_result.get("executor_invoked") is True,
                "executes_recovery": real_executor_instance_creation_boundary_result.get("executes_recovery") is True,
                "runtime_state_mutated": real_executor_instance_creation_boundary_result.get("runtime_state_mutated") is True,
            },
            "real_executor_instance_factory_contract": {
                "status": real_executor_instance_factory_contract_status,
                "reason": real_executor_instance_factory_contract_result.get("reason"),
                "factory_contract_enabled": real_executor_instance_factory_contract_result.get("factory_contract_enabled") is True,
                "factory_contract_verified": real_executor_instance_factory_contract_result.get("factory_contract_verified") is True,
                "factory_contract_ready": real_executor_instance_factory_contract_result.get("factory_contract_ready") is True,
                "factory_contract_decision": real_executor_instance_factory_contract_result.get("factory_contract_decision"),
                "blocked_reason": real_executor_instance_factory_contract_result.get("blocked_reason"),
                "blocked": real_executor_instance_factory_contract_result.get("blocked") is True,
                "instance_creation_boundary_ready": real_executor_instance_factory_contract_result.get("instance_creation_boundary_ready") is True,
                "instance_creation_boundary_status": real_executor_instance_factory_contract_result.get("instance_creation_boundary_status"),
                "factory_module": real_executor_instance_factory_contract_result.get("factory_module"),
                "factory_name": real_executor_instance_factory_contract_result.get("factory_name"),
                "factory_method": real_executor_instance_factory_contract_result.get("factory_method"),
                "instance_type": real_executor_instance_factory_contract_result.get("instance_type"),
                "required_method": real_executor_instance_factory_contract_result.get("required_method"),
                "accepts_input": real_executor_instance_factory_contract_result.get("accepts_input"),
                "required_input": real_executor_instance_factory_contract_result.get("required_input"),
                "input_source": real_executor_instance_factory_contract_result.get("input_source"),
                "creation_contract_version": real_executor_instance_factory_contract_result.get("creation_contract_version"),
                "plan_id": real_executor_instance_factory_contract_result.get("plan_id"),
                "factory_available": real_executor_instance_factory_contract_result.get("factory_available") is True,
                "factory_attempted": real_executor_instance_factory_contract_result.get("factory_attempted") is True,
                "factory_created": real_executor_instance_factory_contract_result.get("factory_created") is True,
                "instance_creation_allowed": real_executor_instance_factory_contract_result.get("instance_creation_allowed") is True,
                "instance_attempted": real_executor_instance_factory_contract_result.get("instance_attempted") is True,
                "executor_instance_created": real_executor_instance_factory_contract_result.get("executor_instance_created") is True,
                "real_executor_imported": real_executor_instance_factory_contract_result.get("real_executor_imported") is True,
                "real_executor_instantiated": real_executor_instance_factory_contract_result.get("real_executor_instantiated") is True,
                "real_executor_invoked": real_executor_instance_factory_contract_result.get("real_executor_invoked") is True,
                "executor_invoked": real_executor_instance_factory_contract_result.get("executor_invoked") is True,
                "executes_recovery": real_executor_instance_factory_contract_result.get("executes_recovery") is True,
                "runtime_state_mutated": real_executor_instance_factory_contract_result.get("runtime_state_mutated") is True,
            },
            "real_executor_instance_factory_contract_verification": {
                "status": real_executor_instance_factory_contract_verification_status,
                "reason": real_executor_instance_factory_contract_verification_result.get("reason"),
                "verification_contract_version": real_executor_instance_factory_contract_verification_result.get("verification_contract_version"),
                "checks": copy.deepcopy(real_executor_instance_factory_contract_verification_result.get("checks") or {}),
                "missing_or_invalid": copy.deepcopy(real_executor_instance_factory_contract_verification_result.get("missing_or_invalid") or []),
                "factory_contract_verified": real_executor_instance_factory_contract_verification_result.get("factory_contract_verified") is True,
                "factory_module": real_executor_instance_factory_contract_verification_result.get("factory_module"),
                "factory_name": real_executor_instance_factory_contract_verification_result.get("factory_name"),
                "factory_method": real_executor_instance_factory_contract_verification_result.get("factory_method"),
                "instance_type": real_executor_instance_factory_contract_verification_result.get("instance_type"),
                "required_method": real_executor_instance_factory_contract_verification_result.get("required_method"),
                "accepts_input": real_executor_instance_factory_contract_verification_result.get("accepts_input"),
                "required_input": real_executor_instance_factory_contract_verification_result.get("required_input"),
                "input_source": real_executor_instance_factory_contract_verification_result.get("input_source"),
                "creation_contract_version": real_executor_instance_factory_contract_verification_result.get("creation_contract_version"),
                "factory_attempted": real_executor_instance_factory_contract_verification_result.get("factory_attempted") is True,
                "factory_created": real_executor_instance_factory_contract_verification_result.get("factory_created") is True,
                "executor_instance_created": real_executor_instance_factory_contract_verification_result.get("executor_instance_created") is True,
                "real_executor_instantiated": real_executor_instance_factory_contract_verification_result.get("real_executor_instantiated") is True,
                "real_executor_invoked": real_executor_instance_factory_contract_verification_result.get("real_executor_invoked") is True,
                "executor_invoked": real_executor_instance_factory_contract_verification_result.get("executor_invoked") is True,
                "executes_recovery": real_executor_instance_factory_contract_verification_result.get("executes_recovery") is True,
                "runtime_state_mutated": real_executor_instance_factory_contract_verification_result.get("runtime_state_mutated") is True,
            },
            "executor_binding": {
                "executor_available": executor_binding_result.get("executor_available") is True,
                "executor_name": executor_binding_result.get("executor_name"),
                "module": executor_binding_result.get("module"),
                "required_input": executor_binding_result.get("required_input"),
                "plan_id": executor_binding_result.get("plan_id"),
                "executable_plan": executor_binding_result.get("executable_plan") is True,
                "execution_allowed": executor_binding_result.get("execution_allowed") is True,
                "executor_invoked": executor_binding_result.get("executor_invoked") is True,
                "executes_recovery": executor_binding_result.get("executes_recovery") is True,
                "runtime_state_mutated": executor_binding_result.get("runtime_state_mutated") is True,
            },
            "executor_wiring": {
                "status": executor_wiring_status,
                "recovery_executor_enabled": executor_wiring_result.get("recovery_executor_enabled") is True,
                "executor_lookup_allowed": executor_wiring_result.get("executor_lookup_allowed") is True,
                "required_input": executor_wiring_result.get("required_input"),
                "input_source": executor_wiring_result.get("input_source"),
                "plan_id": executor_wiring_result.get("plan_id"),
                "executable_plan": executor_wiring_result.get("executable_plan") is True,
                "gate_execution_allowed": executor_wiring_result.get("gate_execution_allowed") is True,
                "execution_allowed": executor_wiring_result.get("execution_allowed") is True,
                "executor_invoked": executor_wiring_result.get("executor_invoked") is True,
                "executes_recovery": executor_wiring_result.get("executes_recovery") is True,
                "runtime_state_mutated": executor_wiring_result.get("runtime_state_mutated") is True,
            },
            "executor_invocation_guard": {
                "status": executor_invocation_guard_status,
                "required_input": executor_invocation_guard_result.get("required_input"),
                "input_source": executor_invocation_guard_result.get("input_source"),
                "plan_id": executor_invocation_guard_result.get("plan_id"),
                "conditions": copy.deepcopy(executor_invocation_guard_result.get("conditions") or {}),
                "missing_conditions": copy.deepcopy(executor_invocation_guard_result.get("missing_conditions") or []),
                "invocation_allowed": executor_invocation_guard_result.get("invocation_allowed") is True,
                "executor_invoked": executor_invocation_guard_result.get("executor_invoked") is True,
                "executes_recovery": executor_invocation_guard_result.get("executes_recovery") is True,
                "runtime_state_mutated": executor_invocation_guard_result.get("runtime_state_mutated") is True,
            },
            "executor_invocation": {
                "status": executor_invocation_status,
                "input_source": executor_invocation_result.get("input_source"),
                "plan_id": executor_invocation_result.get("plan_id"),
                "stub_invoked": executor_invocation_result.get("stub_invoked") is True,
                "real_executor_invoked": executor_invocation_result.get("real_executor_invoked") is True,
                "executor_invoked": executor_invocation_result.get("executor_invoked") is True,
                "executes_recovery": executor_invocation_result.get("executes_recovery") is True,
                "runtime_state_mutated": executor_invocation_result.get("runtime_state_mutated") is True,
            },
            "executes_recovery": False,
            "runtime_state_mutated": False,
            "scheduler_mutation_allowed": False,
            "taskrunner_mutation_allowed": False,
            "operator_mutation_allowed": False,
            "metadata": copy.deepcopy(metadata or {}),
        }
        audit_lineage = self._json_safe_mapping(audit_lineage)
        record = build_runtime_evidence_record(
            transaction_id=str(bridge_id or ""),
            execution_intent="runtime_recovery_gate_audit_evidence",
            boundary_state=str(stage or ""),
            verification_state="not_executed",
            rollback_state="not_required",
            seal_state="evidence_only",
            source_execution_id=str(activation_intent.get("intent_id") or bridge_id),
            authority_metadata={
                "admission_allowed": admission.get("allowed") is True,
                "executes_recovery": False,
                "runtime_state_mutated": False,
            },
            audit_lineage=audit_lineage,
            mutation_lineage={
                "runtime_state_mutated": False,
                "scheduler_mutation_allowed": False,
                "taskrunner_mutation_allowed": False,
                "operator_mutation_allowed": False,
            },
        )
        record["evidence_kind"] = "runtime_recovery_gate_audit"
        record["executes_recovery"] = False
        record["runtime_state_mutated"] = False
        return record

    def _status_from_mapping(self, value: dict[str, Any]) -> str:
        if not isinstance(value, dict) or not value:
            return ""
        if value.get("allowed") is False:
            return "denied"
        summary = value.get("dry_run_summary")
        if isinstance(summary, dict):
            summary_status = str(summary.get("status") or "").strip()
            if summary_status:
                return summary_status
        return str(
            value.get("status")
            or value.get("readiness")
            or value.get("mode")
            or ("allowed" if value.get("allowed") is True else "")
        )

    def _json_safe_mapping(self, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(
            value if isinstance(value, dict) else {},
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        decoded = json.loads(encoded)
        return decoded if isinstance(decoded, dict) else {}

    def _normalize_recovery_admission(
        self,
        admission: Any,
        *,
        bridge_id: str,
        current_tick: int,
        supervisor_cases: list[dict[str, Any]],
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if callable(admission):
            admission = admission(
                {
                    "bridge_id": bridge_id,
                    "current_tick": int(current_tick),
                    "supervisor_cases": copy.deepcopy(supervisor_cases),
                    "metadata": copy.deepcopy(metadata or {}),
                    "source": "runtime_supervisor_bridge",
                }
            )

        if hasattr(admission, "to_dict") and callable(admission.to_dict):
            admission = admission.to_dict()
        elif hasattr(admission, "__dict__") and not isinstance(admission, dict):
            admission = dict(admission.__dict__)

        if not isinstance(admission, dict):
            return {
                "allowed": False,
                "reason": "recovery activation admission missing",
                "source": "runtime_supervisor_bridge",
            }

        allowed = (
            admission.get("allowed") is True
            or admission.get("eligible") is True
            or admission.get("admitted") is True
        )
        blocked = admission.get("blocked") is True or admission.get("denied") is True
        return {
            **copy.deepcopy(admission),
            "allowed": bool(allowed and not blocked),
            "source": str(admission.get("source") or "runtime_supervisor_bridge"),
        }

    def _append_event(
        self,
        event_type: str,
        *,
        bridge_id: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_id = "runtime-supervisor-bridge-event-" + stable_supervisor_bridge_fingerprint(
            {
                "event_type": event_type,
                "bridge_id": bridge_id,
                "sequence": len(self._events) + 1,
            }
        )[:16]
        event = RuntimeSupervisorBridgeEvent(
            event_id=event_id,
            event_type=event_type,
            bridge_id=bridge_id,
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._events.append(event)
        self._record_external_event(event.to_dict())

    def _record_external_event(self, event: dict[str, Any]) -> None:
        for target in (self.audit, self.journal):
            if target is None:
                continue
            try:
                if hasattr(target, "append"):
                    target.append(copy.deepcopy(event))
                elif hasattr(target, "record_event"):
                    target.record_event(copy.deepcopy(event))
                elif hasattr(target, "record"):
                    target.record(copy.deepcopy(event))
                elif hasattr(target, "append_record"):
                    target.append_record("runtime_supervisor_bridge", copy.deepcopy(event))
            except Exception:
                pass
