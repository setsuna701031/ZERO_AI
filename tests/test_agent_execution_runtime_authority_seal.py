from __future__ import annotations

from typing import Any

from core.runtime.agent_execution_runtime import AgentExecutionRuntime


def test_runtime_task_handoff_carries_complete_runtime_owner_authority() -> None:
    runner = _RecordingTaskRunner()
    runtime = AgentExecutionRuntime(task_runner=runner)

    result = runtime.run_steps(steps=[{"type": "command", "command": "echo sealed"}])

    task = runner.tasks[0]
    authority = task["execution_authority"]
    assert authority["authority_source"] == "runtime_step_executor"
    assert authority["ownership_source"] == "core.runtime.agent_execution_runtime"
    assert authority["execution_authority_endpoint"] == "step_executor"
    assert authority["action_type"] == "runtime_execution"
    assert authority["task_id"] == task["task_id"]
    assert authority["runtime_session"] == task["task_id"]
    assert authority["approval_state"] == "approved"
    assert authority["policy_result"]["allowed"] is True
    assert authority["trace_id"]
    assert task["authority_propagation_required"] is True
    assert task["authority_context"]["execution_authority"] == authority

    path = result["execution_path"]
    assert path["direct_execution"] is False
    assert path["runtime_owns_execution"] is True
    assert path["taskrunner_required"] is True
    assert path["step_executor_endpoint_only"] is True


def test_runtime_preserves_explicit_upstream_execution_authority() -> None:
    runner = _RecordingTaskRunner()
    runtime = AgentExecutionRuntime(task_runner=runner)
    upstream = {
        "task_id": "upstream-task",
        "step_id": "upstream-step",
        "authority_source": "human_review",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "runtime_execution",
        "runtime_session": "upstream-session",
        "approval_state": "approved",
        "policy_result": {"allowed": True},
        "trace_id": "upstream-trace",
    }

    runtime.run_steps(
        steps=[{"type": "command", "command": "echo sealed"}],
        context={"execution_authority": upstream},
    )

    task = runner.tasks[0]
    assert task["execution_authority"] == upstream
    assert task["authority_context"]["execution_authority"] == upstream


def test_runtime_returns_canonical_endpoint_result_shape() -> None:
    runtime = AgentExecutionRuntime(task_runner=_ResultRecordingTaskRunner())

    result = runtime.run_steps(steps=[{"type": "apply_patch"}])

    assert result["results"][0]["result"] == {
        "ok": True,
        "transaction_ok": True,
        "message": "endpoint result",
    }
    assert result["last_result"]["transaction_ok"] is True
    assert result["message"] == "endpoint result"


class _RecordingTaskRunner:
    def __init__(self) -> None:
        self.tasks: list[dict[str, Any]] = []

    def run_task(self, *, task: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.tasks.append(task)
        return {
            "ok": True,
            "status": "finished",
            "runtime_state": {
                "status": "finished",
                "results": [],
                "execution_trace": [],
            },
        }


class _ResultRecordingTaskRunner(_RecordingTaskRunner):
    def run_task(self, *, task: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        super().run_task(task=task, **kwargs)
        return {
            "ok": True,
            "status": "finished",
            "runtime_state": {
                "status": "finished",
                "results": [
                    {
                        "step_index": 0,
                        "step": {"type": "apply_patch"},
                        "result": {
                            "ok": True,
                            "result": {
                                "ok": True,
                                "transaction_ok": True,
                                "message": "endpoint result",
                            },
                        },
                    }
                ],
                "execution_trace": [],
            },
        }
