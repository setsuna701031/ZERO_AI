from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from core.runtime.runtime_execution_transaction import RuntimeExecutionTransactionManager


_ORCHESTRATION_STATUSES = {
    "created",
    "running",
    "completed",
    "committed",
    "rolled_back",
    "failed",
}
_ITEM_STATUSES = {
    "pending",
    "running",
    "completed",
    "committed",
    "rolled_back",
    "failed",
    "skipped",
}


@dataclass
class RuntimeTransactionOrchestrationItem:
    orchestration_id: str
    transaction_id: str
    steps: Any
    status: str
    result: Any
    sequence: int


@dataclass
class RuntimeTransactionOrchestration:
    orchestration_id: str
    status: str
    items: list[RuntimeTransactionOrchestrationItem]
    results: list[Any]
    payload: Any
    metadata: Any
    sequence: int
    committed: bool
    rolled_back: bool


class RuntimeTransactionOrchestrationRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeTransactionOrchestrator:
    def __init__(
        self,
        transaction_manager: RuntimeExecutionTransactionManager | None = None,
    ) -> None:
        self.transaction_manager = (
            transaction_manager
            if transaction_manager is not None
            else RuntimeExecutionTransactionManager()
        )
        self._orchestrations: dict[str, RuntimeTransactionOrchestration] = {}
        self._sequence = 0

    def create(
        self,
        orchestration_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeTransactionOrchestration:
        orchestration_id = self._validate_text("orchestration_id", orchestration_id)
        if orchestration_id in self._orchestrations:
            raise RuntimeTransactionOrchestrationRejected(
                f"runtime transaction orchestration already exists: {orchestration_id!r}"
            )

        self._sequence += 1
        orchestration = RuntimeTransactionOrchestration(
            orchestration_id=orchestration_id,
            status="created",
            items=[],
            results=[],
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            committed=False,
            rolled_back=False,
        )
        self._orchestrations[orchestration_id] = orchestration
        return self._copy_orchestration(orchestration)

    def add_transaction(
        self,
        orchestration_id: str,
        transaction_id: str,
        steps: list[dict[str, Any]] | None = None,
    ) -> RuntimeTransactionOrchestrationItem:
        orchestration = self._require_orchestration(orchestration_id)
        self._require_status(orchestration, {"created"}, "add transaction")
        transaction_id = self._validate_text("transaction_id", transaction_id)
        if any(item.transaction_id == transaction_id for item in orchestration.items):
            raise RuntimeTransactionOrchestrationRejected(
                f"runtime transaction orchestration duplicate transaction_id: {transaction_id!r}"
            )

        steps = [] if steps is None else steps
        try:
            self.transaction_manager.begin(transaction_id)
            for step in steps:
                self.transaction_manager.add_step(
                    transaction_id,
                    step.get("operation"),
                    runtime_args=step.get("runtime_args"),
                    payload=step.get("payload"),
                    metadata=step.get("metadata"),
                )
        except Exception as exc:
            raise RuntimeTransactionOrchestrationRejected(
                "runtime transaction orchestration add transaction failed",
                original_exception=exc,
            ) from exc

        item = RuntimeTransactionOrchestrationItem(
            orchestration_id=orchestration.orchestration_id,
            transaction_id=transaction_id,
            steps=steps,
            status="pending",
            result=None,
            sequence=len(orchestration.items) + 1,
        )
        orchestration.items.append(item)
        return self._copy_item(item)

    def run(
        self,
        orchestration_id: str,
        handler: Callable[[RuntimeTransactionOrchestrationItem, Any], Any] | None = None,
    ) -> RuntimeTransactionOrchestration:
        orchestration = self._require_orchestration(orchestration_id)
        self._require_status(orchestration, {"created"}, "run")

        orchestration.status = "running"
        for index, item in enumerate(orchestration.items):
            try:
                item.status = "running"
                transaction_result = self.transaction_manager.run(item.transaction_id)
                item.result = (
                    handler(self._copy_item(item), transaction_result)
                    if handler is not None
                    else transaction_result
                )
                item.status = "completed"
                orchestration.results.append(item.result)
            except Exception as exc:
                item.status = "failed"
                orchestration.status = "failed"
                for remaining in orchestration.items[index + 1 :]:
                    if remaining.status == "pending":
                        remaining.status = "skipped"
                raise RuntimeTransactionOrchestrationRejected(
                    "runtime transaction orchestration run failed",
                    original_exception=exc,
                ) from exc

        orchestration.status = "completed"
        return self._copy_orchestration(orchestration)

    def commit(self, orchestration_id: str) -> RuntimeTransactionOrchestration:
        orchestration = self._require_orchestration(orchestration_id)
        self._require_status(orchestration, {"completed"}, "commit")

        try:
            for item in orchestration.items:
                self.transaction_manager.commit(item.transaction_id)
                item.status = "committed"
        except Exception as exc:
            raise RuntimeTransactionOrchestrationRejected(
                "runtime transaction orchestration commit failed",
                original_exception=exc,
            ) from exc

        orchestration.status = "committed"
        orchestration.committed = True
        return self._copy_orchestration(orchestration)

    def rollback(
        self,
        orchestration_id: str,
        reason: Any = None,
    ) -> RuntimeTransactionOrchestration:
        orchestration = self._require_orchestration(orchestration_id)
        if orchestration.status == "committed":
            raise RuntimeTransactionOrchestrationRejected(
                "runtime transaction orchestration cannot rollback committed orchestration"
            )
        self._require_status(
            orchestration,
            {"created", "running", "completed", "failed"},
            "rollback",
        )

        try:
            for item in orchestration.items:
                if item.status != "committed":
                    self.transaction_manager.rollback(item.transaction_id, reason)
                    item.status = "rolled_back"
        except Exception as exc:
            raise RuntimeTransactionOrchestrationRejected(
                "runtime transaction orchestration rollback failed",
                original_exception=exc,
            ) from exc

        orchestration.status = "rolled_back"
        orchestration.rolled_back = True
        return self._copy_orchestration(orchestration)

    def get(self, orchestration_id: str) -> RuntimeTransactionOrchestration:
        return self._copy_orchestration(self._require_orchestration(orchestration_id))

    def list_all(self) -> list[RuntimeTransactionOrchestration]:
        return [
            self._copy_orchestration(orchestration)
            for orchestration in self._orchestrations.values()
        ]

    def clear(self) -> None:
        self._orchestrations.clear()
        self._sequence = 0

    def _require_orchestration(
        self,
        orchestration_id: str,
    ) -> RuntimeTransactionOrchestration:
        orchestration_id = self._validate_text("orchestration_id", orchestration_id)
        orchestration = self._orchestrations.get(orchestration_id)
        if orchestration is None:
            raise RuntimeTransactionOrchestrationRejected(
                f"runtime transaction orchestration unknown: {orchestration_id!r}"
            )

        return orchestration

    def _require_status(
        self,
        orchestration: RuntimeTransactionOrchestration,
        allowed: set[str],
        action: str,
    ) -> None:
        if orchestration.status not in _ORCHESTRATION_STATUSES:
            raise RuntimeTransactionOrchestrationRejected(
                f"runtime transaction orchestration invalid status: {orchestration.status!r}"
            )
        if orchestration.status not in allowed:
            raise RuntimeTransactionOrchestrationRejected(
                "runtime transaction orchestration cannot "
                f"{action} while status is {orchestration.status!r}"
            )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeTransactionOrchestrationRejected(
                f"runtime transaction orchestration {field_name} is required"
            )

        return value

    def _copy_orchestration(
        self,
        orchestration: RuntimeTransactionOrchestration,
    ) -> RuntimeTransactionOrchestration:
        return replace(
            orchestration,
            items=[self._copy_item(item) for item in orchestration.items],
            results=list(orchestration.results),
        )

    def _copy_item(
        self,
        item: RuntimeTransactionOrchestrationItem,
    ) -> RuntimeTransactionOrchestrationItem:
        if item.status not in _ITEM_STATUSES:
            raise RuntimeTransactionOrchestrationRejected(
                f"runtime transaction orchestration invalid item status: {item.status!r}"
            )

        return replace(item)
