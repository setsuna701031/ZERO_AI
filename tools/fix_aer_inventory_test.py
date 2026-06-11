from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "tests" / "test_aer_execution_authority_inventory.py"


TEST_CONTENT = r"""from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = [
    ROOT / "core" / "agent",
    ROOT / "core" / "runtime",
    ROOT / "core" / "tasks",
]

ALLOWED_STEPEXECUTOR_CONSTRUCTORS = {
    "core/runtime/agent_execution_runtime.py",
    "core/tasks/scheduler.py",
}

ALLOWED_EXECUTE_STEP_CALLS = {
    "core/runtime/task_runner.py",
}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if root.exists():
            files.extend(sorted(root.rglob("*.py")))
    return files


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_no_unapproved_stepexecutor_construction() -> None:
    violations: list[str] = []

    for path in _python_files():
        rel = _rel(path)
        tree = ast.parse(_source(path), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "StepExecutor":
                    if rel not in ALLOWED_STEPEXECUTOR_CONSTRUCTORS:
                        violations.append(f"{rel}:{node.lineno}: StepExecutor(...)")

    assert not violations, "\\n".join(violations)


def test_no_unapproved_execute_step_calls() -> None:
    violations: list[str] = []

    for path in _python_files():
        rel = _rel(path)
        tree = ast.parse(_source(path), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"execute_step", "execute_steps"}:
                    if rel not in ALLOWED_EXECUTE_STEP_CALLS:
                        violations.append(f"{rel}:{node.lineno}: .{node.func.attr}(...)")

    assert not violations, "\\n".join(violations)


def test_agent_loop_has_no_legacy_engineering_task_direct_route() -> None:
    source = _source(ROOT / "core" / "agent" / "agent_loop.py")
    forbidden = [
        "AgentLoop -> EngineeringTaskRunner",
        '"legacy_direct_json_engineering_task_runner": True',
        "'legacy_direct_json_engineering_task_runner': True",
        'legacy_direct_json_engineering_task_runner"] = True',
        "legacy_direct_json_engineering_task_runner'] = True",
    ]
    remaining = [item for item in forbidden if item in source]
    assert not remaining, remaining


def test_bridges_do_not_reference_direct_step_executor_execution() -> None:
    bridge_paths = [
        ROOT / "core" / "agent" / "code_chain_controlled_self_edit_bridge.py",
        ROOT / "core" / "runtime" / "controlled_mutation_bridge.py",
    ]
    forbidden = [
        "StepExecutor(",
        ".execute_step(",
        ".execute_steps(",
        "step_executor_from_agent",
        "PlannerStepExecutorAdapter",
    ]

    violations: list[str] = []
    for path in bridge_paths:
        if not path.exists():
            continue
        source = _source(path)
        for item in forbidden:
            if item in source:
                violations.append(f"{_rel(path)} contains {item}")

    assert not violations, "\\n".join(violations)


def test_aer_execution_authority_document_exists() -> None:
    doc = ROOT / "docs" / "architecture" / "aer_execution_authority_seal.md"
    assert doc.exists()

    source = doc.read_text(encoding="utf-8-sig")
    required = [
        "AgentLoop -> AgentExecutionRuntime -> TaskRunner -> StepExecutor",
        "CodeChainControlledSelfEditBridge -> AgentExecutionRuntime -> TaskRunner -> StepExecutor",
        "ControlledMutationBridge -> AgentExecutionRuntime -> TaskRunner -> StepExecutor",
        "Scheduler -> TaskRunner -> StepExecutor",
        "direct_execution=False",
        "runtime_owns_execution=True",
        "taskrunner_required=True",
        "step_executor_endpoint_only=True",
    ]

    missing = [item for item in required if item not in source]
    assert not missing, missing
"""


def main() -> None:
    TEST.parent.mkdir(parents=True, exist_ok=True)
    TEST.write_text(TEST_CONTENT, encoding="utf-8")
    print("rewrote:", TEST)


if __name__ == "__main__":
    main()
