from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from core.runtime.runtime_gate_integration import RuntimeGateIntegration
from core.runtime.runtime_intent_classifier import (
    RuntimeIntent,
    RuntimeIntentClassifier,
)


@dataclass(frozen=True)
class RuntimeIntentRouteResult:
    operation: str
    intent: RuntimeIntent
    gate_result: Any
    runtime_result: Any
    payload: Any
    metadata: Any
    sequence: int


class RuntimeIntentRouteRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeIntentGateRouter:
    def __init__(
        self,
        classifier: RuntimeIntentClassifier | None = None,
        gate_integration: RuntimeGateIntegration | None = None,
    ) -> None:
        self.classifier = (
            classifier if classifier is not None else RuntimeIntentClassifier()
        )
        self.gate_integration = (
            gate_integration
            if gate_integration is not None
            else RuntimeGateIntegration()
        )
        self._results: list[RuntimeIntentRouteResult] = []
        self._sequence = 0

    def route(
        self,
        operation: str,
        runtime_args: dict[str, Any] | None = None,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeIntentRouteResult:
        if not str(operation or "").strip():
            raise RuntimeIntentRouteRejected(
                "runtime intent route operation is required",
                original_exception=ValueError("operation is required"),
            )

        try:
            intent = self.classifier.classify(operation, payload, metadata)
        except Exception as exc:
            raise RuntimeIntentRouteRejected(
                "runtime intent route classification failed",
                original_exception=exc,
            ) from exc

        try:
            integration_result = self._route_intent(
                intent,
                runtime_args=runtime_args,
                payload=payload,
                metadata=metadata,
            )
        except RuntimeIntentRouteRejected:
            raise
        except Exception as exc:
            raise RuntimeIntentRouteRejected(
                "runtime intent route gate integration failed",
                original_exception=exc,
            ) from exc

        self._sequence += 1
        result = RuntimeIntentRouteResult(
            operation=operation,
            intent=intent,
            gate_result=integration_result.gate_result,
            runtime_result=integration_result.runtime_result,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
        )
        self._results.append(result)
        return self._copy_result(result)

    def get_results(self) -> list[RuntimeIntentRouteResult]:
        return [self._copy_result(result) for result in self._results]

    def clear(self) -> None:
        self._results.clear()
        self._sequence = 0

    def _route_intent(
        self,
        intent: RuntimeIntent,
        runtime_args: dict[str, Any] | None,
        payload: Any,
        metadata: Any,
    ) -> Any:
        args = self._require_runtime_args(runtime_args)

        routes: dict[str, Callable[[dict[str, Any], Any, Any], Any]] = {
            "lifecycle.queue": self._route_lifecycle_queue,
            "lifecycle.dispatch": self._route_lifecycle_dispatch,
            "lifecycle.start_execution": self._route_lifecycle_start_execution,
            "lifecycle.complete_execution": self._route_lifecycle_complete_execution,
            "lifecycle.fail_execution": self._route_lifecycle_fail_execution,
            "replay.session": self._route_replay_session,
            "recovery.create": self._route_recovery_create,
            "recovery.run": self._route_recovery_run,
            "recovery.verify": self._route_recovery_verify,
        }
        route = routes.get(intent.operation)
        if route is None:
            raise RuntimeIntentRouteRejected(
                f"runtime intent route unsupported operation: {intent.operation!r}",
                original_exception=KeyError(intent.operation),
            )

        try:
            return route(args, payload, metadata)
        except RuntimeIntentRouteRejected:
            raise
        except Exception as exc:
            raise RuntimeIntentRouteRejected(
                "runtime intent route gate integration failed",
                original_exception=exc,
            ) from exc

    def _route_lifecycle_queue(
        self,
        args: dict[str, Any],
        payload: Any,
        metadata: Any,
    ) -> Any:
        return self.gate_integration.gated_lifecycle_queue(
            self._require_arg(args, "lifecycle_id"),
            payload,
            metadata,
        )

    def _route_lifecycle_dispatch(
        self,
        args: dict[str, Any],
        payload: Any,
        metadata: Any,
    ) -> Any:
        return self.gate_integration.gated_lifecycle_dispatch(
            self._require_arg(args, "lifecycle_id"),
            payload,
            metadata,
        )

    def _route_lifecycle_start_execution(
        self,
        args: dict[str, Any],
        payload: Any,
        metadata: Any,
    ) -> Any:
        return self.gate_integration.gated_lifecycle_start_execution(
            self._require_arg(args, "lifecycle_id"),
            payload,
            metadata,
        )

    def _route_lifecycle_complete_execution(
        self,
        args: dict[str, Any],
        payload: Any,
        metadata: Any,
    ) -> Any:
        return self.gate_integration.gated_lifecycle_complete_execution(
            self._require_arg(args, "lifecycle_id"),
            payload,
            metadata,
        )

    def _route_lifecycle_fail_execution(
        self,
        args: dict[str, Any],
        payload: Any,
        metadata: Any,
    ) -> Any:
        return self.gate_integration.gated_lifecycle_fail_execution(
            self._require_arg(args, "lifecycle_id"),
            payload,
            metadata,
        )

    def _route_replay_session(
        self,
        args: dict[str, Any],
        payload: Any,
        metadata: Any,
    ) -> Any:
        return self.gate_integration.gated_replay_session(
            self._require_arg(args, "replay_id"),
            self._require_arg(args, "source_session_id"),
            payload,
            metadata,
        )

    def _route_recovery_create(
        self,
        args: dict[str, Any],
        payload: Any,
        metadata: Any,
    ) -> Any:
        return self.gate_integration.gated_create_recovery(
            self._require_arg(args, "recovery_id"),
            self._require_arg(args, "source_session_id"),
            payload,
            metadata,
        )

    def _route_recovery_run(
        self,
        args: dict[str, Any],
        payload: Any,
        metadata: Any,
    ) -> Any:
        return self.gate_integration.gated_run_recovery(
            self._require_arg(args, "recovery_id"),
            payload,
            metadata,
        )

    def _route_recovery_verify(
        self,
        args: dict[str, Any],
        payload: Any,
        metadata: Any,
    ) -> Any:
        return self.gate_integration.gated_verify_recovery(
            self._require_arg(args, "recovery_id"),
            payload,
            metadata,
        )

    def _require_runtime_args(
        self,
        runtime_args: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if runtime_args is None:
            raise RuntimeIntentRouteRejected(
                "runtime intent route runtime_args are required",
                original_exception=ValueError("runtime_args are required"),
            )
        if not isinstance(runtime_args, dict):
            raise RuntimeIntentRouteRejected(
                "runtime intent route runtime_args must be a dict",
                original_exception=TypeError("runtime_args must be a dict"),
            )

        return runtime_args

    def _require_arg(self, runtime_args: dict[str, Any], name: str) -> Any:
        value = runtime_args.get(name)
        if not str(value or "").strip():
            raise RuntimeIntentRouteRejected(
                f"runtime intent route {name} is required",
                original_exception=ValueError(f"{name} is required"),
            )

        return value

    def _copy_result(
        self,
        result: RuntimeIntentRouteResult,
    ) -> RuntimeIntentRouteResult:
        return replace(result)
