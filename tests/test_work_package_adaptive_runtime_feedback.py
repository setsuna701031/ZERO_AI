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


ROOT = Path(__file__).resolve().parents[1]


def _payload(package_id: str) -> dict:
    return {
        "package_id": package_id,
        "title": "Adaptive runtime feedback",
        "goal": "Recover from a repairable runtime failure",
        "description": "Preserve feedback, evidence, and appended replan steps.",
        "target_files": ["core/runtime/runtime_dispatcher.py"],
        "requirements": ["adaptive feedback", "append-only replan"],
        "hard_boundary": ["no direct execution", "preserve lifecycle"],
        "non_mainline_issue_reporting": ["report drift"],
        "validation_commands": ["pytest"],
        "completion_report_format": ["adaptive runtime summary"],
    }


class _AdaptivePlanner:
    def plan(self, **kwargs):
        context = kwargs.get("context") or {}
        package = context.get("work_package") or {}
        if package.get("replan_request"):
            return {
                "ok": True,
                "steps": [{"id": "repair", "type": "verify"}],
                "meta": {"semantic_type": "adaptive_repair"},
            }
        return {
            "ok": True,
            "steps": [{"id": "initial", "type": "inspect"}],
            "meta": {"semantic_type": "initial"},
        }


class _AdaptiveRunner:
    def __init__(self, *, blocked: bool = False) -> None:
        self.blocked = blocked
        self.calls: list[dict] = []

    def run_task(self, *, task, current_tick=0, **_kwargs):
        self.calls.append(copy.deepcopy(task))
        if current_tick == 0:
            status = "blocked" if self.blocked else "failed"
            return {
                "ok": False,
                "status": status,
                "current_step_index": 1,
                "error": f"{status}:repairable-root-cause",
                "next_action": "block" if self.blocked else "replan",
                "message": "initial step needs repair",
                "task": {**copy.deepcopy(task), "current_step_index": 1},
                "runtime_state": {"status": status, "current_step_index": 1},
            }
        return {
            "ok": True,
            "status": "finished",
            "current_step_index": current_tick + 1,
            "message": "repair verification passed",
            "task": {**copy.deepcopy(task), "current_step_index": current_tick + 1},
            "runtime_state": {"status": "finished", "current_step_index": current_tick + 1},
        }


def _operator(tmp_path: Path, *, blocked: bool = False) -> RuntimeWorkPackageOperator:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    bridge = WorkPackagePlannerBridge(
        planner=_AdaptivePlanner(),
        workspace_root=str(tmp_path / "workspace"),
        memory_store=queue.memory_store,
    )
    dispatcher = RuntimeDispatcher(
        queue=queue,
        task_runner=_AdaptiveRunner(blocked=blocked),
        workspace_root=tmp_path / "workspace",
        planner_bridge=bridge,
    )
    return RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        queue=queue,
        planner_bridge=bridge,
        dispatcher=dispatcher,
    )


def test_successful_and_failed_feedback_preserve_adaptive_contract(tmp_path: Path) -> None:
    operator = _operator(tmp_path)
    operator.submit_package(_payload("adaptive-feedback"))
    result = operator.run_package("adaptive-feedback")

    failed, succeeded = result["step_feedback"]
    assert {
        "step_index",
        "step_id",
        "step_type",
        "ok",
        "failed",
        "blocked",
        "root_cause",
        "evidence",
        "output_summary",
        "next_action",
    } <= failed.keys()
    assert failed["next_action"] == "replan"
    assert "repairable-root-cause" in failed["root_cause"]
    assert failed["evidence"]["status"] == "failed"
    assert succeeded["ok"] is True
    assert succeeded["next_action"] == "complete"


def test_replan_request_appends_steps_and_preserves_steps_evidence_and_history(tmp_path: Path) -> None:
    operator = _operator(tmp_path)
    submitted = operator.submit_package(_payload("adaptive-append"))
    original_steps = copy.deepcopy(submitted["runtime_queue_item"]["steps"])
    original_history = copy.deepcopy(submitted["runtime_lifecycle_history"])

    result = operator.run_package("adaptive-append")

    assert result["status"] == "completed"
    assert result["runtime_queue_item"]["steps"][:1] == original_steps
    assert len(result["runtime_queue_item"]["steps"]) == 2
    assert result["runtime_queue_item"]["steps"][1]["id"] == "replan-1:repair"
    assert result["planning_snapshot"]["executable_steps"] == original_steps
    assert result["task_graph"]["edges"][-1] == {"from": "initial", "to": "replan-1:repair"}
    assert result["replan_requests"][0]["previous_evidence"]["status"] == "failed"
    assert result["replan_history"][0]["previous_evidence_preserved"] is True
    assert result["runtime_lifecycle_history"][: len(original_history)] == original_history
    assert result["progress"]["failed_steps"] == 1
    assert result["progress"]["completed_steps"] == 1


def test_replan_limit_fails_without_overwriting_first_request_or_evidence(tmp_path: Path) -> None:
    class _AlwaysFailRunner:
        def run_task(self, *, task, current_tick=0, **_kwargs):
            return {
                "ok": False,
                "status": "failed",
                "current_step_index": current_tick + 1,
                "error": f"failed:tick-{current_tick}",
                "next_action": "replan",
                "task": copy.deepcopy(task),
                "runtime_state": {"status": "failed", "current_step_index": current_tick + 1},
            }

    operator = _operator(tmp_path)
    operator.dispatcher.task_runner = _AlwaysFailRunner()
    operator.submit_package(_payload("adaptive-limit"))

    result = operator.run_package("adaptive-limit")

    assert result["status"] == "failed"
    assert "runtime_replan_limit_reached:1/1" in result["root_cause"]
    assert len(result["replan_requests"]) == 1
    assert len(result["step_feedback"]) == 2
    assert all(item["evidence"] for item in result["step_feedback"])


def test_blocked_step_is_not_completed_or_replanned(tmp_path: Path) -> None:
    operator = _operator(tmp_path, blocked=True)
    operator.submit_package(_payload("adaptive-blocked"))

    result = operator.run_package("adaptive-blocked")

    assert result["status"] == "blocked"
    assert result["progress"]["completed_steps"] == 0
    assert result["progress"]["failed_steps"] == 1
    assert result["step_feedback"][0]["blocked"] is True
    assert result["step_feedback"][0]["next_action"] == "block"
    assert not result.get("replan_requests")


def test_memory_commit_contains_replan_evidence_summary(tmp_path: Path) -> None:
    operator = _operator(tmp_path)
    operator.submit_package(_payload("adaptive-memory"))
    operator.run_package("adaptive-memory")

    memory = operator.package_memory("adaptive-memory")

    assert memory["execution_evidence_summary"]["replan_count"] == 1
    assert memory["execution_evidence_summary"]["replan_appended_steps"] == 1
    assert memory["execution_evidence_summary"]["failed_steps"] == 1


def test_summary_cli_is_not_polluted_by_replan_evidence(tmp_path: Path) -> None:
    operator = _operator(tmp_path)
    operator.submit_package(_payload("adaptive-summary"))
    operator.run_package("adaptive-summary")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}

    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.work_package_cli",
            "--repo-root",
            str(tmp_path),
            "summary",
            "adaptive-summary",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(process.stdout)
    assert process.returncode == 0
    assert payload["lifecycle_state"] == "completed"
    assert payload["failed_steps"] == 1
    assert payload["step_types"] == ["inspect", "verify"]
    assert "previous_evidence" not in process.stdout
    assert "replan_requests" not in process.stdout
    assert "repairable-root-cause" not in process.stdout
