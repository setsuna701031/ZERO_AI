from __future__ import annotations

import copy
import inspect
from pathlib import Path

import core.tasks.work_package_scheduler as scheduler_module
from core.adaptive import AdaptiveRuntimeResume
from core.operator import codex_operator, verification_runner
from core.operator.verification_runner import run_verification_command
from core.runtime.multistep_task_report import build_multistep_task_report
from core.runtime.persistent_runtime_orchestrator import run_persistent_runtime_orchestrator
from core.tasks.goal_continuation_coordinator import GoalContinuationCoordinator
from core.tasks.work_package_scheduler import STATUS_FAILED, WorkPackageScheduler


class _ResumeRuntime:
    def __init__(self) -> None:
        self.state = {"status": "terminal_validation", "steps": [{"id": "step-a"}], "current_step_index": 0}

    def load_runtime_state(self, _task):
        return copy.deepcopy(self.state)

    def begin_terminal_validation(self, _task):
        return copy.deepcopy(self.state)

    def save_runtime_state(self, _task, state):
        self.state = copy.deepcopy(state)
        return copy.deepcopy(self.state)


class _ResumeRunner:
    def __init__(self, live_evidence) -> None:
        self.runtime = _ResumeRuntime()
        self.live_evidence = live_evidence

    def run_task(self, _task, current_tick=0):
        return {"ok": True, "status": "finished", "last_result": {"ok": True}, "runtime_state": self.runtime.load_runtime_state({})}

    def record_terminal_observation(self, _task, *, terminal_evidence=None, **_kwargs):
        if terminal_evidence is self.live_evidence:
            return {"ok": True, "status": "finished", "runtime_state": self.runtime.load_runtime_state({})}
        return {"ok": False, "status": "completion_rejected", "blocked": True, "runtime_state": self.runtime.load_runtime_state({})}


def _authority(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "step_id": "operator",
        "authority_source": "execution_gateway",
        "runtime_session": f"session-{task_id}",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": f"trace-{task_id}",
    }


def _work_package(package_id: str) -> dict:
    return {
        "package_id": package_id,
        "kind": "readonly_audit",
        "mode": "explore",
        "title": "Legacy migration audit",
        "scope_paths": ["core/x.py"],
        "report_path": "workspace/audit.md",
    }


def test_adaptive_resume_without_terminal_evidence_is_blocked() -> None:
    live = object()
    result = AdaptiveRuntimeResume(max_cycles=1).run(
        task_runner=_ResumeRunner(live),
        task={"task_id": "task-a", "steps": [{"id": "step-a"}]},
    )
    assert result["ok"] is False
    assert result["status"] == "blocked"


def test_adaptive_resume_with_live_terminal_evidence_may_finish() -> None:
    live = object()
    result = AdaptiveRuntimeResume(max_cycles=1).run(
        task_runner=_ResumeRunner(live),
        task={"task_id": "task-a", "steps": [{"id": "step-a"}]},
        terminal_evidence=live,
    )
    assert result["ok"] is True
    assert result["status"] == "finished"


def test_goal_continuation_rejects_ok_only_completed_mapping(tmp_path: Path) -> None:
    def runner(_payload):
        return {
            "ok": True,
            "result_bundle": {
                "goal_lifecycle": {"goal_id": "goal-a", "goal_state": "completed"},
                "goal_completion_authority_result": {"accepted": True, "completed": True},
            },
        }

    result = GoalContinuationCoordinator(repo_root=tmp_path, task_runner=runner, max_cycles=1).continue_goal(
        {"task_type": "engineering_task", "engineering_goal_lifecycle": True, "goal_id": "goal-a"}
    )
    assert result["ok"] is False
    assert result["goal_lifecycle"]["goal_state"] == "blocked"


def test_work_package_result_mapping_cannot_complete(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(scheduler_module, "submit_work_package", lambda *_args, **_kwargs: {"ok": True})
    result = WorkPackageScheduler(repo_root=tmp_path).submit(_work_package("package-a"))
    assert result["status"] == STATUS_FAILED
    assert result["error"] == "work_package_completion_authority_required"


def test_verification_runner_bare_taskrunner_path_is_migration_blocked() -> None:
    result = run_verification_command("echo should-not-run", authority=_authority("task-a"), task={"task_id": "task-a"})
    assert result.ok is False
    assert result.stderr == "legacy_runtime_dispatcher_migration_required"


def test_operator_surfaces_do_not_construct_bare_taskrunner() -> None:
    assert "TaskRunner(" not in inspect.getsource(codex_operator.apply_operator_edit_plan)
    assert "TaskRunner(" not in inspect.getsource(verification_runner.run_verification_command)


def test_multistep_report_is_descriptive_not_completion_authority() -> None:
    report = build_multistep_task_report(
        task_id="task-a",
        status="finished",
        lifecycle=[],
        plan={"steps": []},
        execution_result={"ok": True},
        artifacts=[],
    ).to_dict()
    assert report["metadata"]["report_only"] is True
    assert "task_completion_authority" not in report
    assert "terminal_evidence" not in report


def test_persistent_orchestrator_failure_does_not_return_finished(tmp_path: Path) -> None:
    result = run_persistent_runtime_orchestrator(
        repo_root=tmp_path,
        task={"task_id": "persistent-a", "goal": "persistent autonomous engineering", "cycles": [{"cycle_id": "a"}]},
        force=True,
        fail_cycle_index=0,
    )["persistent_runtime_orchestrator"]
    assert result["ok"] is False
    assert result["status"] != "finished"
