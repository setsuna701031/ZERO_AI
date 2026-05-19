from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATED_SURFACES = (
    REPO_ROOT / "core" / "_archive_candidate" / "flask_manager.py",
    REPO_ROOT / "core" / "capabilities" / "demo_flows.py",
    REPO_ROOT / "core" / "capabilities" / "document_flow_orchestrator.py",
    REPO_ROOT / "core" / "capabilities" / "full_build_flow.py",
    REPO_ROOT / "core" / "persona" / "persona_agent_orchestrator.py",
    REPO_ROOT / "core" / "persona" / "runtime_bridge.py",
    REPO_ROOT / "core" / "repo_sandbox" / "controlled_edit.py",
    REPO_ROOT / "core" / "runtime" / "execution_gateway.py",
    REPO_ROOT / "core" / "runtime" / "step_handlers.py",
    REPO_ROOT / "core" / "runtime" / "step_executor.py",
    REPO_ROOT / "core" / "runtime" / "task_runner.py",
    REPO_ROOT / "core" / "tasks" / "scheduler_core" / "command_step_helpers.py",
    REPO_ROOT / "core" / "tasks" / "simple_step_runner.py",
    REPO_ROOT / "core" / "tools" / "command_tool.py",
    REPO_ROOT / "core" / "tools" / "github_tool.py",
    REPO_ROOT / "core" / "tools" / "readonly_tools.py",
    REPO_ROOT / "core" / "tools" / "_archive_candidate" / "debug_python.py",
    REPO_ROOT / "core" / "tools" / "_archive_candidate" / "run_python_tool.py",
    REPO_ROOT / "core" / "tools" / "_archive_candidate" / "run_shell.py",
    REPO_ROOT / "core" / "tools" / "_archive_candidate" / "terminal_tool.py",
    REPO_ROOT / "core" / "watch" / "auto_task_runner.py",
)


def _call_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    calls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name):
                calls.append(f"{value.id}.{node.func.attr}")
            calls.append(node.func.attr)
        elif isinstance(node.func, ast.Name):
            calls.append(node.func.id)
    return calls


def _has_shell_true(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.keyword):
            continue
        if node.arg == "shell" and isinstance(node.value, ast.Constant):
            if node.value.value is True:
                return True
    return False


def test_migrated_surfaces_do_not_directly_call_subprocess_or_shell_true():
    violations: list[str] = []
    for path in MIGRATED_SURFACES:
        calls = _call_names(path)
        forbidden = {
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.call",
            "subprocess.check_call",
            "subprocess.check_output",
            "os.system",
        }
        found = sorted(set(calls) & forbidden)
        if found:
            violations.append(f"{path.relative_to(REPO_ROOT)}: {found}")
        if _has_shell_true(path):
            violations.append(f"{path.relative_to(REPO_ROOT)}: shell=True")

    assert not violations


def test_only_canonical_executor_calls_subprocess_run_repo_wide():
    violations: list[str] = []
    allowed = REPO_ROOT / "core" / "runtime" / "executor.py"
    for path in (REPO_ROOT / "core").rglob("*.py"):
        if "__pycache__" in path.parts or path == allowed:
            continue
        calls = _call_names(path)
        direct = sorted(
            set(calls)
            & {
                "subprocess.run",
                "subprocess.Popen",
                "subprocess.call",
                "subprocess.check_call",
                "subprocess.check_output",
                "os.system",
            }
        )
        if direct:
            violations.append(f"{path.relative_to(REPO_ROOT)}: {direct}")
        if _has_shell_true(path):
            violations.append(f"{path.relative_to(REPO_ROOT)}: shell=True")

    assert not violations


def test_runtime_execution_request_shape():
    module = importlib.import_module("core.runtime.runtime_execution_request")
    request = module.RuntimeExecutionRequest(
        execution_type="command",
        command="echo hello",
        working_directory=".",
        timeout=5,
        metadata={"shell": True},
        lineage={"request_id": "request-1"},
        replay_id="replay-1",
        repair_session_id="repair-1",
        dry_run=False,
    )

    assert request.execution_type == "command"
    assert request.command == "echo hello"
    assert request.metadata == {"shell": True}
    assert request.lineage == {"request_id": "request-1"}
    assert request.replay_id == "replay-1"
    assert request.repair_session_id == "repair-1"


def test_canonical_executor_command_request_emits_result_and_side_effect(tmp_path):
    request_module = importlib.import_module("core.runtime.runtime_execution_request")
    executor_module = importlib.import_module("core.runtime.executor")
    result_module = importlib.import_module("core.runtime.runtime_execution_result")

    command = f'"{sys.executable}" -c "print(\'owned\')"'
    request = request_module.RuntimeExecutionRequest(
        execution_type="command",
        command=command,
        working_directory=str(tmp_path),
        timeout=20,
        metadata={"shell": True},
        lineage={
            "request_id": "request-1",
            "execution_start_id": "execution_start:request-1",
        },
        replay_id="replay:request-1",
    )

    result = executor_module.Executor(workspace_root=tmp_path).execute_request(request)

    assert isinstance(result, result_module.RuntimeExecutionResult)
    assert result.status == "succeeded"
    assert result.stdout.strip() == "owned"
    assert result.return_code == 0
    assert result.side_effects
    assert result.side_effects[0].effect_type == "command_execution"
    assert result.lineage["request_id"] == "request-1"
    assert result.replay_id == "replay:request-1"


def test_command_tool_routes_through_canonical_gateway(tmp_path):
    module = importlib.import_module("core.tools.command_tool")
    tool = module.CommandTool(workspace_root=tmp_path)

    result = tool.execute(
        {
            "command": f'"{sys.executable}" -c "print(\'tool-owned\')"',
            "timeout": 20,
        }
    )

    assert result["ok"] is True
    assert result["stdout"].strip() == "tool-owned"
    assert result["execution_gateway"]["used"] is True
    assert result["execution_gateway"]["error"] is None
