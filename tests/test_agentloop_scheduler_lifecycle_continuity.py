from __future__ import annotations

import copy
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.runtime.operator_integration_bridge import OperatorIntegrationBridge
from core.runtime.operator_session import OPERATOR_SESSION_COMPLETED, OPERATOR_SESSION_RESUMABLE
from core.runtime.operator_session_bootstrap import OperatorSessionBootstrap
from core.runtime.persistent_operator import PersistentOperatorRuntime
from core.runtime.runtime_recovery_executor import RuntimeRecoveryExecutor
from core.runtime.runtime_replay_engine import RuntimeReplayEngine
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runtime import TaskRuntime
from core.tasks.scheduler import Scheduler


class FakePlanner:
    def plan(self, **kwargs):
        return {
            "ok": True,
            "planner_mode": "fake_agentloop_scheduler_lifecycle",
            "intent": "task",
            "steps": [
                {"id": "agent-step-1", "type": "run_python", "code": "print(1)", "max_attempts": 1},
                {
                    "id": "agent-step-2",
                    "type": "run_python",
                    "code": "print(2)",
                    "max_attempts": 1,
                    "force_fail": True,
                },
                {"id": "agent-step-3", "type": "run_python", "code": "print(3)", "max_attempts": 1},
            ],
            "final_answer": "",
        }


class OneStepPlanner:
    def plan(self, **kwargs):
        return {
            "ok": True,
            "planner_mode": "fake_agentloop_scheduler_lifecycle_no_operator",
            "intent": "task",
            "steps": [
                {
                    "id": "agent-step-no-operator",
                    "type": "run_python",
                    "code": "print('ok')",
                    "max_attempts": 1,
                },
            ],
            "final_answer": "",
        }


def _success_handler(step, task=None, context=None, previous_result=None):
    return {
        "ok": True,
        "message": f"{step.get('id')} completed",
        "final_answer": f"{step.get('id')} completed",
        "evidence_refs": [f"evidence:{step.get('id')}:completed"],
        "result": {"seen_operator_session_id": (context or {}).get("operator_session_id")},
    }


def _flaky_handler(step, task=None, context=None, previous_result=None):
    if step.get("force_fail"):
        return {
            "ok": False,
            "message": f"{step.get('id')} failed once",
            "final_answer": f"{step.get('id')} failed once",
            "evidence_refs": [f"evidence:{step.get('id')}:failed"],
            "error": {
                "type": "transient_error",
                "message": f"{step.get('id')} failed once",
                "retryable": True,
            },
            "result": {"seen_operator_session_id": (context or {}).get("operator_session_id")},
        }
    return _success_handler(step, task=task, context=context, previous_result=previous_result)


def _execution_authority(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "step_id": "agentloop-scheduler-lifecycle",
        "authority_source": "agent_loop_test",
        "execution_authority_endpoint": "step_executor",
        "runtime_session": f"runtime-session:{task_id}",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "source": "test"},
        "trace_id": f"trace:{task_id}",
        "authority_status": "allowed",
        "action_type": "execute_or_mutation",
    }


def _make_stack(tmp_path: Path):
    operator_runtime = PersistentOperatorRuntime()
    bridge = OperatorIntegrationBridge(operator_runtime)
    bootstrap = OperatorSessionBootstrap(operator_bridge=bridge)

    task_runtime = TaskRuntime(workspace_root=str(tmp_path), operator_bridge=bridge)
    step_executor = StepExecutor(workspace_root=str(tmp_path), operator_bridge=bridge)
    step_executor.register_handler("run_python", _flaky_handler)

    scheduler = Scheduler(
        workspace_dir=str(tmp_path),
        task_runtime=task_runtime,
        step_executor=step_executor,
        debug=False,
    )
    agent = AgentLoop(
        planner=FakePlanner(),
        scheduler=scheduler,
        task_runtime=task_runtime,
        step_executor=step_executor,
        operator_session_bootstrap=bootstrap,
        debug=False,
    )
    scheduler.agent_loop = agent
    return operator_runtime, bridge, bootstrap, task_runtime, step_executor, scheduler, agent


def _latest_task_from_response(response: dict) -> dict:
    task = response.get("task")
    assert isinstance(task, dict)
    return task


def _repo_task(scheduler: Scheduler, task_id: str) -> dict:
    task = scheduler._get_task_from_repo(task_id)
    assert isinstance(task, dict)
    return task


def _set_step_force_fail(task: dict, step_id: str, force_fail: bool) -> dict:
    updated = copy.deepcopy(task)
    for step in updated.get("steps", []):
        if isinstance(step, dict) and step.get("id") == step_id:
            if force_fail:
                step["force_fail"] = True
            else:
                step.pop("force_fail", None)
    return updated


def _continue_after_governed_boundary(task: dict) -> dict:
    updated = copy.deepcopy(task)
    updated["status"] = "queued"
    updated["next_action"] = "run_next_tick"
    updated["blocked_reason"] = ""
    updated["waiting_reason"] = ""
    updated["requires_review"] = False
    updated["review_status"] = ""
    updated["blockers"] = []
    updated["active_blocker_count"] = 0
    return updated


def test_agentloop_scheduler_runner_runtime_operator_lifecycle_survives_resume_reload_and_complete(tmp_path):
    operator_runtime, bridge, bootstrap, task_runtime, step_executor, scheduler, agent = _make_stack(tmp_path)

    start = agent._run_task_mode(
        context={"enable_operator_session": True},
        user_input="run lifecycle continuity task",
        route={"mode": "task", "execution_authority": _execution_authority("agentloop-lifecycle")},
    )
    assert start["ok"] is True
    created_task = _latest_task_from_response(start)
    task_id = created_task["task_id"]
    session_id = created_task["operator_session_id"]

    assert session_id
    assert start["context"]["operator_session_id"] == session_id
    assert created_task["metadata"]["operator_session_id"] == session_id
    assert operator_runtime.get_session(session_id) is not None

    scheduler_task = _repo_task(scheduler, task_id)

    first_result = scheduler.run_one_step(task=scheduler_task, current_tick=1)
    assert first_result["runtime_state"]["operator_session_id"] == session_id
    assert first_result["ok"] is True
    assert first_result["runtime_state"]["status"] != "finished"

    blocked_session = operator_runtime.get_session(session_id)
    assert blocked_session is not None
    assert blocked_session.status != OPERATOR_SESSION_RESUMABLE
    assert blocked_session.status != OPERATOR_SESSION_COMPLETED
    assert blocked_session.completed_steps == ["agent-step-1"]
    assert operator_runtime.get_session_checkpoints(session_id)
    resume_payload = RuntimeRecoveryExecutor(operator_bridge=bridge).recovery_resume_payload(session_id)
    assert resume_payload["status"] == "running"
    assert resume_payload["completed_steps"] == ["agent-step-1"]
    replay_refs = RuntimeReplayEngine(operator_bridge=bridge).replay_evidence_refs(session_id)
    flattened = [ref for checkpoint_ref in replay_refs for ref in checkpoint_ref["evidence_refs"]]
    assert "evidence:agent-step-1:completed" in flattened


def test_agentloop_scheduler_no_operator_path_and_missing_session_are_safe(tmp_path):
    task_runtime = TaskRuntime(workspace_root=str(tmp_path))
    step_executor = StepExecutor(workspace_root=str(tmp_path))
    step_executor.register_handler("run_python", _success_handler)
    scheduler = Scheduler(
        workspace_dir=str(tmp_path),
        task_runtime=task_runtime,
        step_executor=step_executor,
        debug=False,
    )
    agent = AgentLoop(
        planner=OneStepPlanner(),
        scheduler=scheduler,
        task_runtime=task_runtime,
        step_executor=step_executor,
        debug=False,
    )
    scheduler.agent_loop = agent

    start = agent._run_task_mode(
        context={},
        user_input="run no operator lifecycle task",
        route={"mode": "task", "execution_authority": _execution_authority("agentloop-no-operator")},
    )
    assert start["ok"] is True
    assert "operator_session_id" not in _latest_task_from_response(start)

    result = scheduler.run_one_step(task=_latest_task_from_response(start), current_tick=1)
    assert result["ok"] is True
    assert result["runtime_state"]["status"] in {"finished", "completed"}

    bridge = OperatorIntegrationBridge(PersistentOperatorRuntime())
    assert RuntimeRecoveryExecutor(operator_bridge=bridge).recovery_resume_payload("missing-session") is None
    assert RuntimeReplayEngine(operator_bridge=bridge).replay_evidence_refs("missing-session") == []


def test_agentloop_and_scheduler_do_not_own_operator_persistence_state():
    scheduler_source = Path("core/tasks/scheduler.py").read_text(encoding="utf-8")
    for token in (
        "PersistentOperatorRuntime",
        "OperatorIntegrationBridge",
        "OperatorSessionBootstrap",
        "save_to_dir",
        "load_from_dir",
        "record_checkpoint",
        "mark_step_completed",
        "mark_step_failed",
        "operator.checkpoint",
        "operator.session",
    ):
        assert token not in scheduler_source

    agent_source = Path("core/agent/agent_loop.py").read_text(encoding="utf-8")
    for token in (
        "record_checkpoint(",
        "mark_step_completed(",
        "mark_step_failed(",
        "save_to_dir(",
        "load_from_dir(",
        "checkpoint_id =",
        "checkpoints[",
        "PersistentOperatorRuntime(",
    ):
        assert token not in agent_source
