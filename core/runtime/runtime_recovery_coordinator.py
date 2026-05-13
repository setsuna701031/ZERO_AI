from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

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

        self._call_replay(
            self.replay_engine.replay_session,
            plan.replay_id,
            plan.repair_session_id,
            payload=plan.payload,
            metadata=plan.metadata,
        )

        updated = replace(
            plan,
            status="replayed",
            steps=completed_steps,
            verified=False,
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

        updated = replace(plan, status="verified", verified=True)
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
        return replace(plan, steps=list(plan.steps))
