from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from core.runtime.runtime_capability_resolver import (
    RuntimeCapability,
    RuntimeCapabilityResolver,
)
from core.runtime.runtime_intent_gate_router import (
    RuntimeIntentGateRouter,
    RuntimeIntentRouteResult,
)


@dataclass(frozen=True)
class RuntimeCapabilityDispatchResult:
    operation: str
    capability: RuntimeCapability
    route_result: RuntimeIntentRouteResult
    payload: Any
    metadata: Any
    runtime_args: Any
    sequence: int


class RuntimeCapabilityDispatchRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeCapabilityDispatcher:
    def __init__(
        self,
        resolver: RuntimeCapabilityResolver | None = None,
        router: RuntimeIntentGateRouter | None = None,
    ) -> None:
        self.resolver = resolver if resolver is not None else RuntimeCapabilityResolver()
        self.router = router if router is not None else RuntimeIntentGateRouter()
        self._results: list[RuntimeCapabilityDispatchResult] = []
        self._sequence = 0

    def dispatch(
        self,
        operation: str,
        runtime_args: Any = None,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeCapabilityDispatchResult:
        if not str(operation or "").strip():
            raise RuntimeCapabilityDispatchRejected(
                "runtime capability dispatch operation is required",
                original_exception=ValueError("operation is required"),
            )

        try:
            capability = self.resolver.resolve(operation)
        except Exception as exc:
            raise RuntimeCapabilityDispatchRejected(
                "runtime capability dispatch resolve failed",
                original_exception=exc,
            ) from exc

        try:
            route_result = self.router.route(
                operation,
                runtime_args=runtime_args,
                payload=payload,
                metadata=metadata,
            )
        except Exception as exc:
            raise RuntimeCapabilityDispatchRejected(
                "runtime capability dispatch route failed",
                original_exception=exc,
            ) from exc

        self._sequence += 1
        result = RuntimeCapabilityDispatchResult(
            operation=operation,
            capability=capability,
            route_result=route_result,
            payload=payload,
            metadata=metadata,
            runtime_args=runtime_args,
            sequence=self._sequence,
        )
        self._results.append(result)
        return self._copy_result(result)

    def dispatch_many(self, requests: list[dict[str, Any]]) -> list[RuntimeCapabilityDispatchResult]:
        results: list[RuntimeCapabilityDispatchResult] = []
        try:
            for request in requests:
                results.append(
                    self.dispatch(
                        request.get("operation"),
                        runtime_args=request.get("runtime_args"),
                        payload=request.get("payload"),
                        metadata=request.get("metadata"),
                    )
                )
        except RuntimeCapabilityDispatchRejected as exc:
            raise RuntimeCapabilityDispatchRejected(
                "runtime capability dispatch_many failed",
                original_exception=exc,
            ) from exc
        except Exception as exc:
            raise RuntimeCapabilityDispatchRejected(
                "runtime capability dispatch_many failed",
                original_exception=exc,
            ) from exc

        return results

    def get_results(self) -> list[RuntimeCapabilityDispatchResult]:
        return [self._copy_result(result) for result in self._results]

    def clear(self) -> None:
        self._results.clear()
        self._sequence = 0

    def _copy_result(
        self,
        result: RuntimeCapabilityDispatchResult,
    ) -> RuntimeCapabilityDispatchResult:
        return replace(result)
