from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any, Callable

from core.runtime.runtime_evidence_chain import (
    build_runtime_evidence_record,
    validate_runtime_evidence_record,
)
from core.runtime.runtime_execution_session import (
    RuntimeExecutionSessionManager,
)
from core.runtime.runtime_replay_engine import RuntimeReplayEngine


@dataclass(frozen=True)
class RuntimeRecoveryStep:
    recovery_id: str
    step_type: str
    status: str
    payload: Any
    metadata: Any
    sequence: int
    result: Any
    governance: Any = None


@dataclass(frozen=True)
class RuntimeRecoveryPlan:
    recovery_id: str
    source_session_id: str
    repair_session_id: str
    replay_id: str
    status: str
    steps: list[RuntimeRecoveryStep]
    payload: Any
    metadata: Any
    sequence: int
    verified: bool
    governance: Any = None


class RuntimeRecoveryRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeRecoveryCoordinator:
    def __init__(
        self,
        session_manager: RuntimeExecutionSessionManager | None = None,
        replay_engine: RuntimeReplayEngine | None = None,
    ) -> None:
        self.session_manager = (
            session_manager
            if session_manager is not None
            else RuntimeExecutionSessionManager()
        )
        self.replay_engine = (
            replay_engine
            if replay_engine is not None
            else RuntimeReplayEngine(session_manager=self.session_manager)
        )
        self._recoveries: dict[str, RuntimeRecoveryPlan] = {}
        self._sequence = 0

    def create_recovery(
        self,
        recovery_id: str,
        source_session_id: str,
        repair_session_id: str | None = None,
        replay_id: str | None = None,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeRecoveryPlan:
        recovery_id = self._validate_recovery_id(recovery_id)
        if recovery_id in self._recoveries:
            raise RuntimeRecoveryRejected(
                f"runtime recovery already exists: {recovery_id!r}"
            )

        source_session = self._get_source_session(source_session_id)
        self._ensure_failed_source(source_session)

        repair_session_id = repair_session_id or f"{recovery_id}:repair"
        replay_id = replay_id or f"{recovery_id}:replay"

        self._create_repair_session(
            repair_session_id=repair_session_id,
            source_session_id=source_session_id,
            recovery_id=recovery_id,
            payload=payload,
            metadata=metadata,
        )

        self._sequence += 1
        plan = RuntimeRecoveryPlan(
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            repair_session_id=repair_session_id,
            replay_id=replay_id,
            status="created",
            steps=self._build_steps(recovery_id, payload, metadata),
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            verified=False,
        )
        plan = replace(
            plan,
            governance=self._build_recovery_governance(plan, status="created"),
        )
        self._recoveries[recovery_id] = plan
        return self._copy_plan(plan)

    def run_recovery(
        self,
        recovery_id: str,
        handler: Callable[[RuntimeRecoveryStep], Any] | None = None,
    ) -> RuntimeRecoveryPlan:
        plan = self._get_existing_plan(recovery_id)
        if plan.status not in {"created", "replayed"}:
            raise RuntimeRecoveryRejected(
                "runtime recovery cannot run from status: "
                f"{plan.status!r}"
            )

        completed_steps = []
        for step in sorted(plan.steps, key=lambda item: item.sequence):
            try:
                result = handler(step) if handler is not None else None
            except Exception as exc:
                raise RuntimeRecoveryRejected(
                    "runtime recovery step handler failed",
                    original_exception=exc,
                ) from exc

            completed_steps.append(
                replace(step, status="completed", result=result)
            )

        replay = self._call_replay(
            self.replay_engine.replay_session,
            plan.replay_id,
            plan.repair_session_id,
            payload=plan.payload,
            metadata=self._metadata_with_recovery_governance(plan),
        )

        updated = replace(
            plan,
            status="replayed",
            steps=[
                replace(step, governance=self._build_step_governance(plan, step))
                for step in completed_steps
            ],
            verified=False,
        )
        updated = replace(
            updated,
            governance=self._build_recovery_governance(
                updated,
                status="replayed",
                replay=replay,
            ),
        )
        self._recoveries[recovery_id] = updated
        return self._copy_plan(updated)

    def verify_recovery(self, recovery_id: str) -> RuntimeRecoveryPlan:
        plan = self._get_existing_plan(recovery_id)
        if plan.status != "replayed":
            raise RuntimeRecoveryRejected(
                "runtime recovery verification requires replayed status"
            )

        replay = self._get_replay(plan.replay_id)
        if replay is None or not replay.verified:
            raise RuntimeRecoveryRejected(
                "runtime recovery replay is not verified"
            )

        if any(step.status != "completed" for step in plan.steps):
            raise RuntimeRecoveryRejected(
                "runtime recovery has incomplete steps"
            )

        self._assert_verified_recovery_governance(plan.governance)
        governance = self._build_recovery_governance(
            plan,
            status="verified",
            replay=replay,
        )
        self._assert_verified_recovery_governance(governance)

        updated = replace(
            plan,
            status="verified",
            verified=True,
            governance=governance,
        )
        self._recoveries[recovery_id] = updated
        return self._copy_plan(updated)

    def get_recovery(self, recovery_id: str) -> RuntimeRecoveryPlan | None:
        plan = self._recoveries.get(recovery_id)
        if plan is None:
            return None

        return self._copy_plan(plan)

    def get_recoveries(self) -> list[RuntimeRecoveryPlan]:
        return [
            self._copy_plan(plan)
            for plan in self._recoveries.values()
        ]

    def clear(self) -> None:
        self._recoveries.clear()
        self._sequence = 0

    def _build_steps(
        self,
        recovery_id: str,
        payload: Any,
        metadata: Any,
    ) -> list[RuntimeRecoveryStep]:
        step_types = [
            "detect_failure",
            "create_repair_session",
            "mark_incident",
            "mark_repaired",
            "prepare_replay",
        ]
        return [
            RuntimeRecoveryStep(
                recovery_id=recovery_id,
                step_type=step_type,
                status="created",
                payload=payload,
                metadata=metadata,
                sequence=index,
                result=None,
            )
            for index, step_type in enumerate(step_types, start=1)
        ]

    def _build_step_governance(
        self,
        plan: RuntimeRecoveryPlan,
        step: RuntimeRecoveryStep,
    ) -> dict[str, Any]:
        return {
            "governance_source": "runtime_recovery_coordinator",
            "recovery_id": plan.recovery_id,
            "step_type": step.step_type,
            "step_status": step.status,
            "source_session_id": plan.source_session_id,
            "repair_session_id": plan.repair_session_id,
            "replay_id": plan.replay_id,
            "executes_raw_recovery": False,
            "executes_raw_rollback": False,
            "executes_raw_repair": False,
        }

    def _build_recovery_governance(
        self,
        plan: RuntimeRecoveryPlan,
        *,
        status: str,
        replay: Any = None,
    ) -> dict[str, Any]:
        metadata = self._safe_mapping(plan.metadata)
        payload = self._safe_mapping(plan.payload)
        lineage = self._lineage_for_recovery(plan, metadata=metadata, payload=payload)
        mutation_transaction_id = self._first_nonempty(
            lineage.get("mutation_transaction_id"),
            metadata.get("mutation_transaction_id"),
            payload.get("mutation_transaction_id"),
            f"recovery_mutation:{plan.recovery_id}",
        )
        mutation_request_id = self._first_nonempty(
            lineage.get("mutation_request_id"),
            metadata.get("mutation_request_id"),
            payload.get("mutation_request_id"),
            f"recovery_request:{plan.recovery_id}",
        )
        repair_transaction_id = self._first_nonempty(
            lineage.get("repair_transaction_id"),
            metadata.get("repair_transaction_id"),
            payload.get("repair_transaction_id"),
            f"recovery_repair:{plan.repair_session_id}",
        )
        continuation_id = self._first_nonempty(
            lineage.get("continuation_id"),
            metadata.get("continuation_id"),
            payload.get("continuation_id"),
        )
        handoff_id = self._first_nonempty(
            lineage.get("handoff_id"),
            metadata.get("handoff_id"),
            payload.get("handoff_id"),
        )
        replay_session_id = self._first_nonempty(
            getattr(replay, "replay_id", ""),
            plan.replay_id,
        )
        authority_metadata = {
            "governance_source": "runtime_recovery_coordinator",
            "source_session_id": plan.source_session_id,
            "repair_session_id": plan.repair_session_id,
            "replay_id": plan.replay_id,
            "recovery_status": status,
            "recovery_verified": status == "verified",
            "manual_recovery_authority": metadata.get("authority", {}),
            "executes_raw_recovery": False,
            "executes_raw_rollback": False,
            "executes_raw_repair": False,
        }
        evidence_record = build_runtime_evidence_record(
            transaction_id=plan.recovery_id,
            execution_intent="runtime_recovery_governance",
            boundary_state=f"runtime_recovery_{status}",
            approval_chain_id=self._first_nonempty(
                metadata.get("approval_chain_id"),
                metadata.get("approval_id"),
                "runtime_recovery_approval",
            ),
            capability_grant_id=self._first_nonempty(
                metadata.get("capability_grant_id"),
                "runtime_recovery",
            ),
            verification_state="verified" if status == "verified" else status,
            rollback_state=self._first_nonempty(
                metadata.get("rollback_state"),
                "rollback_governed",
            ),
            seal_state="evidence_sealed",
            source_execution_id=plan.recovery_id,
            execution_session_id=plan.repair_session_id,
            replay_session_id=replay_session_id,
            continuation_id=continuation_id,
            handoff_id=handoff_id,
            mutation_transaction_id=mutation_transaction_id,
            mutation_request_id=mutation_request_id,
            authority_metadata=authority_metadata,
            audit_lineage={
                **lineage,
                "recovery_id": plan.recovery_id,
                "source_session_id": plan.source_session_id,
                "repair_session_id": plan.repair_session_id,
                "execution_session_id": plan.repair_session_id,
                "replay_id": plan.replay_id,
                "replay_session_id": replay_session_id,
                "mutation_transaction_id": mutation_transaction_id,
                "mutation_request_id": mutation_request_id,
                "repair_transaction_id": repair_transaction_id,
            },
            mutation_lineage={
                "mutation_transaction_id": mutation_transaction_id,
                "mutation_request_id": mutation_request_id,
                "repair_transaction_id": repair_transaction_id,
                "recovery_id": plan.recovery_id,
                "source_session_id": plan.source_session_id,
                "repair_session_id": plan.repair_session_id,
            },
        )
        audit_metadata = {
            "audit_id": self._first_nonempty(
                metadata.get("audit_id"),
                f"audit:{plan.recovery_id}",
            ),
            "evidence_id": evidence_record["evidence_id"],
            "evidence_hash": evidence_record["evidence_hash"],
            "runtime_evidence_id": evidence_record["evidence_id"],
            "recovery_id": plan.recovery_id,
            "source_session_id": plan.source_session_id,
            "execution_session_id": plan.repair_session_id,
            "replay_session_id": replay_session_id,
            "continuation_id": continuation_id,
            "handoff_id": handoff_id,
            "mutation_transaction_id": mutation_transaction_id,
            "mutation_request_id": mutation_request_id,
            "repair_transaction_id": repair_transaction_id,
            "authority": authority_metadata,
            "lineage": evidence_record["audit_lineage"],
        }
        return {
            "schema": "zero.runtime.recovery_governance.v1",
            "governance_source": "runtime_recovery_coordinator",
            "recovery_id": plan.recovery_id,
            "recovery_status": status,
            "runtime_evidence_id": evidence_record["evidence_id"],
            "runtime_evidence_record": evidence_record,
            "runtime_audit_metadata": audit_metadata,
            "authority_metadata": authority_metadata,
            "execution_session_id": plan.repair_session_id,
            "replay_session_id": replay_session_id,
            "continuation_id": continuation_id,
            "handoff_id": handoff_id,
            "mutation_transaction_id": mutation_transaction_id,
            "mutation_request_id": mutation_request_id,
            "repair_transaction_id": repair_transaction_id,
            "lineage": evidence_record["audit_lineage"],
            "raw_recovery_execution_allowed": False,
        }

    def _assert_verified_recovery_governance(self, governance: Any) -> None:
        payload = self._safe_mapping(governance)
        evidence_record = self._safe_mapping(payload.get("runtime_evidence_record"))
        validation = validate_runtime_evidence_record(evidence_record)
        if not validation.get("ok"):
            raise RuntimeRecoveryRejected(
                "runtime recovery governed evidence invalid"
            )
        required_fields = (
            "runtime_evidence_id",
            "runtime_audit_metadata",
            "authority_metadata",
            "execution_session_id",
            "replay_session_id",
            "mutation_transaction_id",
            "mutation_request_id",
            "repair_transaction_id",
        )
        missing = [
            field
            for field in required_fields
            if not self._governance_field_present(payload, field)
        ]
        if missing:
            raise RuntimeRecoveryRejected(
                "runtime recovery governance metadata incomplete: "
                + ", ".join(sorted(missing))
            )
        if payload.get("raw_recovery_execution_allowed") is not False:
            raise RuntimeRecoveryRejected(
                "runtime recovery raw execution bypass is not governed"
            )

    def _metadata_with_recovery_governance(
        self,
        plan: RuntimeRecoveryPlan,
    ) -> Any:
        if not isinstance(plan.metadata, dict):
            return plan.metadata
        return {
            **plan.metadata,
            "runtime_recovery_governance": plan.governance,
        }

    def _lineage_for_recovery(
        self,
        plan: RuntimeRecoveryPlan,
        *,
        metadata: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        metadata_lineage = metadata.get("lineage") if isinstance(metadata.get("lineage"), dict) else {}
        payload_lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
        return {
            **payload_lineage,
            **metadata_lineage,
            "recovery_id": plan.recovery_id,
            "source_session_id": plan.source_session_id,
            "repair_session_id": plan.repair_session_id,
            "replay_id": plan.replay_id,
            "source": "runtime_recovery_coordinator",
        }

    def _governance_field_present(self, payload: dict[str, Any], field: str) -> bool:
        value = payload.get(field)
        if isinstance(value, dict):
            return bool(value)
        return bool(str(value or "").strip())

    def _safe_mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def _first_nonempty(self, *values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _create_repair_session(
        self,
        repair_session_id: str,
        source_session_id: str,
        recovery_id: str,
        payload: Any,
        metadata: Any,
    ) -> None:
        repair_lifecycle_id = f"{repair_session_id}:lifecycle"
        self._call_session(
            self.session_manager.create_session,
            repair_session_id,
            repair_lifecycle_id,
            source="repair_chain",
            parent_session_id=source_session_id,
            replay_group=recovery_id,
            payload=payload,
            metadata=metadata,
        )
        self._call_session(
            self.session_manager.start_session,
            repair_session_id,
            payload=payload,
            metadata=metadata,
        )
        self._call_session(
            self.session_manager.fail_session,
            repair_session_id,
            payload=payload,
            metadata=metadata,
        )
        self._call_session(
            self.session_manager.incident_session,
            repair_session_id,
            payload=payload,
            metadata=metadata,
        )
        self._call_session(
            self.session_manager.repair_session,
            repair_session_id,
            payload=payload,
            metadata=metadata,
        )

    def _get_source_session(self, source_session_id: str):
        try:
            source_session = self.session_manager.get_session(source_session_id)
        except Exception as exc:
            raise RuntimeRecoveryRejected(
                "runtime recovery source session lookup failed",
                original_exception=exc,
            ) from exc

        if source_session is None:
            raise RuntimeRecoveryRejected(
                "runtime recovery source session does not exist: "
                f"{source_session_id!r}"
            )

        return source_session

    def _ensure_failed_source(self, source_session) -> None:
        last_phase = (
            source_session.lifecycle_records[-1].phase
            if source_session.lifecycle_records
            else None
        )
        if last_phase != "failed":
            raise RuntimeRecoveryRejected(
                "runtime recovery source session must be failed"
            )

    def _call_session(self, operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except Exception as exc:
            raise RuntimeRecoveryRejected(
                "runtime recovery session operation failed",
                original_exception=exc,
            ) from exc

    def _call_replay(self, operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except Exception as exc:
            raise RuntimeRecoveryRejected(
                "runtime recovery replay operation failed",
                original_exception=exc,
            ) from exc

    def _get_replay(self, replay_id: str):
        try:
            return self.replay_engine.get_replay(replay_id)
        except Exception as exc:
            raise RuntimeRecoveryRejected(
                "runtime recovery replay lookup failed",
                original_exception=exc,
            ) from exc

    def _get_existing_plan(self, recovery_id: str) -> RuntimeRecoveryPlan:
        recovery_id = self._validate_recovery_id(recovery_id)
        plan = self._recoveries.get(recovery_id)
        if plan is None:
            raise RuntimeRecoveryRejected(
                f"runtime recovery does not exist: {recovery_id!r}"
            )

        return plan

    def _validate_recovery_id(self, recovery_id: str) -> str:
        if not str(recovery_id or "").strip():
            raise RuntimeRecoveryRejected("runtime recovery_id is required")

        return recovery_id

    def _copy_plan(self, plan: RuntimeRecoveryPlan) -> RuntimeRecoveryPlan:
        return replace(
            plan,
            steps=[
                replace(step, governance=copy.deepcopy(step.governance))
                for step in plan.steps
            ],
            governance=copy.deepcopy(plan.governance),
        )
