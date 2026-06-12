from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.runtime.work_package_queue import RuntimePackageQueue
from services.system_boot import ZeroSystem


ROOT = Path(__file__).resolve().parents[1]


def _payload(package_id: str) -> dict:
    return {
        "package_id": package_id,
        "title": "Engineering session resume",
        "goal": "Resume the active graph after process restart",
        "description": "Preserve graph cursor, evidence, replan history, and memory.",
        "target_files": ["core/runtime/work_package_queue.py"],
        "requirements": ["resume contract", "no duplicate completed step"],
        "hard_boundary": ["do not replan", "do not recreate package"],
        "non_mainline_issue_reporting": ["report drift"],
        "validation_commands": ["pytest"],
        "completion_report_format": ["resume summary"],
    }


class _Planner:
    def __init__(self) -> None:
        self.calls = 0

    def plan(self, **_kwargs):
        self.calls += 1
        return {
            "ok": True,
            "steps": [
                {"id": "one", "type": "inspect"},
                {"id": "two", "type": "verify"},
                {"id": "three", "type": "respond"},
            ],
            "meta": {"semantic_type": "resume"},
        }


class _ForbiddenPlanner:
    def plan(self, **_kwargs):
        raise AssertionError("resume must not replan")


class _RecordingRunner:
    def __init__(self) -> None:
        self.ticks: list[int] = []
        self.step_ids: list[str] = []

    def run_task(self, *, task, current_tick=0, **_kwargs):
        self.ticks.append(current_tick)
        step = task["steps"][current_tick]
        self.step_ids.append(step["id"])
        return {
            "ok": True,
            "status": "finished" if current_tick + 1 >= len(task["steps"]) else "running",
            "current_step_index": current_tick + 1,
            "message": f"completed:{step['id']}",
            "task": {**copy.deepcopy(task), "current_step_index": current_tick + 1},
            "runtime_state": {"status": "running", "current_step_index": current_tick + 1},
        }


def _operator(tmp_path: Path, *, planner, runner) -> RuntimeWorkPackageOperator:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    bridge = WorkPackagePlannerBridge(
        planner=planner,
        workspace_root=str(tmp_path / "workspace"),
        memory_store=queue.memory_store,
    )
    dispatcher = RuntimeDispatcher(
        queue=queue,
        task_runner=runner,
        workspace_root=tmp_path / "workspace",
        planner_bridge=bridge,
    )
    return RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        queue=queue,
        planner_bridge=bridge,
        dispatcher=dispatcher,
    )


def test_session_save_contract_contains_required_runtime_state(tmp_path: Path) -> None:
    planner = _Planner()
    runner = _RecordingRunner()
    operator = _operator(tmp_path, planner=planner, runner=runner)
    operator.submit_package(_payload("resume-save"))

    interrupted = operator.dispatcher.dispatch("resume-save", max_steps=1)
    contract = interrupted["session_resume_contract"]

    assert contract["session_id"] == interrupted["session_id"]
    assert contract["task_id"] == interrupted["task_id"]
    assert contract["package_id"] == "resume-save"
    assert contract["active_graph"]["cursor"] == 1
    assert [step["id"] for step in contract["active_graph"]["steps"]] == ["one", "two", "three"]
    assert contract["completed_steps"] == {"count": 1, "step_ids": ["one"]}
    assert contract["failed_steps"] == {"count": 0, "step_ids": []}
    assert contract["replan_history"] == []
    assert contract["memory_summary"]["status"] == "pending"
    assert contract["last_runtime_state"]["current_step_index"] == 1


def test_process_restart_restores_cursor_and_does_not_duplicate_completed_step(tmp_path: Path) -> None:
    first_runner = _RecordingRunner()
    first = _operator(tmp_path, planner=_Planner(), runner=first_runner)
    submitted = first.submit_package(_payload("resume-restart"))
    first.dispatcher.dispatch("resume-restart", max_steps=1)
    original_package_id = submitted["package_id"]
    original_history = first.queue.status("resume-restart")["runtime_lifecycle_history"]

    resumed_runner = _RecordingRunner()
    restarted = _operator(tmp_path, planner=_ForbiddenPlanner(), runner=resumed_runner)
    result = restarted.resume_session("resume-restart")

    assert result["status"] == "completed"
    assert result["package_id"] == original_package_id
    assert first_runner.step_ids == ["one"]
    assert resumed_runner.ticks == [1, 2]
    assert resumed_runner.step_ids == ["two", "three"]
    assert [item["step_id"] for item in result["step_feedback"]] == ["one", "two", "three"]
    assert result["runtime_lifecycle_history"][: len(original_history)] == original_history
    assert result["session_resume_count"] == 1


def test_resume_after_replan_restores_appended_graph_without_replanning(tmp_path: Path) -> None:
    class _ReplanPlanner:
        def plan(self, **kwargs):
            package = (kwargs.get("context") or {}).get("work_package") or {}
            if package.get("replan_request"):
                return {"ok": True, "steps": [{"id": "repair", "type": "verify"}], "meta": {}}
            return {"ok": True, "steps": [{"id": "initial", "type": "inspect"}], "meta": {}}

    class _FailForReplan:
        def run_task(self, *, task, current_tick=0, **_kwargs):
            return {
                "ok": False,
                "status": "failed",
                "current_step_index": 1,
                "error": "repairable",
                "next_action": "replan",
                "task": copy.deepcopy(task),
                "runtime_state": {"status": "failed", "current_step_index": 1},
            }

    first = _operator(tmp_path, planner=_ReplanPlanner(), runner=_FailForReplan())
    first.submit_package(_payload("resume-replan"))
    interrupted = first.dispatcher.dispatch("resume-replan", max_steps=1)
    assert [step["id"] for step in interrupted["session_resume_contract"]["active_graph"]["steps"]] == [
        "initial",
        "replan-1:repair",
    ]

    resumed_runner = _RecordingRunner()
    restarted = _operator(tmp_path, planner=_ForbiddenPlanner(), runner=resumed_runner)
    result = restarted.resume_session("resume-replan")

    assert result["status"] == "completed"
    assert resumed_runner.step_ids == ["replan-1:repair"]
    assert len(result["replan_history"]) == 1
    assert result["progress"]["failed_steps"] == 1
    assert result["progress"]["completed_steps"] == 1


def test_resume_commits_memory_and_summary_cli_reports_restored_completion(tmp_path: Path) -> None:
    first = _operator(tmp_path, planner=_Planner(), runner=_RecordingRunner())
    first.submit_package(_payload("resume-memory"))
    first.dispatcher.dispatch("resume-memory", max_steps=2)

    restarted = _operator(tmp_path, planner=_ForbiddenPlanner(), runner=_RecordingRunner())
    result = restarted.resume_session("resume-memory")
    memory = restarted.package_memory("resume-memory")

    assert result["memory_status"] == "committed"
    assert memory["session_resume_summary"]["resume_count"] == 1
    assert memory["session_resume_summary"]["cursor"] == 3

    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.work_package_cli",
            "--repo-root",
            str(tmp_path),
            "summary",
            "resume-memory",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    summary = json.loads(process.stdout)
    assert process.returncode == 0
    assert summary["lifecycle_state"] == "completed"
    assert summary["completed_steps"] == 3
    assert summary["remaining_steps"] == 0


def test_system_boot_resume_hook_uses_existing_work_package_operator() -> None:
    class _Operator:
        def __init__(self) -> None:
            self.calls = 0

        def resume_interrupted_packages(self):
            self.calls += 1
            return {"ok": True, "action": "work_package_sessions_resumed", "resumed_count": 1}

    operator = _Operator()
    system = ZeroSystem.__new__(ZeroSystem)
    system.work_package_operator = operator
    system.work_package_session_resume_result = {}
    system.boot_errors = {}

    result = system._resume_work_package_sessions_on_boot()

    assert result["resumed_count"] == 1
    assert operator.calls == 1
    source = (ROOT / "services/system_boot.py").read_text(encoding="utf-8")
    assert source.index("self._ensure_runtime_components()") < source.index(
        "self._resume_work_package_sessions_on_boot()"
    )
