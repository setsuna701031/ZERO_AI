from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.execution_plan import ExecutionPlan
from core.runtime.runtime_evidence_integration import RuntimeEvidenceEmitter
from core.runtime.runtime_execution_graph import RuntimeExecutionGraph
from core.runtime.runtime_operation import RuntimeOperation
from core.runtime.runtime_transaction import RuntimeTransaction
from core.runtime.scheduler_evidence_adapter import SchedulerEvidenceAdapter
from core.runtime.scheduler_evidence_boundary import SchedulerEvidenceBoundary
from core.runtime.step_executor_evidence_adapter import StepExecutorEvidenceAdapter
from core.runtime.step_executor_evidence_hook import StepExecutorEvidenceHook
from core.runtime.task_runtime_evidence_adapter import TaskRuntimeEvidenceAdapter
from core.runtime.task_runtime_evidence_boundary import TaskRuntimeEvidenceBoundary


class RuntimeMainlineEvidenceSeal:
    def __init__(
        self,
        *,
        seal_id: str,
        scheduler_boundary: SchedulerEvidenceBoundary,
        task_boundary: TaskRuntimeEvidenceBoundary,
        step_hook: StepExecutorEvidenceHook,
        scheduler_adapter: SchedulerEvidenceAdapter,
        task_adapter: TaskRuntimeEvidenceAdapter,
        step_adapter: StepExecutorEvidenceAdapter,
        emitter: RuntimeEvidenceEmitter,
        evidence_records: dict[str, Any],
    ) -> None:
        self.seal_id = self._validate_text("seal_id", seal_id)
        self.scheduler_boundary = scheduler_boundary
        self.task_boundary = task_boundary
        self.step_hook = step_hook
        self.scheduler_adapter = scheduler_adapter
        self.task_adapter = task_adapter
        self.step_adapter = step_adapter
        self.emitter = emitter
        self._evidence_records = copy.deepcopy(evidence_records)

    @property
    def evidence_records(self) -> dict[str, Any]:
        return copy.deepcopy(self._evidence_records)

    @property
    def evidence_refs(self) -> dict[str, str]:
        bundle = self._evidence_records.get("bundle")
        snapshot = self._evidence_records.get("snapshot")
        replay = self._evidence_records.get("replay")
        audit = self._evidence_records.get("audit")
        rollback = self._evidence_records.get("rollback")
        return {
            "seal_id": self.seal_id,
            "bundle_id": getattr(bundle, "bundle_id", ""),
            "snapshot_id": getattr(snapshot, "snapshot_id", ""),
            "replay_id": getattr(replay, "replay_id", ""),
            "audit_id": getattr(audit, "audit_id", ""),
            "rollback_id": getattr(rollback, "rollback_id", ""),
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "seal_id": self.seal_id,
                "emitter_fingerprint": self.emitter.fingerprint,
                "scheduler_adapter_fingerprint": self.scheduler_adapter.fingerprint,
                "task_adapter_fingerprint": self.task_adapter.fingerprint,
                "step_adapter_fingerprint": self.step_adapter.fingerprint,
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise ValueError(f"runtime mainline evidence seal {field_name} is required")
        return str(value)


def build_runtime_mainline_evidence_seal(
    *,
    workspace_root: str,
    seal_id: str = "zero-mainline",
) -> RuntimeMainlineEvidenceSeal:
    scheduler_boundary = SchedulerEvidenceBoundary(f"{seal_id}:scheduler-boundary")
    task_boundary = TaskRuntimeEvidenceBoundary(f"{seal_id}:task-boundary")
    step_hook = StepExecutorEvidenceHook(f"{seal_id}:step-hook")

    scheduler_adapter = SchedulerEvidenceAdapter(
        f"{seal_id}:scheduler-adapter",
        scheduler_boundary,
    )
    task_adapter = TaskRuntimeEvidenceAdapter(
        f"{seal_id}:task-adapter",
        task_boundary,
    )
    step_adapter = StepExecutorEvidenceAdapter(
        f"{seal_id}:step-adapter",
        step_hook,
    )

    emitter = RuntimeEvidenceEmitter(f"{seal_id}:runtime-evidence")
    plan = _build_mainline_execution_plan(
        seal_id=seal_id,
        workspace_root=workspace_root,
    )
    snapshot = emitter.emit_snapshot(plan)
    replay = emitter.emit_replay(snapshot, plan)
    audit = emitter.emit_audit(replay)
    rollback = emitter.emit_rollback(snapshot)
    bundle = emitter.emit_bundle(snapshot, replay, audit, rollback)

    return RuntimeMainlineEvidenceSeal(
        seal_id=seal_id,
        scheduler_boundary=scheduler_boundary,
        task_boundary=task_boundary,
        step_hook=step_hook,
        scheduler_adapter=scheduler_adapter,
        task_adapter=task_adapter,
        step_adapter=step_adapter,
        emitter=emitter,
        evidence_records={
            "snapshot": snapshot,
            "replay": replay,
            "audit": audit,
            "rollback": rollback,
            "bundle": bundle,
        },
    )


def _build_mainline_execution_plan(
    *,
    seal_id: str,
    workspace_root: str,
) -> ExecutionPlan:
    graph = RuntimeExecutionGraph()
    graph.add_node(
        "scheduler.dispatch",
        "scheduler.dispatch",
        runtime_args={"workspace_root": workspace_root},
        metadata={"layer": "scheduler"},
    )
    graph.add_node(
        "task_runtime.lifecycle",
        "task_runtime.lifecycle",
        runtime_args={"workspace_root": workspace_root},
        metadata={"layer": "task_runtime"},
    )
    graph.add_node(
        "step_executor.execute",
        "step_executor.execute",
        runtime_args={"workspace_root": workspace_root},
        metadata={"layer": "step_executor"},
    )
    graph.add_dependency(
        "scheduler.dispatch",
        "task_runtime.lifecycle",
        reason="scheduler hands task to runtime lifecycle",
    )
    graph.add_dependency(
        "task_runtime.lifecycle",
        "step_executor.execute",
        reason="runtime lifecycle advances executable steps",
    )

    transaction = RuntimeTransaction(
        f"{seal_id}:mainline-transaction",
        runtime_args={"workspace_root": workspace_root},
        metadata={"seal": "runtime_mainline_evidence"},
    )
    for operation_id, operation_name, layer in (
        ("scheduler.dispatch", "scheduler.dispatch", "scheduler"),
        ("task_runtime.lifecycle", "task_runtime.lifecycle", "task_runtime"),
        ("step_executor.execute", "step_executor.execute", "step_executor"),
    ):
        operation = RuntimeOperation(
            operation_id=operation_id,
            operation=operation_name,
            runtime_args={"workspace_root": workspace_root},
            metadata={"layer": layer, "seal_id": seal_id},
        )
        operation.start()
        operation.succeed(
            value={"sealed": True},
            metadata={"seal_id": seal_id},
        )
        transaction.add_operation(operation)

    return ExecutionPlan(
        f"{seal_id}:mainline-plan",
        graph,
        transaction,
        runtime_args={"workspace_root": workspace_root},
        metadata={"seal": "runtime_mainline_evidence", "seal_id": seal_id},
    )
