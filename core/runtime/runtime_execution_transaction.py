from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from core.runtime.runtime_capability_dispatcher import RuntimeCapabilityDispatcher


_TRANSACTION_STATUSES = {
    "created",
    "running",
    "completed",
    "committed",
    "rolled_back",
    "failed",
}
_STEP_STATUSES = {"pending", "running", "completed", "failed", "skipped"}


@dataclass
class RuntimeExecutionTransactionStep:
    transaction_id: str
    operation: str
    runtime_args: Any
    payload: Any
    metadata: Any
    status: str
    result: Any
    sequence: int


@dataclass
class RuntimeExecutionTransaction:
    transaction_id: str
    status: str
    steps: list[RuntimeExecutionTransactionStep]
    results: list[Any]
    payload: Any
    metadata: Any
    sequence: int
    committed: bool
    rolled_back: bool


class RuntimeExecutionTransactionRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeExecutionTransactionManager:
    def __init__(self, dispatcher: RuntimeCapabilityDispatcher | None = None) -> None:
        self.dispatcher = dispatcher if dispatcher is not None else RuntimeCapabilityDispatcher()
        self._transactions: dict[str, RuntimeExecutionTransaction] = {}
        self._sequence = 0

    def begin(
        self,
        transaction_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionTransaction:
        transaction_id = self._validate_text("transaction_id", transaction_id)
        if transaction_id in self._transactions:
            raise RuntimeExecutionTransactionRejected(
                f"runtime execution transaction already exists: {transaction_id!r}"
            )

        self._sequence += 1
        transaction = RuntimeExecutionTransaction(
            transaction_id=transaction_id,
            status="created",
            steps=[],
            results=[],
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            committed=False,
            rolled_back=False,
        )
        self._transactions[transaction_id] = transaction
        return self._copy_transaction(transaction)

    def add_step(
        self,
        transaction_id: str,
        operation: str,
        runtime_args: Any = None,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionTransactionStep:
        transaction = self._require_transaction(transaction_id)
        self._require_status(transaction, {"created"}, "add step")
        operation = self._validate_text("operation", operation)

        step = RuntimeExecutionTransactionStep(
            transaction_id=transaction.transaction_id,
            operation=operation,
            runtime_args=runtime_args,
            payload=payload,
            metadata=metadata,
            status="pending",
            result=None,
            sequence=len(transaction.steps) + 1,
        )
        transaction.steps.append(step)
        return self._copy_step(step)

    def run(
        self,
        transaction_id: str,
        handler: Callable[[RuntimeExecutionTransactionStep, Any], Any] | None = None,
    ) -> RuntimeExecutionTransaction:
        transaction = self._require_transaction(transaction_id)
        self._require_status(transaction, {"created"}, "run")

        transaction.status = "running"
        for index, step in enumerate(transaction.steps):
            try:
                step.status = "running"
                dispatch_result = self.dispatcher.dispatch(
                    step.operation,
                    runtime_args=step.runtime_args,
                    payload=step.payload,
                    metadata=step.metadata,
                )
                step.result = (
                    handler(self._copy_step(step), dispatch_result)
                    if handler is not None
                    else dispatch_result
                )
                step.status = "completed"
                transaction.results.append(step.result)
            except Exception as exc:
                step.status = "failed"
                transaction.status = "failed"
                for remaining in transaction.steps[index + 1 :]:
                    if remaining.status == "pending":
                        remaining.status = "skipped"
                raise RuntimeExecutionTransactionRejected(
                    "runtime execution transaction dispatch failed",
                    original_exception=exc,
                ) from exc

        transaction.status = "completed"
        return self._copy_transaction(transaction)

    def commit(self, transaction_id: str) -> RuntimeExecutionTransaction:
        transaction = self._require_transaction(transaction_id)
        self._require_status(transaction, {"completed"}, "commit")

        transaction.status = "committed"
        transaction.committed = True
        return self._copy_transaction(transaction)

    def rollback(
        self,
        transaction_id: str,
        reason: Any = None,
    ) -> RuntimeExecutionTransaction:
        transaction = self._require_transaction(transaction_id)
        if transaction.status == "committed":
            raise RuntimeExecutionTransactionRejected(
                "runtime execution transaction cannot rollback committed transaction"
            )
        self._require_status(
            transaction,
            {"created", "running", "completed", "failed"},
            "rollback",
        )

        for step in transaction.steps:
            if step.status in {"pending", "running"}:
                step.status = "skipped"
        transaction.status = "rolled_back"
        transaction.rolled_back = True
        return self._copy_transaction(transaction)

    def get_transaction(self, transaction_id: str) -> RuntimeExecutionTransaction:
        return self._copy_transaction(self._require_transaction(transaction_id))

    def get_transactions(self) -> list[RuntimeExecutionTransaction]:
        return [
            self._copy_transaction(transaction)
            for transaction in self._transactions.values()
        ]

    def clear(self) -> None:
        self._transactions.clear()
        self._sequence = 0

    def _require_transaction(
        self,
        transaction_id: str,
    ) -> RuntimeExecutionTransaction:
        transaction_id = self._validate_text("transaction_id", transaction_id)
        transaction = self._transactions.get(transaction_id)
        if transaction is None:
            raise RuntimeExecutionTransactionRejected(
                f"runtime execution transaction unknown: {transaction_id!r}"
            )

        return transaction

    def _require_status(
        self,
        transaction: RuntimeExecutionTransaction,
        allowed: set[str],
        action: str,
    ) -> None:
        if transaction.status not in _TRANSACTION_STATUSES:
            raise RuntimeExecutionTransactionRejected(
                f"runtime execution transaction invalid status: {transaction.status!r}"
            )
        if transaction.status not in allowed:
            raise RuntimeExecutionTransactionRejected(
                "runtime execution transaction cannot "
                f"{action} while status is {transaction.status!r}"
            )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeExecutionTransactionRejected(
                f"runtime execution transaction {field_name} is required"
            )

        return value

    def _copy_transaction(
        self,
        transaction: RuntimeExecutionTransaction,
    ) -> RuntimeExecutionTransaction:
        return replace(
            transaction,
            steps=[self._copy_step(step) for step in transaction.steps],
            results=list(transaction.results),
        )

    def _copy_step(
        self,
        step: RuntimeExecutionTransactionStep,
    ) -> RuntimeExecutionTransactionStep:
        if step.status not in _STEP_STATUSES:
            raise RuntimeExecutionTransactionRejected(
                f"runtime execution transaction invalid step status: {step.status!r}"
            )

        return replace(step)
