from __future__ import annotations

import ast
from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy, pytest.mark.integration]




ROOT = Path(__file__).resolve().parents[1]
SCOPED = (
    "core/runtime/execution_authority.py",
    "core/runtime/runtime_execution_authority_gate.py",
    "core/runtime/runtime_execution_authority_policy.py",
    "core/runtime/runtime_native_execution_authority.py",
    "core/runtime/task_runner.py",
    "core/runtime/task_runtime.py",
    "core/runtime/runtime_dispatcher.py",
)


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_scoped_files_have_no_raw_process_execution() -> None:
    violations: list[str] = []
    for path in SCOPED:
        tree = ast.parse(_source(path), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if name in {"subprocess.run", "subprocess.Popen", "os.system", "os.popen"}:
                violations.append(f"{path}:{node.lineno}:{name}")
    assert violations == []


def test_every_scoped_subprocess_gateway_call_has_explicit_gate() -> None:
    for path in ("core/runtime/task_runner.py", "core/runtime/task_runtime.py"):
        source = _source(path)
        assert source.count("safe_subprocess_run(") == source.count("delegated_from")
        assert "enforce_execution_authority(" in source


def test_taskrunner_active_authority_builder_propagates_live_capabilities() -> None:
    source = _source("core/runtime/task_runner.py")
    active_builder = source[source.rfind("def _zero_boundary_build_taskrunner_authority_context"):]
    assert '"runtime_execution_capability": capability' in active_builder
    assert '"runtime_system_capability": system_capability' in active_builder
    assert "delegate_taskrunner_execution_capability(" in active_builder


def test_gate_and_policy_do_not_execute() -> None:
    source = _source("core/runtime/runtime_execution_authority_gate.py") + _source(
        "core/runtime/runtime_execution_authority_policy.py"
    )
    for forbidden in ("safe_subprocess_run(", ".execute_step(", ".execute_steps(", "subprocess.run("):
        assert forbidden not in source
