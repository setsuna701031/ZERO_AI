from __future__ import annotations

from pathlib import Path
from typing import Any


def test_agentloop_forced_repo_edit_is_intent_only_and_does_not_write(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    from core.agent import agent_loop as agent_loop_module
    from core.agent.agent_loop import AgentLoop

    marker = tmp_path / "agentloop-hidden-write.txt"

    def forbidden_repo_edit(*args: Any, **kwargs: Any) -> dict[str, Any]:
        marker.write_text("hidden mutation", encoding="utf-8")
        return {"handled": True, "status": "success", "payload": {}}

    monkeypatch.setattr(agent_loop_module, "run_repo_edit_decision", forbidden_repo_edit)

    result = AgentLoop(debug=False)._try_force_repo_edit_route(
        "replace bad with good in workspace/shared/agentloop_bridge.py"
    )

    assert isinstance(result, dict)
    assert result["mode"] == "forced_repo_edit_intent"
    assert result["execution_intent_only"] is True
    assert result["forced_repo_edit"]["execution_intent_only"] is True
    assert result["execution"]["mutation_executed"] is False
    assert result["plan"]["steps"][0]["type"] == "code_chain_repair"
    assert not marker.exists()


def test_scheduler_create_task_forced_repo_edit_is_intent_only(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    from core.tasks import scheduler as scheduler_module

    marker = tmp_path / "scheduler-hidden-write.txt"

    def forbidden_repo_edit(*args: Any, **kwargs: Any) -> dict[str, Any]:
        marker.write_text("hidden mutation", encoding="utf-8")
        return {"handled": True, "status": "success", "payload": {}}

    monkeypatch.setattr(scheduler_module, "run_repo_edit_decision", forbidden_repo_edit)
    scheduler = _make_scheduler(tmp_path)

    result = scheduler._try_force_repo_edit_at_create_task(
        "replace bad with good in workspace/shared/create_task_bridge.py"
    )

    assert isinstance(result, dict)
    assert result["execution_intent_only"] is True
    assert result["mutation_executed"] is False
    assert result["status"] == scheduler.STATUS_QUEUED
    assert result["planner_result"]["steps"][0]["type"] == "code_chain_repair"
    assert not marker.exists()


def test_create_task_records_forced_repo_edit_as_queued_execution_intent(
    tmp_path: Path,
) -> None:
    scheduler = _make_scheduler(tmp_path)

    task = scheduler._create_task_record(
        "replace bad with good in workspace/shared/create_task_record.py"
    )

    assert task["execution_intent_only"] is True
    assert task["mutation_executed"] is False
    assert task["status"] == scheduler.STATUS_QUEUED
    assert task["current_step_index"] == 0
    assert task["results"] == []
    assert task["last_step_result"] is None
    assert task["planner_result"]["steps"][0]["type"] == "code_chain_repair"
    assert task["authority_context"]["authority_role"] == "orchestration"


def test_code_chain_bridge_delegates_to_step_executor_with_scheduler_context(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()
    scheduler = _make_scheduler(tmp_path, step_executor=recorder)

    result = scheduler._execute_simple_step(
        task={
            "task_id": "task-code-chain-agentloop-bridge",
            "steps": [{"type": "code_chain_repair"}],
            "execution_authority": _execution_authority("mutation"),
            "authority_propagation_required": True,
        },
        step={
            "type": "code_chain_repair",
            "target_path": "workspace/shared/bridge.py",
        },
    )

    assert result["source"] == "step_executor"
    assert recorder.calls[0]["step"]["type"] == "code_chain_repair"
    assert recorder.calls[0]["context"]["authority_context"]["authority_layer"] == "task_runner"
    assert recorder.calls[0]["context"]["authority_context"][
        "execution_authority_granted"
    ] is False


def test_missing_authority_blocks_before_mutation_handler_execution(
    tmp_path: Path,
) -> None:
    from core.runtime.step_executor import StepExecutor

    executor = StepExecutor(workspace_root=str(tmp_path))
    result = executor.execute_step(
        step={
            "type": "write_file",
            "path": "workspace/shared/blocked_by_agentloop_bridge.txt",
            "content": "blocked",
        },
        context={"authority_propagation_required": True},
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["executed"] is False
    assert result["authority_decision"]["decision"] == "denied"
    assert not (tmp_path / "shared" / "blocked_by_agentloop_bridge.txt").exists()


def test_runtime_injected_repair_task_preserves_authority_context() -> None:
    from core.tasks.scheduler_core.repair_injection_execution import (
        normalize_repair_injection_mutation,
    )

    authority_context = {
        "authority_layer": "scheduler",
        "authority_role": "orchestration",
        "execution_authority_granted": False,
        "execution_authority": _execution_authority("mutation"),
    }
    task = {"task_id": "repair-task", "authority_context": authority_context}
    runtime_state = {"authority_context": authority_context}
    repair_context: dict[str, Any] = {}

    mutation = normalize_repair_injection_mutation(
        task=task,
        runtime_state=runtime_state,
        repair_context=repair_context,
        steps=[{"type": "verify"}],
        step_index=0,
        repair_steps=[{"id": "repair-1", "type": "code_chain_repair"}],
        repair_meta={"path": "workspace/shared/repair.py"},
        current_tick=7,
        now="2026-05-25 00:00:00",
    )

    assert mutation["task"]["authority_context"] == authority_context
    assert mutation["runtime_state"]["authority_context"] == authority_context
    assert mutation["repair_context"]["authority_context"] == authority_context


def test_taskrunner_remains_pass_through_only_for_agentloop_bridge(
    tmp_path: Path,
) -> None:
    from core.runtime.task_runner import TaskRunner

    scheduler_context = _make_scheduler(tmp_path)._build_scheduler_authority_context(
        {
            "task_id": "task-agentloop-pass-through",
            "authority_propagation_required": True,
            "execution_authority": _execution_authority("mutation"),
        }
    )
    runner = TaskRunner(step_executor=_RecordingStepExecutor(), debug=False)
    context = runner._build_taskrunner_authority_context(
        task={"task_id": "task-agentloop-pass-through", "authority_context": scheduler_context},
        state={},
        step={"type": "code_chain_repair"},
        upstream_context={},
    )

    assert context["authority_role"] == "propagation"
    assert context["execution_authority_granted"] is False
    assert context["can_execute_privileged_step"] is False
    assert context["execution_authority"] == scheduler_context["execution_authority"]


def _make_scheduler(tmp_path: Path, step_executor: Any | None = None) -> Any:
    from core.tasks.scheduler import Scheduler

    return Scheduler(
        workspace_dir=str(tmp_path),
        step_executor=step_executor,
        allow_commands=True,
        debug=False,
    )


def _execution_authority(action_type: str) -> dict[str, Any]:
    return {
        "authority_source": "human_review",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": action_type,
        "ownership_source": "human_review",
        "authority_scope": "agentloop_createtask_mutation_bridge",
    }


class _RecordingStepExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_step(
        self,
        *,
        step: dict[str, Any],
        task: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "step": step,
                "task": task,
                "context": context,
                "kwargs": kwargs,
            }
        )
        return {
            "ok": True,
            "source": "step_executor",
            "step_type": str(step.get("type") or ""),
            "runtime_execution_result": {
                "metadata": {
                    "execution_endpoint": "step_executor",
                    "authority_decision": {
                        "authority_phase": "pre_execution",
                        "decision": "allowed",
                    },
                }
            },
            "authority_decision": {
                "authority_phase": "pre_execution",
                "authority_required": True,
                "action_type": "mutation",
                "step_type": str(step.get("type") or ""),
                "decision": "allowed",
                "authority_source": "human_review",
                "sealed": False,
                "reason": "explicit_step_executor_authority",
            },
        }
