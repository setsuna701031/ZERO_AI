from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from core.tasks.scheduler import Scheduler
import pytest

pytestmark = [pytest.mark.contract]




REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = REPO_ROOT / "core" / "tasks" / "scheduler.py"


def _tree() -> ast.AST:
    return ast.parse(SCHEDULER_PATH.read_text(encoding="utf-8-sig"), filename=str(SCHEDULER_PATH))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _owner(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return "<module>"


def _assert_path(path: dict[str, Any]) -> None:
    assert path["direct_execution"] is False
    assert path["scheduler_owns_execution"] is False
    assert path["runtime_dispatcher_required"] is True
    assert path["taskrunner_required"] is True
    assert path["step_executor_endpoint_only"] is True
    assert path["authority_path"] == "Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor"


def test_scheduler_formal_path_has_no_direct_step_executor_calls() -> None:
    tree = _tree()
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    direct_calls: list[str] = []
    constructors: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        owner = _owner(node, parents)
        if name in {"execute_step", "execute_steps", "_run_one_step"}:
            direct_calls.append(f"{owner}:{node.lineno}:{name}")
        if name == "StepExecutor":
            constructors.append(f"{owner}:{node.lineno}")

    assert direct_calls == []
    assert len(constructors) == 1
    assert constructors[0].startswith("__init__:")


def test_scheduler_direct_execution_true_is_not_introduced() -> None:
    source = SCHEDULER_PATH.read_text(encoding="utf-8-sig")

    assert '"direct_execution": True' not in source
    assert "'direct_execution': True" not in source


def test_scheduler_side_effect_reaches_endpoint_through_taskrunner(tmp_path: Path) -> None:
    endpoint = _RecordingEndpoint()
    scheduler = Scheduler(workspace_dir=str(tmp_path), step_executor=endpoint, allow_commands=True)

    result = scheduler._execute_simple_step(
        task={
            "task_id": "scheduler-boundary",
            "authority_propagation_required": True,
            "execution_authority": _execution_authority(),
        },
        step={"type": "write_file", "path": "workspace/shared/sealed.txt", "content": "sealed"},
    )

    assert endpoint.calls
    assert endpoint.calls[0]["context"]["authority_context"]["authority_layer"] == "task_runner"
    assert [item["layer"] for item in endpoint.calls[0]["context"]["authority_context"]["authority_chain"]] == [
        "scheduler",
        "runtime_dispatcher",
        "task_runner",
    ]
    _assert_path(result["execution_path"])


def test_scheduler_payload_exposes_runtime_dispatcher_authority_path(tmp_path: Path) -> None:
    scheduler = Scheduler(workspace_dir=str(tmp_path), step_executor=_RecordingEndpoint())

    result = scheduler.run_one_step({"task_id": "terminal", "status": "finished", "steps": []})

    _assert_path(result["execution_path"])


def test_scheduler_legacy_compatibility_wrappers_delegate_to_taskrunner() -> None:
    tree = _tree()
    legacy_wrappers = {
        "_zero_v702_scheduler_execute_simple_step",
        "_zero_v7335_scheduler_execute_simple_step_no_direct_mutation",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in legacy_wrappers:
            calls = {_call_name(call) for call in ast.walk(node) if isinstance(call, ast.Call)}
            assert "_run_step_via_task_runner" in calls
            assert not ({"StepExecutor", "execute_step", "execute_steps"} & calls)


def test_uninitialized_scheduler_diagnostic_bridge_is_explicitly_non_formal() -> None:
    source = SCHEDULER_PATH.read_text(encoding="utf-8-sig")

    assert '"legacy_bridge"] = True' in source
    assert '"diagnostic_only"] = True' in source
    assert '"formal_execution_path"] = False' in source


class _RecordingEndpoint:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_step(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ok": True, "source": "step_executor"}


def _execution_authority() -> dict[str, Any]:
    return {
        "authority_source": "human_review",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "mutation",
        "ownership_source": "human_review",
        "authority_scope": "step_executor_side_effect",
    }
