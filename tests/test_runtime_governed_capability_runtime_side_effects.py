import ast
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import urllib.request

from core.runtime.runtime_governed_capability_runtime import run_governed_capability_runtime
from tests.test_runtime_governed_capability_runtime import completed_input


def test_production_boundary_has_no_executor_or_mutating_imports():
    path = Path("core/runtime/runtime_governed_capability_runtime.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    forbidden = {"core.runtime.runtime_transactional_active_execution", "subprocess", "requests", "urllib", "socket", "openai"}
    assert not imported & forbidden
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls & {"write_text", "write_bytes", "unlink", "rename", "replace", "mkdir", "rmdir"}


def _snapshot(root):
    result = []
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result.append((relative, "directory", None, None))
        else:
            data = path.read_bytes()
            result.append((relative, "file", data, hashlib.sha256(data).hexdigest()))
    return result


def test_all_dangerous_boundaries_are_guarded_and_workspace_unchanged(monkeypatch, tmp_path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"unchanged")
    value = completed_input(tmp_path)
    before = _snapshot(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("dangerous boundary called")

    import core.runtime.runtime_transactional_active_execution as transactional
    import core.runtime.controlled_mutation_bridge as mutation
    import core.runtime.repair_transaction_execution_bridge as committed
    import core.runtime.runtime_autonomous_loop as autonomous
    import core.system.llm_client as model_client
    monkeypatch.setattr(transactional, "execute_transactional_active_plan", forbidden)
    monkeypatch.setattr(mutation, "execute_controlled_mutation_transaction", forbidden)
    monkeypatch.setattr(committed, "execute_committed_runtime_repair_transaction", forbidden)
    monkeypatch.setattr(autonomous, "project_runtime_scheduler", forbidden)
    monkeypatch.setattr(autonomous, "project_runtime_worker", forbidden)
    monkeypatch.setattr(autonomous, "project_runtime_mission", forbidden)
    monkeypatch.setattr(model_client.LocalLLMClient, "chat_with_model", forbidden)
    monkeypatch.setattr(model_client.LocalLLMClient, "generate_with_model", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(os, "popen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    for name in ("write_text", "write_bytes", "unlink", "rename", "replace", "mkdir", "rmdir"):
        monkeypatch.setattr(Path, name, forbidden)

    result = run_governed_capability_runtime(value)
    assert result["runtime_state"]["runtime_status"] == "prepared"
    assert _snapshot(tmp_path) == before
    assert not any(p.name.lower() in {"runtime_state.json", "temp", "workspace", "snapshot", "journal", "backup"}
                   for p in tmp_path.rglob("*"))
