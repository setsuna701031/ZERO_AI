from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any, Iterable

from core.runtime.runtime_operation_registry import RuntimeOperationRegistry


def _norm(path: Any) -> str:
    text = str(path or "").replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def _is_under(path: str, root: str) -> bool:
    path = _norm(path)
    root = _norm(root)

    if not root:
        return True

    return path == root or path.startswith(root + "/")


def _normalize_allow_paths(
    allow_paths: Iterable[str] | None = None,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            _norm(path)
            for path in (allow_paths or ())
            if _norm(path)
        )
    )


def _extract_target_paths(operation_request: dict[str, Any]) -> list[str]:
    paths: list[str] = []

    for key in (
        "target_file",
        "target_path",
    ):
        value = operation_request.get(key)
        if value:
            paths.append(_norm(value))

    for key in (
        "target_files",
        "target_paths",
        "affected_files",
        "impacted_files",
    ):
        value = operation_request.get(key)

        if not value:
            continue

        if isinstance(value, str):
            paths.append(_norm(value))
            continue

        try:
            for item in value:
                normalized = _norm(item)
                if normalized:
                    paths.append(normalized)
        except TypeError:
            normalized = _norm(value)
            if normalized:
                paths.append(normalized)

    runtime_args = operation_request.get("runtime_args")
    if isinstance(runtime_args, dict):
        for key in (
            "target_file",
            "target_path",
        ):
            value = runtime_args.get(key)
            if value:
                paths.append(_norm(value))

    return sorted(set(path for path in paths if path))


def _paths_allowed(
    target_paths: Iterable[str],
    allow_paths: Iterable[str] | None = None,
) -> bool:
    normalized_allow = _normalize_allow_paths(allow_paths)

    if not normalized_allow:
        return True

    for path in target_paths:
        normalized = _norm(path)

        if not any(
            _is_under(normalized, root)
            for root in normalized_allow
        ):
            return False

    return True


@dataclass
class RuntimeExecutionPlanStep:
    transaction_id: str
    operation: str
    runtime_args: Any
    payload: Any
    metadata: Any
    operation_metadata: dict[str, Any]
    sequence: int
    target_paths: list[str]


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
    allow_paths: list[str]


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
        allow_paths: Iterable[str] | None = None,
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

        normalized_allow = _normalize_allow_paths(allow_paths)

        transactions_by_id: dict[
            str,
            RuntimeExecutionPlanTransaction,
        ] = {}

        transactions: list[
            RuntimeExecutionPlanTransaction
        ] = []

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

            target_paths = _extract_target_paths(
                operation_request,
            )

            if not _paths_allowed(
                target_paths,
                normalized_allow,
            ):
                raise RuntimeExecutionPlanRejected(
                    "runtime execution plan target path "
                    "outside allow_paths boundary"
                )

            try:
                registered = self.operation_registry.get(
                    operation,
                )
            except Exception as exc:
                raise RuntimeExecutionPlanRejected(
                    "runtime execution plan operation lookup failed",
                    original_exception=exc,
                ) from exc

            transaction = transactions_by_id.get(
                transaction_id,
            )

            if transaction is None:
                transaction = RuntimeExecutionPlanTransaction(
                    plan_id=plan_id,
                    transaction_id=transaction_id,
                    steps=[],
                    payload=payload,
                    metadata=metadata,
                    sequence=len(transactions) + 1,
                )

                transactions_by_id[
                    transaction_id
                ] = transaction

                transactions.append(transaction)

            step = RuntimeExecutionPlanStep(
                transaction_id=transaction_id,
                operation=operation,
                runtime_args=operation_request.get(
                    "runtime_args"
                ),
                payload=operation_request.get("payload"),
                metadata=operation_request.get("metadata"),
                operation_metadata=self._operation_metadata(
                    registered
                ),
                sequence=len(transaction.steps) + 1,
                target_paths=target_paths,
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
            allow_paths=list(normalized_allow),
        )

        self._plans[plan_id] = plan

        return self._copy_plan(plan)

    def get_plan(
        self,
        plan_id: str,
    ) -> RuntimeExecutionPlan:
        plan_id = self._validate_text(
            "plan_id",
            plan_id,
        )

        plan = self._plans.get(plan_id)

        if plan is None:
            raise RuntimeExecutionPlanRejected(
                f"runtime execution plan unknown: {plan_id!r}"
            )

        return self._copy_plan(plan)

    def list_plans(
        self,
    ) -> list[RuntimeExecutionPlan]:
        return [
            self._copy_plan(plan)
            for plan in self._plans.values()
        ]

    def clear(self) -> None:
        self._plans.clear()
        self._sequence = 0

    def _operation_metadata(
        self,
        registered: Any,
    ) -> dict[str, Any]:
        return {
            "operation": registered.operation,
            "target": registered.target,
            "action": registered.action,
            "category": registered.category,
            "risk_level": registered.risk_level,
            "governance_target": registered.governance_target,
            "description": registered.description,
            "metadata": copy.deepcopy(
                registered.metadata
            ),
            "sequence": registered.sequence,
        }

    def _validate_text(
        self,
        field_name: str,
        value: str,
    ) -> str:
        if not str(value or "").strip():
            raise RuntimeExecutionPlanRejected(
                f"runtime execution plan "
                f"{field_name} is required"
            )

        return value

    def _copy_plan(
        self,
        plan: RuntimeExecutionPlan,
    ) -> RuntimeExecutionPlan:
        return replace(
            plan,
            transactions=[
                self._copy_transaction(transaction)
                for transaction in plan.transactions
            ],
            allow_paths=list(plan.allow_paths),
        )

    def _copy_transaction(
        self,
        transaction: RuntimeExecutionPlanTransaction,
    ) -> RuntimeExecutionPlanTransaction:
        return replace(
            transaction,
            steps=[
                self._copy_step(step)
                for step in transaction.steps
            ],
        )

    def _copy_step(
        self,
        step: RuntimeExecutionPlanStep,
    ) -> RuntimeExecutionPlanStep:
        return replace(
            step,
            operation_metadata=copy.deepcopy(
                step.operation_metadata
            ),
            target_paths=list(step.target_paths),
        )