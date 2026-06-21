from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.runtime_execution_authority import propagate_runtime_capability
from core.goals.goal_lineage_contract import (
    attach_goal_lineage,
    attach_runtime_identity_graph,
    bind_runtime_identity_graph,
    create_root_goal_lineage,
    extract_goal_lineage,
)


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def agent_execution_path() -> dict[str, Any]:
    return {
        "direct_execution": False,
        "agent_loop_owns_execution": False,
        "runtime_owns_execution": True,
        "taskrunner_required": True,
        "step_executor_endpoint_only": True,
        "authority_path": "AgentLoop -> Runtime -> TaskRunner -> StepExecutor",
    }


def _execution_authority_from_sources(*sources: Any) -> dict[str, Any]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        authority = source.get("execution_authority")
        if isinstance(authority, dict) and authority:
            return copy.deepcopy(authority)
        for key in ("authority_context", "runtime_authority_context"):
            authority_context = source.get(key)
            if not isinstance(authority_context, dict):
                continue
            authority = authority_context.get("execution_authority")
            if isinstance(authority, dict) and authority:
                return copy.deepcopy(authority)
    return {}


def _runtime_task_execution_authority(
    *,
    boundary_id: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    steps_fingerprint = _fingerprint(steps)
    return {
        "task_id": boundary_id,
        "step_id": f"{boundary_id}:steps:{steps_fingerprint}",
        "authority_source": "runtime_step_executor",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "runtime_execution",
        "ownership_source": "core.runtime.agent_execution_runtime",
        "authority_scope": "agent_execution_runtime_task",
        "runtime_session": boundary_id,
        "approval_state": "approved",
        "policy_result": {
            "allowed": True,
            "decision": "allow",
            "source": "core.runtime.agent_execution_runtime",
            "reason": "runtime_owner_task_admission",
        },
        "trace_id": f"trace:{boundary_id}:{steps_fingerprint}",
        "provenance": {
            "issued_by": "core.runtime.agent_execution_runtime.AgentExecutionRuntime",
            "execution_owner": "runtime",
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
            "steps_fingerprint": steps_fingerprint,
        },
    }


def _endpoint_result_from_taskrunner_record(record: dict[str, Any]) -> dict[str, Any]:
    taskrunner_result = record.get("result")
    if not isinstance(taskrunner_result, dict):
        return {}
    endpoint_result = taskrunner_result.get("result")
    if isinstance(endpoint_result, dict):
        return copy.deepcopy(endpoint_result)
    return copy.deepcopy(taskrunner_result)


class _RuntimeStepExecutorEndpoint:
    def __init__(self, endpoint: Any) -> None:
        self.endpoint = endpoint

    def execute_step(self, **kwargs: Any) -> dict[str, Any]:
        task = kwargs.get("task") if isinstance(kwargs.get("task"), dict) else {}
        runtime_context = task.get("agent_runtime_context") if isinstance(task.get("agent_runtime_context"), dict) else {}
        if runtime_context:
            kwargs = copy.deepcopy(kwargs)
            context = kwargs.get("context") if isinstance(kwargs.get("context"), dict) else {}
            delegated_authority = (
                context.get("authority_context")
                if isinstance(context.get("authority_context"), dict)
                else {}
            )
            kwargs["context"] = {**copy.deepcopy(runtime_context), **copy.deepcopy(context)}
            if delegated_authority:
                kwargs["context"]["authority_context"] = copy.deepcopy(delegated_authority)
                kwargs["context"]["runtime_authority_context"] = copy.deepcopy(delegated_authority)
        for method_name in ("execute_step", "execute"):
            method = getattr(self.endpoint, method_name, None)
            if not callable(method):
                continue
            try:
                result = method(**kwargs)
            except TypeError:
                result = method(
                    step=copy.deepcopy(kwargs.get("step")),
                    task=copy.deepcopy(kwargs.get("task")),
                    context=copy.deepcopy(kwargs.get("context")),
                )
            return result if isinstance(result, dict) else {"ok": True, "result": copy.deepcopy(result)}
        return {"ok": False, "error": "runtime step executor endpoint unavailable"}


class AgentExecutionRuntime:
    """Runtime-owned AgentLoop execution boundary."""

    def __init__(
        self,
        *,
        task_runner: Any = None,
        step_executor: Any = None,
        task_runtime: Any = None,
        workspace_root: str | Path = "workspace",
        replanner: Any = None,
        verifier: Any = None,
        debug: bool = False,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.endpoint = step_executor
        if task_runner is not None:
            self.task_runner = task_runner
        else:
            runtime_endpoint = step_executor or StepExecutor(workspace_root=str(self.workspace_root))
            endpoint = _RuntimeStepExecutorEndpoint(runtime_endpoint)
            self.task_runner = TaskRunner(
                task_runtime=task_runtime or TaskRuntime(workspace_root=str(self.workspace_root), debug=debug),
                step_executor=endpoint,
                replanner=replanner,
                verifier=verifier,
                debug=debug,
            )

    @property
    def has_endpoint(self) -> bool:
        return self.task_runner is not None

    def run_task(self, task: dict[str, Any], *, current_tick: int = 0, **kwargs: Any) -> dict[str, Any]:
        result = self.task_runner.run_task(task=task, current_tick=current_tick, **kwargs)
        return self._attach_path(result)

    def run_step(
        self,
        *,
        step: dict[str, Any],
        task: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        current_tick: int = 0,
    ) -> dict[str, Any]:
        execution = self.run_steps(
            steps=[step],
            task=task,
            context=context,
            current_tick=current_tick,
        )
        results = execution.get("results") if isinstance(execution.get("results"), list) else []
        if results and isinstance(results[-1], dict):
            result = results[-1].get("result")
            if isinstance(result, dict):
                return self._attach_path(result)
        return self._attach_path(execution)

    def run_steps(
        self,
        *,
        steps: list[dict[str, Any]],
        task: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        current_tick: int = 0,
    ) -> dict[str, Any]:
        source = copy.deepcopy(task) if isinstance(task, dict) else {}
        task_id = str(source.get("task_id") or source.get("id") or "agent-runtime-" + _fingerprint(steps))
        try:
            source_lineage = extract_goal_lineage(
                source, require_complete=True, reject_conflicts=True
            )
        except ValueError:
            source_lineage = create_root_goal_lineage(
                goal_id=str(source.get("goal_id") or task_id),
                session_id=str(source.get("session_id") or "") or None,
                runtime_session_id=str(source.get("runtime_session_id") or "") or None,
            )
        source = attach_goal_lineage(source, source_lineage)
        boundary_id = task_id + "-runtime-" + _fingerprint(
            {
                "steps": steps,
                "tick": current_tick,
                "runtime_session_id": source_lineage["runtime_session_id"],
                "workspace_root": str(self.workspace_root.resolve()),
            }
        )
        package_id = str(source.get("package_id") or source.get("work_package_id") or f"{boundary_id}:package")
        session_id = str(source.get("session_id") or source.get("runtime_session") or boundary_id)
        task_dir = self.workspace_root / "agent_execution_runtime" / boundary_id
        runtime_context = copy.deepcopy(context or {})
        execution_authority = _execution_authority_from_sources(source, runtime_context)
        if not execution_authority:
            execution_authority = _runtime_task_execution_authority(
                boundary_id=boundary_id,
                steps=steps,
            )
        runtime_execution_capability = RuntimeDispatcher._execution_capability(
            {
                "task_id": boundary_id,
                "package_id": package_id,
                "session_id": session_id,
            }
        )
        identity_task = RuntimeDispatcher._attach_execution_identity(
            {
                **source,
                "task_id": boundary_id,
                "package_id": package_id,
                "session_id": source_lineage["session_id"],
            }
        )
        provenance = RuntimeDispatcher._capability_provenance(identity_task)
        propagated = propagate_runtime_capability({}, provenance, stage="dispatcher")
        identity_graph = bind_runtime_identity_graph(
            identity_task["runtime_identity_graph"], capability_id=provenance.capability_id
        )
        authority_context = {
            "authority_phase": "runtime_task_handoff",
            "authority_layer": "runtime",
            "authority_role": "runtime_owner",
            "authority_source": "runtime_dispatcher",
            "authority_policy": "owner_issued_runtime_execution_capability",
            "authority_propagation_required": True,
            "execution_authority_granted": True,
            "can_execute_privileged_step": True,
            "escalated": False,
            "execution_authority": copy.deepcopy(execution_authority),
            "runtime_execution_capability": runtime_execution_capability,
            "runtime_identity_graph": identity_graph,
            **propagated,
            "authority_chain": [
                {
                    "layer": "runtime_dispatcher",
                    "authority_role": "runtime_owner",
                    "execution_authority_granted": True,
                    "can_execute_privileged_step": True,
                }
            ],
        }
        runtime_task = {
            **source,
            "id": boundary_id,
            "task_id": boundary_id,
            "task_name": boundary_id,
            "package_id": package_id,
            "session_id": session_id,
            "status": "queued",
            "task_dir": str(task_dir),
            "runtime_state_file": str(task_dir / "runtime_state.json"),
            "steps": copy.deepcopy(steps),
            "current_step_index": 0,
            "results": [],
            "step_results": [],
            "execution_log": [],
            "execution_trace": [],
            "max_auto_ticks": max(1, len(steps)),
            "agent_runtime_context": runtime_context,
            "execution_authority": copy.deepcopy(execution_authority),
            "runtime_execution_capability": runtime_execution_capability,
            "runtime_identity_graph": identity_graph,
            **propagated,
            "authority_context": copy.deepcopy(authority_context),
            "runtime_authority_context": copy.deepcopy(authority_context),
            "authority_propagation_required": True,
        }
        runtime_task = attach_goal_lineage(runtime_task, source_lineage)
        runtime_task = attach_runtime_identity_graph(runtime_task, identity_graph)
        runner_result = self.run_task(runtime_task, current_tick=current_tick)
        runtime_state = runner_result.get("runtime_state") if isinstance(runner_result.get("runtime_state"), dict) else {}
        records = runtime_state.get("results") if isinstance(runtime_state.get("results"), list) else []
        results = [
            {
                "step_index": int(record.get("step_index", index) or index) + 1,
                "step": copy.deepcopy(record.get("step") or {}),
                "result": _endpoint_result_from_taskrunner_record(record),
            }
            for index, record in enumerate(records)
            if isinstance(record, dict)
        ]
        last_result = copy.deepcopy(results[-1]["result"]) if results else {}
        result_message = str(
            last_result.get("message")
            or last_result.get("final_answer")
            or runner_result.get("message")
            or ""
        )
        return self._attach_path(
            {
                "ok": bool(runner_result.get("ok")),
                "status": str(runner_result.get("status") or runtime_state.get("status") or ""),
                "results": results,
                "last_result": last_result,
                "execution_trace": copy.deepcopy(runtime_state.get("execution_trace") or []),
                "steps_executed": len(results),
                "completed_steps": sum(1 for item in results if bool(item["result"].get("ok"))),
                "message": result_message,
                "final_answer": str(runner_result.get("final_answer") or runtime_state.get("final_answer") or ""),
                "error": copy.deepcopy(runner_result.get("error")),
            }
        )

    def execute(self, *, step: dict[str, Any], context: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        return self.run_step(
            step=step,
            task=kwargs.get("task") if isinstance(kwargs.get("task"), dict) else {},
            context=context,
            current_tick=int(kwargs.get("step_index") or 0),
        )

    @staticmethod
    def _attach_path(payload: Any) -> dict[str, Any]:
        result = copy.deepcopy(payload) if isinstance(payload, dict) else {"ok": False, "raw_result": payload}
        path = result.get("execution_path") if isinstance(result.get("execution_path"), dict) else {}
        path.update(agent_execution_path())
        result["execution_path"] = path
        return result


__all__ = ["AgentExecutionRuntime", "agent_execution_path"]
