from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any


class RuntimeOperationStatus:
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"

    TERMINAL = {SUCCEEDED, FAILED, BLOCKED}


@dataclass(frozen=True)
class RuntimeOperationResult:
    operation_id: str
    status: str
    value: Any = None
    failure: Any = None
    metadata: Any = None


class RuntimeOperationRejected(RuntimeError):
    pass


class RuntimeOperation:
    def __init__(
        self,
        operation_id: str,
        operation: str,
        runtime_args: Any = None,
        payload: Any = None,
        metadata: Any = None,
        dependency_ids: list[str] | None = None,
    ) -> None:
        self.operation_id = self._validate_text("operation_id", operation_id)
        self.operation = self._validate_text("operation", operation)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._payload = copy.deepcopy(payload)
        self._metadata = copy.deepcopy(metadata)
        self._dependency_ids = list(dependency_ids or [])
        self.status = RuntimeOperationStatus.PENDING
        self._result: RuntimeOperationResult | None = None
        self._failure: Any = None

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def payload(self) -> Any:
        return copy.deepcopy(self._payload)

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def dependency_ids(self) -> list[str]:
        return list(self._dependency_ids)

    @property
    def result(self) -> RuntimeOperationResult | None:
        if self._result is None:
            return None

        return self._copy_result(self._result)

    @property
    def failure(self) -> Any:
        return copy.deepcopy(self._failure)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "operation_id": self.operation_id,
                "operation": self.operation,
                "runtime_args": self._runtime_args,
                "payload": self._payload,
                "metadata": self._metadata,
                "dependency_ids": self._dependency_ids,
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def start(self) -> "RuntimeOperation":
        self._transition(RuntimeOperationStatus.PENDING, RuntimeOperationStatus.RUNNING)
        return self

    def succeed(
        self,
        value: Any = None,
        metadata: Any = None,
    ) -> RuntimeOperationResult:
        self._require_running("succeed")
        result = self.attach_result(
            RuntimeOperationResult(
                operation_id=self.operation_id,
                status=RuntimeOperationStatus.SUCCEEDED,
                value=value,
                metadata=metadata,
            )
        )
        self.status = RuntimeOperationStatus.SUCCEEDED
        return result

    def fail(
        self,
        failure: Any,
        metadata: Any = None,
    ) -> RuntimeOperationResult:
        self._require_running("fail")
        self.attach_failure(failure)
        result = self.attach_result(
            RuntimeOperationResult(
                operation_id=self.operation_id,
                status=RuntimeOperationStatus.FAILED,
                failure=failure,
                metadata=metadata,
            )
        )
        self.status = RuntimeOperationStatus.FAILED
        return result

    def block(
        self,
        failure: Any,
        metadata: Any = None,
    ) -> RuntimeOperationResult:
        self._require_running("block")
        self.attach_failure(failure)
        result = self.attach_result(
            RuntimeOperationResult(
                operation_id=self.operation_id,
                status=RuntimeOperationStatus.BLOCKED,
                failure=failure,
                metadata=metadata,
            )
        )
        self.status = RuntimeOperationStatus.BLOCKED
        return result

    def attach_result(
        self,
        result: RuntimeOperationResult,
    ) -> RuntimeOperationResult:
        if self._result is not None:
            raise RuntimeOperationRejected(
                "runtime operation result already attached"
            )

        self._result = self._copy_result(result)
        return self._copy_result(self._result)

    def attach_failure(self, failure: Any) -> Any:
        if self._failure is not None:
            raise RuntimeOperationRejected(
                "runtime operation failure already attached"
            )

        self._failure = copy.deepcopy(failure)
        return copy.deepcopy(self._failure)

    def _transition(self, expected: str, next_status: str) -> None:
        if self.status in RuntimeOperationStatus.TERMINAL:
            raise RuntimeOperationRejected(
                f"runtime operation terminal status cannot transition: {self.status!r}"
            )
        if self.status != expected:
            raise RuntimeOperationRejected(
                f"runtime operation expected status {expected!r}, got {self.status!r}"
            )

        self.status = next_status

    def _require_running(self, action: str) -> None:
        if self.status in RuntimeOperationStatus.TERMINAL:
            raise RuntimeOperationRejected(
                f"runtime operation cannot {action} from terminal status {self.status!r}"
            )
        if self.status != RuntimeOperationStatus.RUNNING:
            raise RuntimeOperationRejected(
                f"runtime operation cannot {action} before running"
            )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeOperationRejected(
                f"runtime operation {field_name} is required"
            )

        return value

    def _copy_result(
        self,
        result: RuntimeOperationResult,
    ) -> RuntimeOperationResult:
        return replace(
            result,
            value=copy.deepcopy(result.value),
            failure=copy.deepcopy(result.failure),
            metadata=copy.deepcopy(result.metadata),
        )
