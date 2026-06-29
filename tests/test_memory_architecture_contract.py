from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from core.memory.memory_ownership_contract import (

    MEMORY_MODULES,
    audit_memory_control_boundaries,
    memory_architecture_summary,
)
from core.memory.work_package_memory import WorkPackageMemoryStore
from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.integration]



ROOT = Path(__file__).resolve().parents[1]


def test_memory_inventory_declares_all_required_layers() -> None:
    summary = memory_architecture_summary()
    names = {item["name"] for item in summary["memory_modules"]}
    assert names == {
        "task_memory",
        "planning_memory",
        "runtime_global_memory",
        "engineering_memory",
        "work_package_memory",
    }
    for item in summary["memory_modules"]:
        assert set(item) >= {
            "owner",
            "read_path",
            "write_path",
            "lifecycle_authority",
            "persistent",
            "planner_readable",
            "runtime_readable",
        }


def test_memory_ownership_contract_is_explicit() -> None:
    contract = memory_architecture_summary()["contract"]
    assert contract["work_package_memory"] == "terminal engineering facts only"
    assert contract["planning_memory"] == "planning context only"
    assert contract["task_memory"] == "cannot control runtime lifecycle"
    assert contract["runtime_global_memory"] == "cannot change planner decisions"
    assert contract["engineering_memory"] == "cannot bypass queue/dispatcher/scheduler"
    assert contract["all_memory"] == "cannot call execution endpoints"


def test_memory_modules_have_no_runtime_control_imports_or_calls() -> None:
    audit = audit_memory_control_boundaries(ROOT)
    assert audit["ok"] is True
    assert audit["violations"] == []
    assert len(audit["audited_modules"]) == sum(len(item["modules"]) for item in MEMORY_MODULES)


def test_work_package_memory_commit_does_not_mutate_lifecycle_payload(tmp_path: Path) -> None:
    store = WorkPackageMemoryStore(tmp_path)
    runtime_record = {
        "package_id": "package-memory-contract",
        "session_id": "session-memory-contract",
        "task_id": "task-memory-contract",
        "status": "completed",
        "runtime_lifecycle_state": "completed",
        "runtime_lifecycle_history": [
            {"from": "executing", "to": "completed", "reason": "done"}
        ],
    }
    original = copy.deepcopy(runtime_record)
    store.commit_terminal(runtime_record)
    assert runtime_record == original


def test_planner_receives_summary_only_not_memory_control_objects(tmp_path: Path) -> None:
    store = WorkPackageMemoryStore(tmp_path / "memory")
    store.commit_terminal(
        {
            "package_id": "history-package",
            "session_id": "history-session",
            "task_id": "history-task",
            "status": "failed",
            "goal": "repair core/runtime/example.py",
            "target_files": ["core/runtime/example.py"],
            "root_cause": "example failure",
            "runtime_lifecycle_history": [{"from": "executing", "to": "failed"}],
        }
    )

    class Planner:
        context = {}

        def plan(self, **kwargs):
            self.context = copy.deepcopy(kwargs["context"])
            return {"ok": True, "steps": [{"type": "inspect"}], "meta": {}}

    planner = Planner()
    bridge = WorkPackagePlannerBridge(
        planner=planner,
        workspace_root=str(tmp_path / "workspace"),
        memory_store=store,
    )
    snapshot = bridge.plan_package(
        {
            "package_id": "next-package",
            "session_id": "next-session",
            "task_id": "next-task",
            "goal": "repair core/runtime/example.py",
            "target_files": ["core/runtime/example.py"],
        }
    )
    context = planner.context["memory_context"]["related_work_packages"][0]
    assert context == snapshot["memory_context_used"][0]
    assert "runtime_lifecycle_history" not in context
    assert "planning_snapshot" not in context
    assert "authority" not in context


def test_legacy_core_task_memory_path_is_explicitly_deprecated() -> None:
    import core.task_memory as legacy
    from core.memory.task_memory import TaskMemory

    assert legacy.TaskMemory is TaskMemory
    assert legacy.DEPRECATED_MEMORY_PATH == "core.task_memory"
    assert legacy.CANONICAL_MEMORY_PATH == "core.memory.task_memory"
    assert "core.task_memory" in memory_architecture_summary()["deprecated_paths"]


def test_memory_status_cli_is_machine_readable(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.work_package_cli",
            "--repo-root",
            str(tmp_path),
            "memory-status",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(process.stdout)
    assert process.returncode == 0
    result = payload["result"]
    assert set(result) >= {
        "memory_modules",
        "ownership",
        "writable_paths",
        "readable_paths",
        "deprecated_paths",
        "drift_warnings",
    }
