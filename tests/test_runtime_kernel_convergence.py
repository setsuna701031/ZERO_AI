from __future__ import annotations

from core.planning.planner_contract import normalize_planner_payload
from core.tasks.execution_gateway_runtime import run_scheduler_execution_gateway
from core.tasks.scheduler import Scheduler


class ConvergenceExecutor:
    def execute(self, step):
        step_type = step.get("type")

        if step_type == "write_file":
            return {
                "ok": True,
                "action": "write_file",
                "target_path": step.get("target_path"),
                "content_length": len(step.get("content") or ""),
            }

        if step_type == "command":
            return {
                "ok": True,
                "action": "command",
                "command": step.get("command"),
            }

        if step_type == "verify":
            return {
                "ok": True,
                "action": "verify",
                "target_path": step.get("target_path"),
            }

        return {
            "ok": True,
            "action": step_type or "noop",
        }


def _planner_payload_to_step(payload):
    normalized = normalize_planner_payload(payload)
    assert normalized.ok is True

    scheduler = Scheduler.__new__(Scheduler)
    plan = scheduler._normalize_external_plan(normalized.payload)

    assert plan is not None
    assert plan["steps"]

    return plan["steps"][0]


def test_runtime_kernel_convergence_write_file_flow():
    step = _planner_payload_to_step(
        {
            "action": "write_file",
            "target_path": "workspace/shared/convergence.txt",
            "content": "hello convergence",
            "goal": "write convergence file",
        }
    )

    runtime_result = run_scheduler_execution_gateway(
        ConvergenceExecutor(),
        step,
        trace=False,
    )

    assert runtime_result.ok is True
    assert runtime_result.used_gateway is True
    assert runtime_result.step["type"] == "write_file"
    assert runtime_result.step["target_path"] == "workspace/shared/convergence.txt"
    assert runtime_result.result["action"] == "write_file"
    assert runtime_result.result["content_length"] == len("hello convergence")


def test_runtime_kernel_convergence_command_flow():
    step = _planner_payload_to_step(
        {
            "action": "run_command",
            "command": "pytest tests -q",
            "goal": "run tests",
        }
    )

    runtime_result = run_scheduler_execution_gateway(
        ConvergenceExecutor(),
        step,
        trace=False,
    )

    assert runtime_result.ok is True
    assert runtime_result.used_gateway is True
    assert runtime_result.step["type"] == "command"
    assert runtime_result.step["command"] == "pytest tests -q"
    assert runtime_result.result["action"] == "command"
    assert runtime_result.result["command"] == "pytest tests -q"


def test_runtime_kernel_convergence_verify_flow():
    step = _planner_payload_to_step(
        {
            "action": "verify_file",
            "target_path": "workspace/shared/result.txt",
            "reason": "ensure file exists",
            "goal": "verify result",
        }
    )

    runtime_result = run_scheduler_execution_gateway(
        ConvergenceExecutor(),
        step,
        trace=False,
    )

    assert runtime_result.ok is True
    assert runtime_result.used_gateway is True
    assert runtime_result.step["type"] == "verify"
    assert runtime_result.step["target_path"] == "workspace/shared/result.txt"
    assert runtime_result.result["action"] == "verify"


def test_runtime_kernel_convergence_rejects_invalid_contract():
    normalized = normalize_planner_payload(
        {
            "action": "write_file",
            "content": "missing path",
            "goal": "broken write",
        }
    )

    assert normalized.ok is False


def test_runtime_kernel_convergence_runtime_rejects_invalid_step():
    runtime_result = run_scheduler_execution_gateway(
        ConvergenceExecutor(),
        {
            "type": "write_file",
            "content": "missing target",
        },
        allow_legacy_fallback=False,
        trace=False,
    )

    assert runtime_result.ok is False
    assert runtime_result.used_gateway is False
    assert runtime_result.result["action"] == "noop"
    assert runtime_result.result["scheduler_execution_runtime_ok"] is False
    assert "write_file:missing_path" in runtime_result.errors