from __future__ import annotations

from pathlib import Path

import pytest

import core.tasks.engineering_goal_lifecycle as lifecycle_module
import core.tasks.work_package_scheduler as scheduler_module
from core.evidence.evidence_record import EvidenceRecord
from core.evidence.evidence_validator import EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.runtime.runtime_authority_seal import (
    _RUNTIME_DISPATCHER_ISSUER_TOKEN,
    is_work_package_completion_authority,
    issue_work_package_completion_authority,
)
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from core.tasks.engineering_goal_lifecycle import EngineeringGoalLifecycle
from core.tasks.work_package_scheduler import STATUS_COMPLETED, STATUS_FAILED, WorkPackageScheduler
from tests.test_aer_multifile_engineering_workflow_contract import MultiFileEngineeringPlanner
from core.agent.agent_loop import AgentLoop
from core.tools.tool_registry import ToolRegistry


def _task() -> dict:
    task = {"task_id": "task-a", "package_id": "package-a", "session_id": "session-a"}
    task["runtime_execution_capability"] = RuntimeDispatcher._execution_capability(task)
    return task


def test_taskrunner_rejects_completion_without_execution_lineage() -> None:
    with pytest.raises(PermissionError, match="terminal_execution_evidence_required"):
        TaskRunner().complete_task(_task())


def test_taskrunner_rejects_completion_after_denied_execution() -> None:
    runner = TaskRunner(step_executor=StepExecutor())
    result = runner.execute_owned_step({"id": "step-a", "type": "command", "command": "echo denied"}, task={"task_id": "task-a"})
    assert result["ok"] is False
    with pytest.raises(PermissionError, match="terminal_execution_evidence_required"):
        runner.complete_task({"task_id": "task-a"})


def test_taskrunner_completes_only_with_terminal_execution_evidence() -> None:
    runner = TaskRunner(step_executor=StepExecutor())
    task = _task()
    result = runner.execute_owned_step({"id": "step-a", "type": "command", "command": "echo sealed"}, task=task)
    authority = runner._terminal_completion_authority(task=task, step={"id": "step-a"}, result=result)
    completed = runner.runtime.mark_finished(task, completion_authority=authority)
    assert completed["status"] == "finished"


def test_serialized_terminal_evidence_cannot_complete_task() -> None:
    runner = TaskRunner()
    with pytest.raises(PermissionError, match="terminal_execution_evidence_required"):
        runner.complete_task(
            _task(),
            terminal_evidence={
                "schema": "zero.terminal_execution_evidence.summary.v1",
                "task_id": "task-a",
                "package_id": "package-a",
                "session_id": "session-a",
                "authoritative": True,
            },
        )


def _lifecycle() -> EngineeringGoalLifecycle:
    item = object.__new__(EngineeringGoalLifecycle)
    item.path = "unused"
    item.goal = "goal"
    item.goal_id = "goal-a"
    item.raw_steps = [{"id": "step-a"}]
    item.task_summaries = [{"task_id": "step-a"}]
    item._append_event = lambda *_args, **_kwargs: None
    return item


def _state() -> dict:
    return {
        "selected_task": {"task_id": "step-a"},
        "completed_tasks": [],
        "blocked_tasks": [],
        "failed_tasks": [],
        "superseded_tasks": [],
        "cancelled_tasks": [],
        "task_buckets": {"running": [{"summary": {"task_id": "step-a"}, "task_payload": {}}]},
    }


def test_engineering_goal_lifecycle_rejects_ok_only_completion(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle_module, "_write_json", lambda *_args: None)
    result = _lifecycle().finish_execution(state=_state(), result_bundle={"ok": True}, memory_record={}, relevant_memory={})
    assert result["goal_state"] == "completion_rejected"


def test_engineering_goal_lifecycle_accepts_canonical_attestation(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle_module, "_write_json", lambda *_args: None)
    evidence = EvidenceValidator().validate(EvidenceRecord("e", "goal-a", None, "test", "ok", "now"))
    attestation = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[evidence],
        all_subgoals_completed=True,
    )
    result = _lifecycle().finish_execution(
        state=_state(),
        result_bundle={"ok": True},
        memory_record={},
        relevant_memory={},
        completion_attestation=attestation,
    )
    assert result["goal_state"] == "completed"


def test_engineering_goal_lifecycle_rejects_serialized_attestation(monkeypatch) -> None:
    monkeypatch.setattr(lifecycle_module, "_write_json", lambda *_args: None)
    result = _lifecycle().finish_execution(
        state=_state(),
        result_bundle={"ok": True},
        memory_record={},
        relevant_memory={},
        completion_attestation={"accepted": True, "completed": True, "goal_id": "goal-a"},
    )
    assert result["goal_state"] == "completion_rejected"


def test_work_package_scheduler_rejects_result_artifact_dict_completion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        scheduler_module,
        "submit_work_package",
        lambda *_args, **_kwargs: {"ok": True, "package_id": "package-a", "result_path": "forged.json"},
    )
    result = WorkPackageScheduler(repo_root=tmp_path).submit({"package_id": "package-a", "kind": "readonly_audit", "mode": "explore", "title": "x", "scope_paths": ["core/x.py"], "report_path": "workspace/x.md"})
    assert result["status"] == STATUS_FAILED


def test_work_package_scheduler_accepts_live_dispatcher_authority(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(scheduler_module, "submit_work_package", lambda *_args, **_kwargs: {"ok": True, "package_id": "package-a"})
    scheduler = WorkPackageScheduler(repo_root=tmp_path)
    scheduler.submit({"package_id": "package-a", "kind": "readonly_audit", "mode": "explore", "title": "x", "scope_paths": ["core/x.py"], "report_path": "workspace/x.md"}, execute=False)
    authority = issue_work_package_completion_authority(_RUNTIME_DISPATCHER_ISSUER_TOKEN, package_id="package-a")
    assert is_work_package_completion_authority(authority, package_id="package-a")
    assert scheduler.run("package-a", completion_authority=authority)["status"] == STATUS_COMPLETED


def test_agent_loop_denied_execution_does_not_report_finished(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shared = workspace / "shared"
    shared.mkdir(parents=True)
    (shared / "module_a.py").write_text("x", encoding="utf-8")
    (shared / "module_b.py").write_text("x", encoding="utf-8")
    loop = AgentLoop(
        planner=MultiFileEngineeringPlanner(),
        step_executor=StepExecutor(
            tool_registry=ToolRegistry(workspace_dir=str(workspace)),
            workspace_root=str(workspace),
        ),
        repo_root=str(tmp_path),
    )
    result = loop.run("Use planner runtime dispatch for Persistent Autonomous Engineering Runtime multi-file engineering workflow")
    orchestrator = result["persistent_runtime_orchestrator"]
    assert orchestrator["ok"] is False
    assert orchestrator["status"] != "finished"
