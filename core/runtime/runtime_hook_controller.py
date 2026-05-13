from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.runtime.runtime_integration_adapter import (
    RuntimeAdapterResult,
    RuntimeIntegrationAdapter,
)


@dataclass(frozen=True)
class RuntimeHookResult:
    hook_name: str
    source: str
    phase: str
    adapter_result: RuntimeAdapterResult | None
    payload: Any
    metadata: Any
    skipped: bool
    reason: str | None


class RuntimeHookRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeHookController:
    def __init__(
        self,
        adapter: RuntimeIntegrationAdapter | None = None,
        enabled: bool = True,
    ) -> None:
        self.adapter = adapter if adapter is not None else RuntimeIntegrationAdapter()
        self._enabled = bool(enabled)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def before_queue_transition(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeHookResult:
        return self._run_hook(
            hook_name="before_queue_transition",
            source="scheduler",
            phase="before",
            mirror=self.adapter.mirror_scheduler_queue_transition,
            payload=payload,
            metadata=metadata,
        )

    def after_queue_transition(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeHookResult:
        return self._run_hook(
            hook_name="after_queue_transition",
            source="scheduler",
            phase="after",
            mirror=self.adapter.mirror_scheduler_queue_transition,
            payload=payload,
            metadata=metadata,
        )

    def before_execution_result_write(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeHookResult:
        return self._run_hook(
            hook_name="before_execution_result_write",
            source="step_executor",
            phase="before",
            mirror=self.adapter.mirror_executor_result_write,
            payload=payload,
            metadata=metadata,
        )

    def after_execution_result_write(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeHookResult:
        return self._run_hook(
            hook_name="after_execution_result_write",
            source="step_executor",
            phase="after",
            mirror=self.adapter.mirror_executor_result_write,
            payload=payload,
            metadata=metadata,
        )

    def before_orchestrator_dispatch(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeHookResult:
        return self._run_hook(
            hook_name="before_orchestrator_dispatch",
            source="orchestrator",
            phase="before",
            mirror=self.adapter.mirror_orchestrator_dispatch,
            payload=payload,
            metadata=metadata,
        )

    def after_orchestrator_dispatch(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeHookResult:
        return self._run_hook(
            hook_name="after_orchestrator_dispatch",
            source="orchestrator",
            phase="after",
            mirror=self.adapter.mirror_orchestrator_dispatch,
            payload=payload,
            metadata=metadata,
        )

    def before_repair_incident(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeHookResult:
        return self._run_hook(
            hook_name="before_repair_incident",
            source="repair_chain",
            phase="before",
            mirror=self.adapter.mirror_repair_incident,
            payload=payload,
            metadata=metadata,
        )

    def after_repair_incident(
        self,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeHookResult:
        return self._run_hook(
            hook_name="after_repair_incident",
            source="repair_chain",
            phase="after",
            mirror=self.adapter.mirror_repair_incident,
            payload=payload,
            metadata=metadata,
        )

    def _run_hook(
        self,
        hook_name: str,
        source: str,
        phase: str,
        mirror: Callable[..., RuntimeAdapterResult],
        payload: Any,
        metadata: Any,
    ) -> RuntimeHookResult:
        if not self._enabled:
            return RuntimeHookResult(
                hook_name=hook_name,
                source=source,
                phase=phase,
                adapter_result=None,
                payload=payload,
                metadata=metadata,
                skipped=True,
                reason="runtime hook disabled",
            )

        try:
            adapter_result = mirror(payload=payload, metadata=metadata)
        except Exception as exc:
            raise RuntimeHookRejected(
                "runtime hook controller rejected hook operation",
                original_exception=exc,
            ) from exc

        return RuntimeHookResult(
            hook_name=hook_name,
            source=source,
            phase=phase,
            adapter_result=adapter_result,
            payload=payload,
            metadata=metadata,
            skipped=False,
            reason=None,
        )
