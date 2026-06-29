from __future__ import annotations

import ast
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.memory.work_package_memory import WorkPackageMemoryError, WorkPackageMemoryStore
from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.runtime.work_package_queue import RuntimePackageQueue
pytestmark = [pytest.mark.integration]




ROOT = Path(__file__).resolve().parents[1]


def _payload(package_id: str, *, target: str = "core/runtime/work_package_queue.py") -> dict:
    return {
        "package_id": package_id,
        "title": "WorkPackage memory closure",
        "goal": f"Repair scheduler memory behavior for {target}",
        "description": "Preserve runtime engineering experience for future planning.",
        "target_files": [target],
        "requirements": ["memory context", "lifecycle evidence"],
        "hard_boundary": ["memory context only"],
        "non_mainline_issue_reporting": ["report drift"],
        "validation_commands": ["python -m pytest tests/test_work_package_memory_closure.py -q"],
        "completion_report_format": ["memory record"],
    }


class _Planner:
    def __init__(self) -> None:
        self.context = {}

    def plan(self, **kwargs):
        self.context = copy.deepcopy(kwargs.get("context") or {})
        return {"ok": True, "steps": [{"id": "inspect", "type": "inspect"}], "meta": {}}


class _Runner:
    def __init__(self, status: str = "finished") -> None:
        self.status = status

    def run_task(self, *, task, current_tick=0, **_kwargs):
        ok = self.status not in {"failed", "blocked"}
        return {
            "ok": ok,
            "status": self.status,
            "current_step_index": current_tick + 1,
            "error": None if ok else f"{self.status}:memory-root-cause",
            "task": {**copy.deepcopy(task), "current_step_index": current_tick + 1},
            "runtime_state": {"status": self.status, "current_step_index": current_tick + 1},
        }


def _operator(tmp_path: Path, *, runner: _Runner | None = None, planner: _Planner | None = None):
    memory = WorkPackageMemoryStore(tmp_path / "workspace" / "work_package_memory")
    queue = RuntimePackageQueue(repo_root=tmp_path, memory_store=memory)
    bridge = WorkPackagePlannerBridge(
        planner=planner or _Planner(),
        workspace_root=str(tmp_path / "workspace"),
        memory_store=memory,
    )
    dispatcher = RuntimeDispatcher(
        queue=queue,
        task_runner=runner or _Runner(),
        workspace_root=tmp_path / "workspace",
    )
    return RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        queue=queue,
        planner_bridge=bridge,
        dispatcher=dispatcher,
        memory_store=memory,
    )


def test_completed_package_commits_serializable_memory(tmp_path: Path) -> None:
    operator = _operator(tmp_path)
    operator.submit_package(_payload("memory-completed"))
    result = operator.run_package("memory-completed")
    memory = operator.package_memory("memory-completed")
    assert result["memory_status"] == "committed"
    assert memory["final_status"] == "completed"
    assert memory["package_id"] == result["package_id"]
    assert memory["session_id"] == result["session_id"]
    assert memory["task_id"] == result["task_id"]
    assert memory["runtime_lifecycle_history"][-1]["to"] == "completed"
    assert memory["execution_evidence_summary"]["evidence_count"] == 1
    assert memory["planning_snapshot"]["planning_status"] == "planned"
    assert memory["task_graph_summary"]["node_count"] == 1
    assert "core/runtime/work_package_queue.py" in memory["modified_files_summary"]
    assert memory["test_result_summary"]["completed_steps"] == 1
    json.dumps(memory)


def test_failed_package_commits_root_cause(tmp_path: Path) -> None:
    operator = _operator(tmp_path, runner=_Runner("failed"))
    operator.submit_package(_payload("memory-failed"))
    result = operator.run_package("memory-failed")
    memory = operator.package_memory("memory-failed")
    assert result["status"] == "failed"
    assert "memory-root-cause" in memory["root_cause"]
    assert memory["final_status"] == "failed"


def test_blocked_package_commits_planning_warnings_and_errors(tmp_path: Path) -> None:
    class FailingPlanner:
        def plan(self, **_kwargs):
            raise RuntimeError("planner unavailable")

    operator = _operator(tmp_path, planner=FailingPlanner())
    payload = _payload("memory-blocked")
    payload.pop("hard_boundary")
    result = operator.submit_package(payload)
    memory = operator.package_memory("memory-blocked")
    assert result["status"] == "blocked"
    assert memory["final_status"] == "blocked"
    assert "missing_hard_boundary" in memory["warnings"]
    assert any("planner unavailable" in error for error in memory["errors"])


def test_executing_package_cannot_write_final_memory(tmp_path: Path) -> None:
    operator = _operator(tmp_path)
    operator.submit_package(_payload("memory-executing"))
    claimed = operator.queue.claim("memory-executing")
    task = operator.dispatcher._execution_task(claimed)
    executing = operator.queue.start_execution_session("memory-executing", task=task)
    assert executing["runtime_lifecycle_state"] == "executing"
    assert operator.package_memory("memory-executing") is None
    with pytest.raises(WorkPackageMemoryError, match="final_memory_requires_terminal_state"):
        operator.memory_store.commit_terminal(executing)


def test_cancelled_package_commits_memory(tmp_path: Path) -> None:
    operator = _operator(tmp_path)
    operator.submit_package(_payload("memory-cancelled"))
    result = operator.cancel_package("memory-cancelled")
    memory = operator.package_memory("memory-cancelled")
    assert result["status"] == "cancelled"
    assert memory["final_status"] == "cancelled"
    assert memory["package_id"] == "memory-cancelled"


def test_planner_reads_only_related_memory_context(tmp_path: Path) -> None:
    first = _operator(tmp_path)
    first.submit_package(_payload("related-history"))
    first.run_package("related-history")
    unrelated = _operator(tmp_path)
    unrelated.submit_package(_payload("unrelated-history", target="ui/theme.css"))
    unrelated.run_package("unrelated-history")

    planner = _Planner()
    next_operator = _operator(tmp_path, planner=planner)
    result = next_operator.submit_package(_payload("next-related"))
    used = result["planning_snapshot"]["memory_context_used"]
    assert [item["package_id"] for item in used] == ["related-history"]
    assert planner.context["memory_context"]["related_work_packages"] == used


def test_memory_commit_does_not_change_runtime_lifecycle(tmp_path: Path) -> None:
    operator = _operator(tmp_path)
    operator.submit_package(_payload("memory-readonly"))
    completed = operator.run_package("memory-readonly")
    before = copy.deepcopy(completed["runtime_lifecycle_history"])
    operator.memory_store.commit_terminal(completed)
    after = operator.queue.status("memory-readonly")["runtime_lifecycle_history"]
    assert after == before


def test_memory_module_cannot_bypass_runtime_execution_boundaries() -> None:
    source = (ROOT / "core/memory/work_package_memory.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "StepExecutor" not in source
    assert "RuntimeDispatcher" not in source
    assert "Scheduler" not in source
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"claim", "dispatch", "execute_step", "execute_steps"}
    ]


def test_status_and_cli_memory_are_machine_readable(tmp_path: Path) -> None:
    operator = _operator(tmp_path)
    operator.submit_package(_payload("memory-cli"))
    operator.run_package("memory-cli")
    status = operator.package_status("memory-cli")
    assert status["memory_status"] == "committed"
    assert status["memory_record_id"]
    assert isinstance(status["memory_context_used"], list)

    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.work_package_cli",
            "--repo-root",
            str(tmp_path),
            "memory",
            "memory-cli",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(process.stdout)
    assert process.returncode == 0
    assert payload["result"]["memory_record_id"] == status["memory_record_id"]
