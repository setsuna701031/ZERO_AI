from __future__ import annotations

import ast
import copy
from pathlib import Path

from core.memory.work_package_memory import WorkPackageMemoryStore
from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.runtime.work_package_queue import RuntimePackageQueue, work_package_execution_path


ROOT = Path(__file__).resolve().parents[1]


def _payload(package_id: str) -> dict:
    return {
        "package_id": package_id,
        "title": "Autonomous engineering loop closure",
        "goal": "Complete a governed replan and resume through the single WorkPackage runtime",
        "description": "Preserve completed work, evidence, graph history, cursor, and memory.",
        "target_files": ["core/runtime/runtime_dispatcher.py"],
        "requirements": ["feedback to replan", "replan to resume", "resume to memory"],
        "hard_boundary": ["no second runtime", "no second planner", "append-only graph"],
        "non_mainline_issue_reporting": ["report all drift"],
        "validation_commands": ["pytest"],
        "completion_report_format": ["loop closure summary"],
        "metadata": {"max_replans": 1},
    }


class _GovernedPlanner:
    def plan(self, **kwargs):
        package = (kwargs.get("context") or {}).get("work_package") or {}
        if package.get("replan_request"):
            return {
                "ok": True,
                "steps": [{"id": "repair-verify", "type": "verify"}],
                "meta": {"semantic_type": "governed_replan"},
            }
        return {
            "ok": True,
            "steps": [
                {"id": "step-1", "type": "inspect"},
                {"id": "step-2", "type": "verify"},
            ],
            "meta": {"semantic_type": "engineering"},
        }


class _FailSecondStepRunner:
    def __init__(self) -> None:
        self.step_ids: list[str] = []

    def run_task(self, *, task, current_tick=0, **_kwargs):
        step_id = task["steps"][current_tick]["id"]
        self.step_ids.append(step_id)
        if step_id == "step-2":
            return {
                "ok": False,
                "status": "failed",
                "current_step_index": current_tick + 1,
                "error": "repairable:step-2",
                "next_action": "replan",
                "task": copy.deepcopy(task),
                "runtime_state": {"status": "failed", "current_step_index": current_tick + 1},
            }
        return {
            "ok": True,
            "status": "running",
            "current_step_index": current_tick + 1,
            "message": f"completed:{step_id}",
            "task": {**copy.deepcopy(task), "current_step_index": current_tick + 1},
            "runtime_state": {"status": "running", "current_step_index": current_tick + 1},
        }


class _ResumeRunner:
    def __init__(self) -> None:
        self.step_ids: list[str] = []
        self.ticks: list[int] = []

    def run_task(self, *, task, current_tick=0, **_kwargs):
        step_id = task["steps"][current_tick]["id"]
        self.step_ids.append(step_id)
        self.ticks.append(current_tick)
        return {
            "ok": True,
            "status": "finished",
            "current_step_index": current_tick + 1,
            "message": f"completed:{step_id}",
            "task": {**copy.deepcopy(task), "current_step_index": current_tick + 1},
            "runtime_state": {"status": "finished", "current_step_index": current_tick + 1},
        }


class _ForbiddenPlanner:
    def plan(self, **_kwargs):
        raise AssertionError("resume must use the persisted graph, not a second planner path")


def _operator(tmp_path: Path, *, planner, runner) -> RuntimeWorkPackageOperator:
    memory = WorkPackageMemoryStore(tmp_path / "workspace" / "work_package_memory")
    queue = RuntimePackageQueue(repo_root=tmp_path, memory_store=memory)
    bridge = WorkPackagePlannerBridge(
        planner=planner,
        workspace_root=str(tmp_path / "workspace"),
        memory_store=memory,
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
        memory_store=memory,
    )


def test_single_mainline_ownership_contract() -> None:
    operator_source = (ROOT / "core/runtime/work_package_operator.py").read_text(encoding="utf-8")
    dispatcher_source = (ROOT / "core/runtime/runtime_dispatcher.py").read_text(encoding="utf-8")
    runner_source = (ROOT / "core/runtime/task_runner.py").read_text(encoding="utf-8")
    queue_source = (ROOT / "core/runtime/work_package_queue.py").read_text(encoding="utf-8")
    planner_source = (ROOT / "core/planning/work_package_planner_bridge.py").read_text(encoding="utf-8")

    operator_tree = ast.parse(operator_source)
    dispatcher_tree = ast.parse(dispatcher_source)
    runner_tree = ast.parse(runner_source)

    def constructors(tree: ast.AST) -> set[str]:
        return {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

    assert "RuntimeDispatcher" in constructors(operator_tree)
    assert "TaskRunner" in constructors(dispatcher_tree)
    assert "StepExecutor" in constructors(runner_tree)
    assert "StepExecutor" not in constructors(operator_tree)
    assert "StepExecutor" not in constructors(dispatcher_tree)
    assert '"runtime_owner": "RuntimeDispatcher"' in planner_source
    assert "AgentExecutionRuntime" not in planner_source
    assert "AgentExecutionRuntime" not in queue_source
    assert work_package_execution_path()["authority_path"].endswith(
        "RuntimeDispatcher -> TaskRunner -> StepExecutor"
    )


def test_long_chain_feedback_replan_resume_memory_and_completion(tmp_path: Path) -> None:
    first_runner = _FailSecondStepRunner()
    first = _operator(tmp_path, planner=_GovernedPlanner(), runner=first_runner)
    submitted = first.submit_package(_payload("loop-closure"))
    original_graph = copy.deepcopy(submitted["task_graph"])

    interrupted = first.dispatcher.dispatch("loop-closure", max_steps=2)
    contract = interrupted["session_resume_contract"]

    assert first_runner.step_ids == ["step-1", "step-2"]
    assert [item["next_action"] for item in interrupted["step_feedback"]] == ["continue", "replan"]
    assert interrupted["replan_requests"][0]["previous_evidence"]["error"] == "repairable:step-2"
    assert interrupted["replan_history"][0]["previous_evidence_preserved"] is True
    assert interrupted["task_graph"]["nodes"][:2] == original_graph["nodes"]
    assert interrupted["task_graph"]["edges"][:1] == original_graph["edges"]
    assert [step["id"] for step in contract["active_graph"]["steps"]] == [
        "step-1",
        "step-2",
        "replan-1:repair-verify",
    ]
    assert contract["active_graph"]["cursor"] == 2
    assert contract["completed_steps"]["step_ids"] == ["step-1"]
    assert contract["failed_steps"]["step_ids"] == ["step-2"]
    assert contract["memory_summary"]["status"] == "pending"

    resumed_runner = _ResumeRunner()
    restarted = _operator(tmp_path, planner=_ForbiddenPlanner(), runner=resumed_runner)
    completed = restarted.resume_session("loop-closure")
    memory = restarted.package_memory("loop-closure")

    assert resumed_runner.ticks == [2]
    assert resumed_runner.step_ids == ["replan-1:repair-verify"]
    assert [item["step_id"] for item in completed["step_feedback"]] == [
        "step-1",
        "step-2",
        "replan-1:repair-verify",
    ]
    assert len(completed["replan_history"]) == 1
    assert completed["status"] == "completed"
    assert completed["progress"]["current_step"] == 3
    assert completed["progress"]["completed_steps"] == 2
    assert completed["progress"]["failed_steps"] == 1
    assert completed["progress"]["remaining_steps"] == 0
    assert completed["session_resume_count"] == 1
    assert completed["memory_status"] == "committed"
    assert memory["final_status"] == "completed"
    assert memory["session_resume_summary"]["cursor"] == 3
    assert memory["session_resume_summary"]["resume_count"] == 1
    assert memory["execution_evidence_summary"]["evidence_count"] == 3
    assert memory["execution_evidence_summary"]["replan_count"] == 1
    assert memory["execution_evidence_summary"]["successful_steps"] == 2
    assert memory["execution_evidence_summary"]["failed_steps"] == 1
    assert memory["test_result_summary"]["completed_steps"] == 2
    assert memory["test_result_summary"]["failed_steps"] == 1


def test_work_package_memory_has_no_execution_or_resume_control() -> None:
    source = (ROOT / "core/memory/work_package_memory.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"dispatch", "resume", "run_task", "execute_step", "replan_package"}
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (calls & forbidden)
