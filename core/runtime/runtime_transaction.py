from __future__ import annotations

import copy
import hashlib
import json
from collections import OrderedDict
from typing import Any

from core.runtime.runtime_operation import RuntimeOperation, RuntimeOperationStatus


class RuntimeTransactionRejected(RuntimeError):
    pass


class RuntimeTransaction:
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL_FAILED = "partial_failed"
    BLOCKED = "blocked"

    def __init__(
        self,
        transaction_id: str,
        runtime_args: Any = None,
        metadata: Any = None,
    ) -> None:
        self.transaction_id = self._validate_text("transaction_id", transaction_id)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._metadata = copy.deepcopy(metadata)
        self._operations: OrderedDict[str, RuntimeOperation] = OrderedDict()

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def status(self) -> str:
        statuses = [operation.status for operation in self._operations.values()]
        if not statuses or all(status == RuntimeOperationStatus.PENDING for status in statuses):
            return self.PENDING
        if any(status == RuntimeOperationStatus.RUNNING for status in statuses):
            return self.RUNNING
        if all(status == RuntimeOperationStatus.SUCCEEDED for status in statuses):
            return self.SUCCEEDED
        if all(status == RuntimeOperationStatus.FAILED for status in statuses):
            return self.FAILED
        if all(status == RuntimeOperationStatus.BLOCKED for status in statuses):
            return self.BLOCKED
        if any(
            status in {
                RuntimeOperationStatus.FAILED,
                RuntimeOperationStatus.BLOCKED,
            }
            for status in statuses
        ):
            return self.PARTIAL_FAILED

        return self.RUNNING

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "transaction_id": self.transaction_id,
                "runtime_args": self._runtime_args,
                "metadata": self._metadata,
                "operation_fingerprints": [
                    operation.fingerprint
                    for operation in self._operations.values()
                ],
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def add_operation(self, operation: RuntimeOperation) -> RuntimeOperation:
        operation_id = self._validate_text(
            "operation_id",
            getattr(operation, "operation_id", None),
        )
        if operation_id in self._operations:
            raise RuntimeTransactionRejected(
                f"runtime transaction duplicate operation_id: {operation_id!r}"
            )

        self._operations[operation_id] = operation
        return operation

    def remove_operation(self, operation_id: str) -> RuntimeOperation:
        operation_id = self._validate_text("operation_id", operation_id)
        operation = self._operations.get(operation_id)
        if operation is None:
            raise RuntimeTransactionRejected(
                f"runtime transaction unknown operation_id: {operation_id!r}"
            )

        del self._operations[operation_id]
        return operation

    def get_operation(self, operation_id: str) -> RuntimeOperation:
        operation_id = self._validate_text("operation_id", operation_id)
        operation = self._operations.get(operation_id)
        if operation is None:
            raise RuntimeTransactionRejected(
                f"runtime transaction unknown operation_id: {operation_id!r}"
            )

        return operation

    def list_operations(self) -> list[RuntimeOperation]:
        return list(self._operations.values())

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeTransactionRejected(
                f"runtime transaction {field_name} is required"
            )

        return value
