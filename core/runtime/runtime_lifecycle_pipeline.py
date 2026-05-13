from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.runtime.runtime_integration_adapter import RuntimeAdapterResult
from core.runtime.runtime_hook_controller import RuntimeHookController, RuntimeHookResult


@dataclass(frozen=True)
class RuntimeLifecycleRecord:
    lifecycle_id: str
    phase: str
    source: str
    payload: Any
    metadata: Any
    sequence: int
    adapter_result: RuntimeAdapterResult | None


class RuntimeLifecycleRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeLifecyclePipeline:
    def __init__(self, hook_controller: RuntimeHookController | None = None) -> None:
        self.hook_controller = (
            hook_controller
            if hook_controller is not None
            else RuntimeHookController()
        )
        self._records: list[RuntimeLifecycleRecord] = []
        self._sequence = 0

    def queue(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeLifecycleRecord:
        return self._advance(
            lifecycle_id=lifecycle_id,
            phase="queued",
            source="scheduler",
            hook=self.hook_controller.after_queue_transition,
            payload=payload,
            metadata=metadata,
        )

    def dispatch(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeLifecycleRecord:
        return self._advance(
            lifecycle_id=lifecycle_id,
            phase="dispatched",
            source="orchestrator",
            hook=self.hook_controller.after_orchestrator_dispatch,
            payload=payload,
            metadata=metadata,
        )

    def start_execution(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeLifecycleRecord:
        return self._advance(
            lifecycle_id=lifecycle_id,
            phase="executing",
            source="step_executor",
            hook=self.hook_controller.before_execution_result_write,
            payload=payload,
            metadata=metadata,
        )

    def complete_execution(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeLifecycleRecord:
        return self._advance(
            lifecycle_id=lifecycle_id,
            phase="completed",
            source="step_executor",
            hook=self.hook_controller.after_execution_result_write,
            payload=payload,
            metadata=metadata,
        )

    def fail_execution(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeLifecycleRecord:
        return self._advance(
            lifecycle_id=lifecycle_id,
            phase="failed",
            source="step_executor",
            hook=self.hook_controller.after_execution_result_write,
            payload=payload,
            metadata=metadata,
        )

    def incident(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeLifecycleRecord:
        return self._advance(
            lifecycle_id=lifecycle_id,
            phase="incident",
            source="repair_chain",
            hook=self.hook_controller.after_repair_incident,
            payload=payload,
            metadata=metadata,
        )

    def repair(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeLifecycleRecord:
        return self._advance(
            lifecycle_id=lifecycle_id,
            phase="repaired",
            source="repair_chain",
            hook=self.hook_controller.after_repair_incident,
            payload=payload,
            metadata=metadata,
        )

    def replay(
        self,
        lifecycle_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeLifecycleRecord:
        return self._advance(
            lifecycle_id=lifecycle_id,
            phase="replayed",
            source="runtime_lifecycle",
            hook=None,
            payload=payload,
            metadata=metadata,
        )

    def get_records(self, lifecycle_id: str | None = None) -> list[RuntimeLifecycleRecord]:
        if lifecycle_id is None:
            return list(self._records)

        return [
            record
            for record in self._records
            if record.lifecycle_id == lifecycle_id
        ]

    def replay_records(
        self,
        lifecycle_id: str | None = None,
        handler: Callable[[RuntimeLifecycleRecord], None] | None = None,
    ) -> list[RuntimeLifecycleRecord]:
        records = sorted(
            self.get_records(lifecycle_id=lifecycle_id),
            key=lambda record: record.sequence,
        )

        if handler is None:
            return list(records)

        for record in records:
            try:
                handler(record)
            except Exception as exc:
                raise RuntimeLifecycleRejected(
                    "runtime lifecycle replay handler failed",
                    original_exception=exc,
                ) from exc

        return list(records)

    def clear(self) -> None:
        self._records.clear()
        self._sequence = 0

    def _advance(
        self,
        lifecycle_id: str,
        phase: str,
        source: str,
        hook: Callable[..., RuntimeHookResult] | None,
        payload: Any,
        metadata: Any,
    ) -> RuntimeLifecycleRecord:
        lifecycle_id = self._validate_lifecycle_id(lifecycle_id)
        self._validate_transition(lifecycle_id, phase)

        hook_result = None
        if hook is not None:
            try:
                hook_result = hook(payload=payload, metadata=metadata)
            except Exception as exc:
                raise RuntimeLifecycleRejected(
                    "runtime lifecycle hook failed",
                    original_exception=exc,
                ) from exc

        self._sequence += 1
        record = RuntimeLifecycleRecord(
            lifecycle_id=lifecycle_id,
            phase=phase,
            source=source,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            adapter_result=(
                hook_result.adapter_result
                if hook_result is not None
                else None
            ),
        )
        self._records.append(record)
        return record

    def _validate_lifecycle_id(self, lifecycle_id: str) -> str:
        if not str(lifecycle_id or "").strip():
            raise RuntimeLifecycleRejected("runtime lifecycle_id is required")

        return lifecycle_id

    def _validate_transition(self, lifecycle_id: str, phase: str) -> None:
        phases = [
            record.phase
            for record in self._records
            if record.lifecycle_id == lifecycle_id
        ]
        previous = phases[-1] if phases else None

        allowed_previous = {
            "queued": {None},
            "dispatched": {"queued"},
            "executing": {"dispatched"},
            "completed": {"executing"},
            "failed": {"executing"},
            "incident": {"failed"},
            "repaired": {"incident"},
            "replayed": {"completed", "repaired"},
        }

        if previous not in allowed_previous[phase]:
            raise RuntimeLifecycleRejected(
                "runtime lifecycle transition rejected: "
                f"lifecycle_id={lifecycle_id!r}, phase={phase!r}, "
                f"previous={previous!r}"
            )
