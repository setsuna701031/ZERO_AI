from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any

from core.runtime.runtime_operation_registry import RuntimeOperationRegistry


@dataclass
class RuntimeExecutionPlanStep:
    transaction_id: str
    operation: str
    runtime_args: Any
    payload: Any
    metadata: Any
    operation_metadata: dict[str, Any]
    sequence: int


@dataclass
class RuntimeExecutionPlanTransaction:
    plan_id: str
    transaction_id: str
    steps: list[RuntimeExecutionPlanStep]
    payload: Any
    metadata: Any
    sequence: int


@dataclass
class RuntimeExecutionPlan:
    plan_id: str
    status: str
    transactions: list[RuntimeExecutionPlanTransaction]
    payload: Any
    metadata: Any
    sequence: int


class RuntimeExecutionPlanRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeExecutionPlanner:
    def __init__(
        self,
        operation_registry: RuntimeOperationRegistry | None = None,
    ) -> None:
        self.operation_registry = (
            operation_registry
            if operation_registry is not None
            else RuntimeOperationRegistry()
        )
        self._plans: dict[str, RuntimeExecutionPlan] = {}
        self._sequence = 0

    def create_plan(
        self,
        plan_id: str,
        operations: list[dict[str, Any]],
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionPlan:
        plan_id = self._validate_text("plan_id", plan_id)
        if plan_id in self._plans:
            raise RuntimeExecutionPlanRejected(
                f"runtime execution plan already exists: {plan_id!r}"
            )
        if not operations:
            raise RuntimeExecutionPlanRejected(
                "runtime execution plan operations are required"
            )

        transactions_by_id: dict[str, RuntimeExecutionPlanTransaction] = {}
        transactions: list[RuntimeExecutionPlanTransaction] = []
        default_transaction_id = f"{plan_id}:tx:1"

        for operation_request in operations:
            operation = self._validate_text(
                "operation",
                operation_request.get("operation"),
            )
            transaction_id = (
                operation_request.get("transaction_id")
                or default_transaction_id
            )

            try:
                registered = self.operation_registry.get(operation)
            except Exception as exc:
                raise RuntimeExecutionPlanRejected(
                    "runtime execution plan operation lookup failed",
                    original_exception=exc,
                ) from exc

            transaction = transactions_by_id.get(transaction_id)
            if transaction is None:
                transaction = RuntimeExecutionPlanTransaction(
                    plan_id=plan_id,
                    transaction_id=transaction_id,
                    steps=[],
                    payload=payload,
                    metadata=metadata,
                    sequence=len(transactions) + 1,
                )
                transactions_by_id[transaction_id] = transaction
                transactions.append(transaction)

            step = RuntimeExecutionPlanStep(
                transaction_id=transaction_id,
                operation=operation,
                runtime_args=operation_request.get("runtime_args"),
                payload=operation_request.get("payload"),
                metadata=operation_request.get("metadata"),
                operation_metadata=self._operation_metadata(registered),
                sequence=len(transaction.steps) + 1,
            )
            transaction.steps.append(step)

        self._sequence += 1
        plan = RuntimeExecutionPlan(
            plan_id=plan_id,
            status="planned",
            transactions=transactions,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
        )
        self._plans[plan_id] = plan
        return self._copy_plan(plan)

    def get_plan(self, plan_id: str) -> RuntimeExecutionPlan:
        plan_id = self._validate_text("plan_id", plan_id)
        plan = self._plans.get(plan_id)
        if plan is None:
            raise RuntimeExecutionPlanRejected(
                f"runtime execution plan unknown: {plan_id!r}"
            )

        return self._copy_plan(plan)

    def list_plans(self) -> list[RuntimeExecutionPlan]:
        return [self._copy_plan(plan) for plan in self._plans.values()]

    def clear(self) -> None:
        self._plans.clear()
        self._sequence = 0

    def _operation_metadata(self, registered: Any) -> dict[str, Any]:
        return {
            "operation": registered.operation,
            "target": registered.target,
            "action": registered.action,
            "category": registered.category,
            "risk_level": registered.risk_level,
            "governance_target": registered.governance_target,
            "description": registered.description,
            "metadata": copy.deepcopy(registered.metadata),
            "sequence": registered.sequence,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeExecutionPlanRejected(
                f"runtime execution plan {field_name} is required"
            )

        return value

    def _copy_plan(self, plan: RuntimeExecutionPlan) -> RuntimeExecutionPlan:
        return replace(
            plan,
            transactions=[
                self._copy_transaction(transaction)
                for transaction in plan.transactions
            ],
        )

    def _copy_transaction(
        self,
        transaction: RuntimeExecutionPlanTransaction,
    ) -> RuntimeExecutionPlanTransaction:
        return replace(
            transaction,
            steps=[self._copy_step(step) for step in transaction.steps],
        )

    def _copy_step(self, step: RuntimeExecutionPlanStep) -> RuntimeExecutionPlanStep:
        return replace(
            step,
            operation_metadata=copy.deepcopy(step.operation_metadata),
        )
