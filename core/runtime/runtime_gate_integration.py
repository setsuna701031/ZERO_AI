from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from core.runtime.runtime_execution_gate import (
    RuntimeExecutionGate,
    RuntimeGateRejected,
    RuntimeGateResult,
)
from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline
from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryCoordinator
from core.runtime.runtime_replay_engine import RuntimeReplayEngine


@dataclass(frozen=True)
class RuntimeGateIntegrationResult:
    operation: str
    target: str
    action: str
    gate_result: RuntimeGateResult
    runtime_result: Any
    payload: Any
    metadata: Any
    sequence: int


class RuntimeGateIntegrationRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        gate_result: RuntimeGateResult | None = None,
        original_exception: BaseException | None = None,
    ) -> None:
        self.gate_result = gate_result
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeGateIntegration:
    def __init__(
        self,
        gate: RuntimeExecutionGate | None = None,
        lifecycle_pipeline: RuntimeLifecyclePipeline | None = None,
        replay_engine: RuntimeReplayEngine | None = None,
        recovery_coordinator: RuntimeRecoveryCoordinator | None = None,
    ) -> None:
        self.gate = gate if gate is not None else RuntimeExecutionGate()
        self.lifecycle_pipeline = (
            lifecycle_pipeline
            if lifecycle_pipeline is not None
            else RuntimeLifecyclePipeline()
        )
        self.replay_engine = (
            replay_engine if replay_engine is not None else RuntimeReplayEngine()
        )
        self.recovery_coordinator = (
            recovery_coordinator
            if recovery_coordinator is not None
            else RuntimeRecoveryCoordinator()
        )
        self._results: list[RuntimeGateIntegrationResult] = []
        self._sequence = 0

    def gated_lifecycle_queue(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateIntegrationResult:
        return self._run_gated(
            operation="gated_lifecycle_queue",
            target="lifecycle",
            action="queue",
            runtime_operation=self.lifecycle_pipeline.queue,
            runtime_args=(lifecycle_id,),
            payload=payload,
            metadata=metadata,
        )

    def gated_lifecycle_dispatch(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateIntegrationResult:
        return self._run_gated(
            operation="gated_lifecycle_dispatch",
            target="lifecycle",
            action="dispatch",
            runtime_operation=self.lifecycle_pipeline.dispatch,
            runtime_args=(lifecycle_id,),
            payload=payload,
            metadata=metadata,
        )

    def gated_lifecycle_start_execution(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateIntegrationResult:
        return self._run_gated(
            operation="gated_lifecycle_start_execution",
            target="lifecycle",
            action="start_execution",
            runtime_operation=self.lifecycle_pipeline.start_execution,
            runtime_args=(lifecycle_id,),
            payload=payload,
            metadata=metadata,
        )

    def gated_lifecycle_complete_execution(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateIntegrationResult:
        return self._run_gated(
            operation="gated_lifecycle_complete_execution",
            target="lifecycle",
            action="complete_execution",
            runtime_operation=self.lifecycle_pipeline.complete_execution,
            runtime_args=(lifecycle_id,),
            payload=payload,
            metadata=metadata,
        )

    def gated_lifecycle_fail_execution(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateIntegrationResult:
        return self._run_gated(
            operation="gated_lifecycle_fail_execution",
            target="lifecycle",
            action="fail_execution",
            runtime_operation=self.lifecycle_pipeline.fail_execution,
            runtime_args=(lifecycle_id,),
            payload=payload,
            metadata=metadata,
        )

    def gated_replay_session(
        self,
        replay_id: str,
        source_session_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateIntegrationResult:
        return self._run_gated(
            operation="gated_replay_session",
            target="replay",
            action="session",
            runtime_operation=self.replay_engine.replay_session,
            runtime_args=(replay_id, source_session_id),
            payload=payload,
            metadata=metadata,
        )

    def gated_create_recovery(
        self,
        recovery_id: str,
        source_session_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateIntegrationResult:
        return self._run_gated(
            operation="gated_create_recovery",
            target="recovery",
            action="create",
            runtime_operation=self.recovery_coordinator.create_recovery,
            runtime_args=(recovery_id, source_session_id),
            payload=payload,
            metadata=metadata,
        )

    def gated_run_recovery(
        self,
        recovery_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateIntegrationResult:
        return self._run_gated(
            operation="gated_run_recovery",
            target="recovery",
            action="run",
            runtime_operation=self.recovery_coordinator.run_recovery,
            runtime_args=(recovery_id,),
            payload=payload,
            metadata=metadata,
            pass_payload_metadata=False,
        )

    def gated_verify_recovery(
        self,
        recovery_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateIntegrationResult:
        return self._run_gated(
            operation="gated_verify_recovery",
            target="recovery",
            action="verify",
            runtime_operation=self.recovery_coordinator.verify_recovery,
            runtime_args=(recovery_id,),
            payload=payload,
            metadata=metadata,
            pass_payload_metadata=False,
        )

    def get_results(self) -> list[RuntimeGateIntegrationResult]:
        return [self._copy_result(result) for result in self._results]

    def clear(self) -> None:
        self._results.clear()
        self._sequence = 0

    def _run_gated(
        self,
        operation: str,
        target: str,
        action: str,
        runtime_operation: Callable[..., Any],
        runtime_args: tuple[Any, ...],
        payload: Any,
        metadata: Any,
        pass_payload_metadata: bool = True,
    ) -> RuntimeGateIntegrationResult:
        try:
            gate_result = self.gate.assert_open(
                target,
                action,
                payload=payload,
                metadata=metadata,
            )
        except RuntimeGateRejected as exc:
            raise RuntimeGateIntegrationRejected(
                "runtime gate integration rejected by gate",
                gate_result=exc.gate_result,
                original_exception=exc,
            ) from exc
        except Exception as exc:
            raise RuntimeGateIntegrationRejected(
                "runtime gate integration gate operation failed",
                original_exception=exc,
            ) from exc

        try:
            if pass_payload_metadata:
                runtime_result = runtime_operation(
                    *runtime_args,
                    payload=payload,
                    metadata=metadata,
                )
            else:
                runtime_result = runtime_operation(*runtime_args)
        except Exception as exc:
            raise RuntimeGateIntegrationRejected(
                "runtime gate integration runtime operation failed",
                gate_result=gate_result,
                original_exception=exc,
            ) from exc

        self._sequence += 1
        result = RuntimeGateIntegrationResult(
            operation=operation,
            target=target,
            action=action,
            gate_result=gate_result,
            runtime_result=runtime_result,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
        )
        self._results.append(result)
        return self._copy_result(result)

    def _copy_result(
        self,
        result: RuntimeGateIntegrationResult,
    ) -> RuntimeGateIntegrationResult:
        return replace(result)
