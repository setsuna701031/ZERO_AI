from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from core.runtime.artifact_completion_report import (
    ArtifactCompletionReport,
    build_artifact_completion_report,
)
from core.tasks.task_intake_evidence import export_task_intake_completion_evidence


TASK_INTAKE_CONTRACT_SCHEMA = "task_intake_contract.v1"


class TaskRepositoryProtocol(Protocol):
    def add_task(self, task: dict[str, Any]) -> bool: ...

    def get_task(self, task_id: str) -> dict[str, Any] | None: ...

    def upsert_task(self, task: dict[str, Any]) -> bool: ...


@dataclass(frozen=True)
class TaskIntakeRequest:
    task_id: str
    title: str
    goal: str
    task_type: str = "engineering"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_task_payload(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "goal": self.goal,
            "task_type": self.task_type,
            "status": "queued",
            "history": ["created", "queued"],
            "metadata": {
                **copy.deepcopy(self.metadata),
                "intake_schema": TASK_INTAKE_CONTRACT_SCHEMA,
            },
        }


@dataclass(frozen=True)
class TaskIntakePipelineResult:
    task_id: str
    status: str
    lifecycle: tuple[dict[str, Any], ...]
    task: dict[str, Any]
    plan: dict[str, Any]
    runtime_receipt: dict[str, Any]
    execution_result: dict[str, Any]
    artifacts: tuple[dict[str, Any], ...]
    completion_report: dict[str, Any]
    evidence: dict[str, Any]
    schema: str = TASK_INTAKE_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task_id": self.task_id,
            "status": self.status,
            "lifecycle": copy.deepcopy(list(self.lifecycle)),
            "task": copy.deepcopy(self.task),
            "plan": copy.deepcopy(self.plan),
            "runtime_receipt": copy.deepcopy(self.runtime_receipt),
            "execution_result": copy.deepcopy(self.execution_result),
            "artifacts": copy.deepcopy(list(self.artifacts)),
            "completion_report": copy.deepcopy(self.completion_report),
            "evidence": copy.deepcopy(self.evidence),
        }


def run_task_intake_pipeline(
    *,
    repo_root: Any,
    request: TaskIntakeRequest,
    repository: TaskRepositoryProtocol,
    planner: Any,
    runtime: Any,
    executor: Any,
) -> TaskIntakePipelineResult:
    """Run the intake contract with injected planning/runtime/executor surfaces.

    This function owns intake bookkeeping only. It does not import scheduler,
    agent_loop, runtime authority, execution authority, or the runtime contract
    seal, and it does not construct an executor.
    """
    lifecycle: list[dict[str, Any]] = []
    task = request.to_task_payload()
    _record(lifecycle, "task_created", status="created", task_id=request.task_id)

    repository.add_task(copy.deepcopy(task))
    stored_task = repository.get_task(request.task_id) or copy.deepcopy(task)
    _record(lifecycle, "task_entered_repository", status="queued", task_id=request.task_id)

    plan = _call_planner(planner, stored_task)
    _record(lifecycle, "planner_produced_plan", status="planned", task_id=request.task_id)

    runtime_receipt = _call_runtime(runtime, stored_task, plan)
    _record(lifecycle, "runtime_received_plan", status="accepted", task_id=request.task_id)

    execution_result = _call_executor(executor, stored_task, plan, runtime_receipt)
    _record(lifecycle, "executor_completed", status="executed", task_id=request.task_id)

    artifacts = _artifact_items(execution_result)
    _record(
        lifecycle,
        "artifact_produced",
        status="recorded",
        task_id=request.task_id,
        artifact_count=len(artifacts),
    )

    completion = build_artifact_completion_report(
        task_id=request.task_id,
        status="done",
        lifecycle=lifecycle,
        plan=plan,
        runtime_receipt=runtime_receipt,
        execution_result=execution_result,
        artifacts=artifacts,
        metadata={"task_intake_contract": TASK_INTAKE_CONTRACT_SCHEMA},
    )
    _record(lifecycle, "completion_report_created", status="reported", task_id=request.task_id)
    completion = _refresh_completion_lifecycle(completion, lifecycle)

    evidence = export_task_intake_completion_evidence(
        repo_root=repo_root,
        task_id=request.task_id,
        completion_report=completion,
    )
    _record(lifecycle, "evidence_registered", status="indexed", task_id=request.task_id)
    _record(lifecycle, "task_completed", status="done", task_id=request.task_id)
    completion = _refresh_completion_lifecycle(completion, lifecycle)
    evidence = export_task_intake_completion_evidence(
        repo_root=repo_root,
        task_id=request.task_id,
        completion_report=completion,
    )

    final_task = {
        **copy.deepcopy(stored_task),
        "status": "done",
        "result": {
            "status": "done",
            "artifact_count": len(artifacts),
            "completion_report_path": evidence.get("evidence_path"),
        },
        "artifacts": copy.deepcopy(artifacts),
        "completion_report": {
            "path": evidence.get("evidence_path"),
            "fingerprint": completion.fingerprint,
        },
        "history": _merged_history(stored_task, lifecycle),
    }
    repository.upsert_task(
        final_task,
        completion_authority=execution_result.get("task_completion_authority"),
    )
    final_task = repository.get_task(request.task_id) or final_task

    return TaskIntakePipelineResult(
        task_id=request.task_id,
        status="done",
        lifecycle=tuple(copy.deepcopy(lifecycle)),
        task=copy.deepcopy(final_task),
        plan=copy.deepcopy(plan),
        runtime_receipt=copy.deepcopy(runtime_receipt),
        execution_result=copy.deepcopy(execution_result),
        artifacts=tuple(copy.deepcopy(artifacts)),
        completion_report=completion.to_dict(),
        evidence=copy.deepcopy(evidence),
    )


def _call_planner(planner: Any, task: Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(planner, "plan"):
        result = planner.plan(task=copy.deepcopy(dict(task)))
    elif callable(planner):
        result = planner(copy.deepcopy(dict(task)))
    else:
        raise TypeError("planner must expose plan(task=...) or be callable")
    return _mapping(result, field_name="plan")


def _call_runtime(runtime: Any, task: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(runtime, "receive_plan"):
        result = runtime.receive_plan(
            task=copy.deepcopy(dict(task)),
            plan=copy.deepcopy(dict(plan)),
        )
    elif callable(runtime):
        result = runtime(copy.deepcopy(dict(task)), copy.deepcopy(dict(plan)))
    else:
        raise TypeError("runtime must expose receive_plan(task=..., plan=...) or be callable")
    return _mapping(result, field_name="runtime_receipt")


def _call_executor(
    executor: Any,
    task: Mapping[str, Any],
    plan: Mapping[str, Any],
    runtime_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(executor, "execute"):
        result = executor.execute(
            task=copy.deepcopy(dict(task)),
            plan=copy.deepcopy(dict(plan)),
            runtime_receipt=copy.deepcopy(dict(runtime_receipt)),
        )
    elif callable(executor):
        result = executor(
            copy.deepcopy(dict(task)),
            copy.deepcopy(dict(plan)),
            copy.deepcopy(dict(runtime_receipt)),
        )
    else:
        raise TypeError("executor must expose execute(...) or be callable")
    return _mapping(result, field_name="execution_result")


def _artifact_items(execution_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = execution_result.get("artifacts")
    if not isinstance(raw, list):
        return []
    return [copy.deepcopy(dict(item)) for item in raw if isinstance(item, Mapping)]


def _record(
    lifecycle: list[dict[str, Any]],
    phase: str,
    *,
    status: str,
    task_id: str,
    **extra: Any,
) -> None:
    item = {
        "index": len(lifecycle),
        "task_id": str(task_id or ""),
        "phase": phase,
        "status": status,
    }
    item.update(copy.deepcopy(extra))
    lifecycle.append(item)


def _refresh_completion_lifecycle(
    report: ArtifactCompletionReport,
    lifecycle: list[dict[str, Any]],
) -> ArtifactCompletionReport:
    return build_artifact_completion_report(
        task_id=report.task_id,
        status=report.status,
        lifecycle=lifecycle,
        plan=report.plan,
        runtime_receipt=report.runtime_receipt,
        execution_result=report.execution_result,
        artifacts=report.artifacts,
        metadata=report.metadata,
    )


def _merged_history(task: Mapping[str, Any], lifecycle: list[dict[str, Any]]) -> list[Any]:
    history = copy.deepcopy(task.get("history") if isinstance(task.get("history"), list) else [])
    for event in lifecycle:
        phase = str(event.get("phase") or "")
        if phase and phase not in history:
            history.append(phase)
    return history


def _mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return copy.deepcopy(dict(value))


__all__ = [
    "TASK_INTAKE_CONTRACT_SCHEMA",
    "TaskIntakePipelineResult",
    "TaskIntakeRequest",
    "run_task_intake_pipeline",
]
