from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from core.runtime.runtime_execution_planner import RuntimeExecutionPlanner
from core.runtime.runtime_transaction_orchestrator import RuntimeTransactionOrchestrator


@dataclass
class RuntimePlanExecution:
    execution_id: str
    plan_id: str
    orchestration_id: str
    plan: Any
    orchestration: Any
    status: str
    payload: Any
    metadata: Any
    sequence: int
    committed: bool
    rolled_back: bool
    operations: Any = None


class RuntimePlanExecutionRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimePlanExecutor:
    def __init__(
        self,
        planner: RuntimeExecutionPlanner | None = None,
        orchestrator: RuntimeTransactionOrchestrator | None = None,
    ) -> None:
        self.planner = planner if planner is not None else RuntimeExecutionPlanner()
        self.orchestrator = (
            orchestrator
            if orchestrator is not None
            else RuntimeTransactionOrchestrator()
        )
        self._executions: dict[str, RuntimePlanExecution] = {}
        self._sequence = 0

    def execute_plan(
        self,
        execution_id: str,
        plan_id: str,
        operations: list[dict[str, Any]],
        payload: Any = None,
        metadata: Any = None,
        handler: Any = None,
    ) -> RuntimePlanExecution:
        execution_id = self._validate_text("execution_id", execution_id)
        plan_id = self._validate_text("plan_id", plan_id)
        if execution_id in self._executions:
            raise RuntimePlanExecutionRejected(
                f"runtime plan execution already exists: {execution_id!r}"
            )

        orchestration_id = f"{execution_id}:orchestration"
        plan = None
        orchestration = None
        execution = None

        try:
            plan = self.planner.create_plan(plan_id, operations, payload, metadata)
            self.orchestrator.create(orchestration_id, payload, metadata)
            for transaction in sorted(plan.transactions, key=lambda item: item.sequence):
                steps = [
                    {
                        "operation": step.operation,
                        "runtime_args": step.runtime_args,
                        "payload": step.payload,
                        "metadata": step.metadata,
                    }
                    for step in sorted(transaction.steps, key=lambda item: item.sequence)
                ]
                self.orchestrator.add_transaction(
                    orchestration_id,
                    transaction.transaction_id,
                    steps=steps,
                )
            orchestration = self.orchestrator.run(orchestration_id, handler=handler)

            execution = self._record_execution(
                execution_id=execution_id,
                plan_id=plan_id,
                orchestration_id=orchestration_id,
                plan=plan,
                orchestration=orchestration,
                status="completed",
                payload=payload,
                metadata=metadata,
                committed=False,
                rolled_back=False,
                operations=operations,
            )
            return self._copy_execution(execution)
        except Exception as exc:
            if execution is None:
                execution = self._record_execution(
                    execution_id=execution_id,
                    plan_id=plan_id,
                    orchestration_id=orchestration_id,
                    plan=plan,
                    orchestration=orchestration,
                    status="failed",
                    payload=payload,
                    metadata=metadata,
                    committed=False,
                    rolled_back=False,
                    operations=operations,
                )
            else:
                execution.status = "failed"
            raise RuntimePlanExecutionRejected(
                "runtime plan execution failed",
                original_exception=exc,
            ) from exc

    def commit_execution(self, execution_id: str) -> RuntimePlanExecution:
        execution = self._require_execution(execution_id)
        if execution.status != "completed":
            raise RuntimePlanExecutionRejected(
                "runtime plan execution commit requires completed status"
            )

        try:
            orchestration = self.orchestrator.commit(execution.orchestration_id)
        except Exception as exc:
            raise RuntimePlanExecutionRejected(
                "runtime plan execution commit failed",
                original_exception=exc,
            ) from exc

        execution.orchestration = orchestration
        execution.status = "committed"
        execution.committed = True
        return self._copy_execution(execution)

    def rollback_execution(
        self,
        execution_id: str,
        reason: Any = None,
    ) -> RuntimePlanExecution:
        execution = self._require_execution(execution_id)
        if execution.status == "committed":
            raise RuntimePlanExecutionRejected(
                "runtime plan execution cannot rollback committed execution"
            )
        if execution.status not in {"completed", "failed"}:
            raise RuntimePlanExecutionRejected(
                "runtime plan execution rollback requires completed or failed status"
            )

        try:
            orchestration = self.orchestrator.rollback(
                execution.orchestration_id,
                reason=reason,
            )
        except Exception as exc:
            raise RuntimePlanExecutionRejected(
                "runtime plan execution rollback failed",
                original_exception=exc,
            ) from exc

        execution.orchestration = orchestration
        execution.status = "rolled_back"
        execution.rolled_back = True
        return self._copy_execution(execution)

    def get_execution(self, execution_id: str) -> RuntimePlanExecution:
        return self._copy_execution(self._require_execution(execution_id))

    def list_executions(self) -> list[RuntimePlanExecution]:
        return [
            self._copy_execution(execution)
            for execution in self._executions.values()
        ]

    def clear(self) -> None:
        self._executions.clear()
        self._sequence = 0

    def _record_execution(
        self,
        execution_id: str,
        plan_id: str,
        orchestration_id: str,
        plan: Any,
        orchestration: Any,
        status: str,
        payload: Any,
        metadata: Any,
        committed: bool,
        rolled_back: bool,
        operations: Any,
    ) -> RuntimePlanExecution:
        self._sequence += 1
        execution = RuntimePlanExecution(
            execution_id=execution_id,
            plan_id=plan_id,
            orchestration_id=orchestration_id,
            plan=plan,
            orchestration=orchestration,
            status=status,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            committed=committed,
            rolled_back=rolled_back,
            operations=operations,
        )
        self._executions[execution_id] = execution
        return execution

    def _require_execution(self, execution_id: str) -> RuntimePlanExecution:
        execution_id = self._validate_text("execution_id", execution_id)
        execution = self._executions.get(execution_id)
        if execution is None:
            raise RuntimePlanExecutionRejected(
                f"runtime plan execution unknown: {execution_id!r}"
            )

        return execution

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimePlanExecutionRejected(
                f"runtime plan execution {field_name} is required"
            )

        return value

    def _copy_execution(self, execution: RuntimePlanExecution) -> RuntimePlanExecution:
        return replace(execution)
