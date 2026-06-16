from __future__ import annotations

import ast
from pathlib import Path

from core.runtime.runtime_native_agent_loop import RuntimeNativeAgentLoopRecord
from core.runtime.runtime_native_execution_authority import runtime_native_execution_path
from core.runtime.runtime_native_execution_dispatch import RuntimeDispatchRecord
from core.runtime.runtime_native_mainline import RuntimeNativeMainlineRunResult
from core.runtime.runtime_native_scheduler import RuntimeNativeScheduleItem


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_NATIVE_FILES = [
    REPO_ROOT / "core" / "runtime" / "runtime_native_mainline.py",
    REPO_ROOT / "core" / "runtime" / "runtime_native_agent_loop.py",
    REPO_ROOT / "core" / "runtime" / "runtime_native_execution_dispatch.py",
    REPO_ROOT / "core" / "runtime" / "runtime_native_multisession_coordination.py",
    REPO_ROOT / "core" / "runtime" / "runtime_native_scheduler.py",
]
ALL_RUNTIME_NATIVE_FILES = sorted((REPO_ROOT / "core" / "runtime").glob("runtime_native_*.py"))
DIRECT_EXECUTION_SYMBOLS = {
    "execute_step",
    "execute_steps",
    "run_task_adaptive",
    "_run_one_step",
}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _attribute_path(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _attribute_path(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _method_calls(path: Path, method_name: str, called_name: str) -> list[str]:
    for node in ast.walk(_tree(path)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            return [
                _attribute_path(call.func)
                for call in ast.walk(node)
                if isinstance(call, ast.Call) and _call_name(call) == called_name
            ]
    raise AssertionError(f"{method_name} not found in {path}")


def _assert_execution_path(path: dict, *, delegation_only: bool) -> None:
    assert path["delegation_only"] is delegation_only
    assert path["direct_execution"] is False
    assert path["runtime_owns_execution"] is True
    assert path["taskrunner_required"] is True
    assert path["step_executor_endpoint_only"] is True
    assert path["authority_path"][-2:] == ["TaskRunner", "StepExecutor"]


def test_runtime_native_payloads_expose_sealed_execution_authority() -> None:
    _assert_execution_path(
        RuntimeNativeMainlineRunResult(
            run_id="run",
            status="completed",
            goal="goal",
            runtime_id="runtime",
            source_session_id="session",
        ).to_dict()["execution_path"],
        delegation_only=False,
    )
    _assert_execution_path(
        RuntimeNativeAgentLoopRecord(loop_id="loop", status="completed").to_dict()["execution_path"],
        delegation_only=True,
    )
    _assert_execution_path(
        RuntimeDispatchRecord(
            dispatch_id="dispatch",
            goal="goal",
            source_session_id="session",
        ).to_dict()["execution_path"],
        delegation_only=True,
    )
    _assert_execution_path(
        RuntimeNativeScheduleItem(
            schedule_id="schedule",
            goal="goal",
            source_session_id="session",
        ).to_dict()["execution_path"],
        delegation_only=True,
    )
    _assert_execution_path(
        runtime_native_execution_path(
            entrypoint="runtime_native_multisession_coordination.dispatch_between_nodes",
            delegation_only=True,
        ),
        delegation_only=True,
    )


def test_runtime_native_mainline_run_goal_only_delegates_run_goal_to_runtime_loop() -> None:
    calls = _method_calls(RUNTIME_NATIVE_FILES[0], "run_goal", "run_goal")

    assert calls == ["self.runtime_loop.run_goal"]


def test_runtime_native_execution_dispatch_only_delegates_run_goal_to_mainline() -> None:
    calls = _method_calls(RUNTIME_NATIVE_FILES[2], "run_dispatch", "run_goal")

    assert calls == ["self.mainline.run_goal"]


def test_runtime_native_scheduler_only_delegates_run_goal_to_mainline() -> None:
    calls = _method_calls(RUNTIME_NATIVE_FILES[4], "run_item", "run_goal")

    assert calls == ["self.mainline.run_goal"]


def test_runtime_native_multisession_only_delegates_run_goal_to_mainline() -> None:
    calls = _method_calls(RUNTIME_NATIVE_FILES[3], "dispatch_between_nodes", "run_goal")

    assert calls == ["self.mainline.run_goal"]


def test_no_runtime_native_module_directly_executes_steps_or_constructs_execution_endpoints() -> None:
    violations: list[str] = []

    for path in ALL_RUNTIME_NATIVE_FILES:
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name in DIRECT_EXECUTION_SYMBOLS or name in {"TaskRunner", "StepExecutor"}:
                violations.append(f"{path.name}:{node.lineno}:{name}")

    assert violations == []


def test_aer_runtime_execution_boundary_uses_runtime_dispatcher_handoff() -> None:
    path = REPO_ROOT / "core" / "runtime" / "aer_runtime_integration.py"
    calls = _method_calls(path, "_execute_step", "run_task")
    constructors = _method_calls(path, "_execute_step", "TaskRunner")
    source = path.read_text(encoding="utf-8-sig")

    assert calls == []
    assert constructors == []
    assert '"runtime_dispatcher_required": True' in source
    assert '"runtime_dispatcher_handoff": True' in source
