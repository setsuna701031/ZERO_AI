from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.governed_engineering_batch import attach_governed_engineering_transaction_batch
from core.runtime.runtime_plan_graph import (
    build_runtime_mutation_plan_graph,
    serialize_plan_graph,
    topological_node_order,
)
from core.runtime.runtime_plan_verifier import (
    collect_verification_edges,
    verify_plan_graph_shape,
    write_plan_graph_journal,
)


SCHEMA_RUNTIME_PLAN_EXECUTION = "zero.aer.runtime_plan_execution.v1"


class RuntimePlanExecutionRejected(RuntimeError):
    """Raised when a runtime plan execution cannot be accepted or completed."""

    def __init__(self, message: str, *, original_exception: BaseException | None = None) -> None:
        super().__init__(message)
        self.original_exception = original_exception


@dataclass
class RuntimePlanExecution:
    execution_id: str
    plan_id: str
    operations: List[Dict[str, Any]]
    payload: Dict[str, Any] | None
    metadata: Dict[str, Any] | None
    sequence: int
    status: str
    orchestration_id: str
    planner_plan: Any = None
    orchestration_result: Any = None
    transaction_results: List[Any] | None = None
    run_result: Any = None
    commit_result: Any = None
    rollback_result: Any = None
    committed: bool = False
    rolled_back: bool = False
    ok: bool = True
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


class RuntimePlanExecutor:
    """Execute planner-created runtime transaction plans through an orchestrator."""

    def __init__(self, *, planner: Any, orchestrator: Any) -> None:
        self.planner = planner
        self.orchestrator = orchestrator
        self._executions: Dict[str, RuntimePlanExecution] = {}
        self._sequence = 0

    def execute_plan(
        self,
        execution_id: str,
        plan_id: str,
        operations: List[Dict[str, Any]],
        *,
        payload: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> RuntimePlanExecution:
        execution_id = str(execution_id or "").strip()
        plan_id = str(plan_id or "").strip()

        if not execution_id:
            raise RuntimePlanExecutionRejected("execution_id is required")
        if not plan_id:
            raise RuntimePlanExecutionRejected("plan_id is required")
        if execution_id in self._executions:
            raise RuntimePlanExecutionRejected(f"duplicate execution_id: {execution_id}")
        if not isinstance(operations, list):
            raise RuntimePlanExecutionRejected("operations must be a list")

        operations_for_planner = copy.deepcopy(operations)
        payload_for_planner = copy.deepcopy(payload) if isinstance(payload, dict) else payload
        metadata_for_planner = copy.deepcopy(metadata) if isinstance(metadata, dict) else metadata

        self._sequence += 1
        now = time.time()
        orchestration_id = f"{execution_id}:orchestration"
        execution = RuntimePlanExecution(
            execution_id=execution_id,
            plan_id=plan_id,
            operations=operations,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            status="running",
            orchestration_id=orchestration_id,
            transaction_results=[],
            created_at=now,
            updated_at=now,
        )
        self._executions[execution_id] = copy.deepcopy(execution)

        try:
            planner_plan = self.planner.create_plan(
                plan_id,
                operations_for_planner,
                payload=payload_for_planner,
                metadata=metadata_for_planner,
            )
            execution.planner_plan = planner_plan

            execution.orchestration_result = self.orchestrator.create(
                orchestration_id,
                payload=copy.deepcopy(payload) if isinstance(payload, dict) else payload,
                metadata=copy.deepcopy(metadata) if isinstance(metadata, dict) else metadata,
            )

            transaction_results: List[Any] = []
            for transaction in list(getattr(planner_plan, "transactions", []) or []):
                transaction_id = str(getattr(transaction, "transaction_id", "") or "").strip()
                if not transaction_id:
                    raise RuntimePlanExecutionRejected("planner transaction_id is required")

                steps_payload = [
                    {
                        "operation": getattr(step, "operation", None),
                        "runtime_args": copy.deepcopy(getattr(step, "runtime_args", None)),
                        "payload": copy.deepcopy(getattr(step, "payload", None)),
                        "metadata": copy.deepcopy(getattr(step, "metadata", None)),
                        "sequence": getattr(step, "sequence", None),
                    }
                    for step in list(getattr(transaction, "steps", []) or [])
                ]

                transaction_results.append(
                    self.orchestrator.add_transaction(
                        orchestration_id,
                        transaction_id,
                        steps=steps_payload,
                    )
                )

            execution.transaction_results = transaction_results
            execution.run_result = self.orchestrator.run(orchestration_id)
            execution.status = "completed"
            execution.ok = True
            execution.updated_at = time.time()
            self._executions[execution_id] = copy.deepcopy(execution)
            return execution

        except RuntimePlanExecutionRejected as exc:
            execution.status = "failed"
            execution.ok = False
            execution.error = str(exc)
            execution.updated_at = time.time()
            self._executions[execution_id] = copy.deepcopy(execution)
            raise

        except Exception as exc:
            execution.status = "failed"
            execution.ok = False
            execution.error = f"{exc.__class__.__name__}: {exc}"
            execution.updated_at = time.time()
            self._executions[execution_id] = copy.deepcopy(execution)
            raise RuntimePlanExecutionRejected(
                execution.error,
                original_exception=exc,
            ) from exc

    def commit_execution(self, execution_id: str) -> RuntimePlanExecution:
        execution = self._require_execution(execution_id)
        if execution.status != "completed":
            raise RuntimePlanExecutionRejected(
                f"execution must be completed before commit: {execution.status}"
            )

        execution.commit_result = self.orchestrator.commit(execution.orchestration_id)
        execution.status = "committed"
        execution.committed = True
        execution.updated_at = time.time()
        self._executions[execution.execution_id] = copy.deepcopy(execution)
        return copy.deepcopy(execution)

    def rollback_execution(self, execution_id: str, reason: str | None = None) -> RuntimePlanExecution:
        execution = self._require_execution(execution_id)
        if execution.status == "committed":
            raise RuntimePlanExecutionRejected("committed execution cannot be rolled back")
        if execution.status not in {"completed", "failed"}:
            raise RuntimePlanExecutionRejected(
                f"execution cannot be rolled back from status: {execution.status}"
            )

        execution.rollback_result = self.orchestrator.rollback(
            execution.orchestration_id,
            reason=reason,
        )
        execution.status = "rolled_back"
        execution.rolled_back = True
        execution.updated_at = time.time()
        self._executions[execution.execution_id] = copy.deepcopy(execution)
        return copy.deepcopy(execution)

    def get_execution(self, execution_id: str) -> RuntimePlanExecution:
        return copy.deepcopy(self._require_execution(execution_id))

    def list_executions(self) -> List[RuntimePlanExecution]:
        return [copy.deepcopy(item) for item in self._executions.values()]

    def clear(self) -> None:
        self._executions.clear()
        self._sequence = 0

    def _require_execution(self, execution_id: str) -> RuntimePlanExecution:
        key = str(execution_id or "").strip()
        execution = self._executions.get(key)
        if execution is None:
            raise RuntimePlanExecutionRejected(f"unknown execution_id: {key}")
        return copy.deepcopy(execution)


def execute_runtime_mutation_plan_graph(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
    targets: Any = None,
    force_verification_failure: bool = False,
) -> Dict[str, Any]:
    graph = build_runtime_mutation_plan_graph(
        repo_root=repo_root,
        task_id=task_id,
        goal=goal,
        targets=targets,
        force_verification_failure=force_verification_failure,
    )
    graph_payload = serialize_plan_graph(graph)
    shape_verification = verify_plan_graph_shape(graph_payload)
    verification_edges = collect_verification_edges(graph_payload)
    ordered_nodes = topological_node_order(graph)

    plan_dir = repo_root / "workspace" / "runtime_plan_graphs" / graph.plan_id
    plan_journal_path = plan_dir / "runtime_plan_graph_journal.json"

    execution_records: List[Dict[str, Any]] = []
    batch_result: Dict[str, Any] = {}

    for node in ordered_nodes:
        node_record: Dict[str, Any] = {
            "node_id": node.node_id,
            "node_type": node.node_type,
            "description": node.description,
            "targets": node.targets,
            "started_at": time.time(),
            "finished_at": None,
            "status": "skipped",
            "ok": True,
        }

        if node.node_type == "stage":
            node_record["status"] = "completed"
            node_record["verification"] = {
                "ok": True,
                "checks": list(node.verification),
            }
        elif node.node_type == "mutation_batch":
            intermediate_result: Dict[str, Any] = {}
            intermediate_result = attach_governed_engineering_transaction_batch(
                repo_root=repo_root,
                task=task,
                result=intermediate_result,
                task_id=task_id,
                goal=goal,
                targets=node.targets,
                force_verification_failure=node.force_verification_failure,
            )
            batch_result = intermediate_result.get("governed_engineering_transaction_batch", {})
            node_record["status"] = str(batch_result.get("status") or "unknown")
            node_record["ok"] = bool(batch_result.get("ok"))
            node_record["batch_id"] = batch_result.get("batch_id")
            node_record["journal_path"] = batch_result.get("journal_path")
            node_record["rollback_applied"] = bool((batch_result.get("rollback") or {}).get("rollback_applied"))
            node_record["transaction"] = batch_result
        elif node.node_type == "rollback":
            rollback = batch_result.get("rollback") if isinstance(batch_result, dict) else {}
            node_record["status"] = "available"
            node_record["ok"] = bool(rollback.get("rollback_available", True)) if isinstance(rollback, dict) else True
            node_record["rollback"] = rollback
        else:
            node_record["status"] = "unknown"
            node_record["ok"] = False

        node_record["finished_at"] = time.time()
        execution_records.append(node_record)

        if node.node_type == "mutation_batch" and not bool(node_record.get("ok")):
            continue

    plan_ok = bool(shape_verification.get("ok")) and bool(batch_result.get("ok"))
    rollback_applied = bool((batch_result.get("rollback") or {}).get("rollback_applied")) if isinstance(batch_result, dict) else False

    plan_record = {
        "ok": plan_ok,
        "schema": "zero.aer.runtime_mutation_plan_graph_execution.v1",
        "plan_id": graph.plan_id,
        "task_id": task_id,
        "goal": goal,
        "status": "committed" if plan_ok else "rolled_back",
        "created_at": graph.created_at,
        "finished_at": time.time(),
        "graph": graph_payload,
        "shape_verification": shape_verification,
        "verification_edges": verification_edges,
        "execution_order": [node.node_id for node in ordered_nodes],
        "execution_records": execution_records,
        "batch_result": batch_result,
        "rollback_applied": rollback_applied,
        "journal_path": str(plan_journal_path),
        "plan_dir": str(plan_dir),
        "execution_authority_endpoint": "step_executor",
        "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
        "boundary": {
            "planner_outputs_plan_graph": True,
            "dependency_ordering_enforced": True,
            "verification_edges_recorded": True,
            "batch_execution_uses_governed_engineering_transaction": True,
            "rollback_strategy_recorded": True,
            "cli_is_not_execution_owner": True,
            "thin_bridge_is_compatibility_layer": True,
            "no_hidden_mutation_shortcut": True,
        },
    }

    write_plan_graph_journal(plan_journal_path, plan_record)

    result["runtime_mutation_plan_graph"] = plan_record
    result["runtime_mutation_plan_graph_schema"] = plan_record["schema"]
    result["runtime_mutation_plan_graph_id"] = plan_record["plan_id"]
    result["runtime_mutation_plan_graph_status"] = plan_record["status"]
    result["runtime_mutation_plan_graph_ok"] = plan_record["ok"]
    result["runtime_mutation_plan_graph_journal_path"] = plan_record["journal_path"]
    result["runtime_mutation_plan_graph_rollback_applied"] = rollback_applied

    task["runtime_mutation_plan_graph"] = plan_record
    task["runtime_mutation_plan_graph_schema"] = plan_record["schema"]
    task["runtime_mutation_plan_graph_id"] = plan_record["plan_id"]
    task["runtime_mutation_plan_graph_status"] = plan_record["status"]
    task["runtime_mutation_plan_graph_ok"] = plan_record["ok"]
    task["runtime_mutation_plan_graph_journal_path"] = plan_record["journal_path"]
    task["runtime_mutation_plan_graph_rollback_applied"] = rollback_applied

    return result


__all__ = [
    "RuntimePlanExecution",
    "RuntimePlanExecutionRejected",
    "RuntimePlanExecutor",
    "execute_runtime_mutation_plan_graph",
]
