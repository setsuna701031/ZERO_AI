from __future__ import annotations

import json

import pytest

from core.adaptive.adaptive_replan_state_machine import AdaptiveReplanStateMachine
from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime
from core.goals.goal_repository import GoalRepository
from core.goals.persistent_goal import PersistentGoal
from core.program.engineering_program_state_machine import EngineeringProgramStateMachine
from core.program.engineering_program_transition import EngineeringProgramTransition
from core.runtime.runtime_state_guard import RuntimeStateGuardError
from core.runtime.runtime_state_machine import RuntimeStateMachine
from core.runtime.runtime_transition_policy import RuntimeTransitionPolicyError
from core.runtime.task_runtime import TaskRuntime
from core.runtime.task_state_machine import TaskStateMachine
from core.session.engineering_session_state_machine import EngineeringSessionStateMachine
from core.session.engineering_session_transition import EngineeringSessionTransition
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
pytestmark = [pytest.mark.contract]




def _task(tmp_path, *, task_id: str = "task-a") -> dict:
    task_dir = tmp_path / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "mutation governance",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [],
    }


def test_goal_repository_requires_state_machine_validator_and_completion_authority(tmp_path) -> None:
    repository = GoalRepository(tmp_path, storage_path=tmp_path / "goals.jsonl")
    repository.append_goal(PersistentGoal("goal-a", "Goal A"))

    with pytest.raises(ValueError, match="goal_lifecycle_contract_violation"):
        repository.update_goal_status("goal-a", "resumable", resume_point={"step": 1})
    with pytest.raises(ValueError, match="canonical_completion_attestation_required"):
        repository.update_goal_status("goal-a", "completed")

    assert repository.get_goal("goal-a")["status"] == "pending"


def test_engineering_goal_repository_rejects_transition_bypass_and_nested_state_override(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal-a", "summary": "Goal A"})

    updated = repository.update_goal(
        "goal-a",
        {
            "metadata": {"status": "completed"},
            "payload": {"status": "failed"},
        },
    )
    assert updated["status"] == "pending"

    with pytest.raises(ValueError, match="goal_lifecycle_contract_violation"):
        repository.update_goal("goal-a", {"status": "resumable", "resume_point": {"step": 1}})
    assert repository.load_goal("goal-a")["status"] == "pending"


def test_runtime_status_mutation_requires_machine_policy_and_owner(tmp_path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path)
    state = runtime.ensure_runtime_state(task)

    running = runtime.apply_runtime_transition(
        task,
        state,
        owner="task_runtime",
        action="authorized_start",
        updates={"status": "running"},
    )
    assert running["status"] == "running"
    assert running["runtime_transition_policy"]["last_decision"]["ok"] is True
    assert running["last_transition_owner"] == "task_runtime"

    with pytest.raises(RuntimeStateGuardError):
        runtime.apply_runtime_transition(
            task,
            state,
            owner="task_runner",
            action="non_owner_status_write",
            updates={"status": "running"},
        )

    terminal = {**running, "status": "finished"}
    with pytest.raises(RuntimeTransitionPolicyError):
        runtime.apply_runtime_transition(
            task,
            terminal,
            owner="task_runtime",
            action="metadata_resume",
            updates={"status": "running"},
        )


def test_runtime_state_machine_force_set_cannot_bypass_transition_graph() -> None:
    machine = RuntimeStateMachine()
    state = machine.ensure_runtime_status_fields({"status": "finished"})

    unchanged, result = machine.force_set(state, "running")

    assert result.ok is False
    assert unchanged["status"] == "finished"


def test_legacy_task_state_machine_blocks_patch_and_terminal_reopen(tmp_path) -> None:
    machine = TaskStateMachine(tmp_path / "task")
    machine.initialize("task", "goal", "engineering")

    with pytest.raises(PermissionError, match="task_state_mutation_authority_required"):
        machine.patch_state({"current_state": "finished"})

    machine.transition("running", "start")
    machine.transition("finished", "finish")
    with pytest.raises(ValueError, match="Invalid task state transition"):
        machine.transition("running", "forged resume")


def test_session_program_and_replan_completion_fail_closed_without_authority() -> None:
    session = EngineeringSessionStateMachine().transition(
        EngineeringSessionTransition(
            from_state="active",
            to_state="completed",
            action="completed",
            reason="payload_claimed_complete",
            evidence={},
            session_id="session-a",
            task_id="goal-a",
        )
    )
    program = EngineeringProgramStateMachine().transition(
        EngineeringProgramTransition(
            from_state="active",
            to_state="completed",
            action="completed",
            reason="metadata_claimed_complete",
            session_state={"session_state": "completed"},
            goal_id="goal-a",
        )
    )
    replan = AdaptiveReplanStateMachine().evaluate_contract(
        {"loop_action": "complete", "reason": "payload_claimed_complete"},
        goal_id="goal-a",
    )

    assert session.accepted is False
    assert session.blocked_reason == "canonical_completion_attestation_required"
    assert program.accepted is False
    assert program.blocked_reason == "canonical_completion_attestation_required"
    assert replan.accepted is False
    assert replan.blocked_reason == "canonical_completion_attestation_required"


def test_continuation_and_replan_state_require_owner_and_respect_limits() -> None:
    continuation = ContinuationRuntime.start("goal-a", max_continuations=1)
    replan = ReplanRuntime.start(max_replans=1)

    with pytest.raises(PermissionError, match="continuation_mutation_authority_required"):
        continuation.replace(continuation_count=1)
    with pytest.raises(PermissionError, match="replan_mutation_authority_required"):
        replan.replace(replan_count=1)

    continuation = continuation.record_work_item({"goal_id": "goal-b"})
    replan = replan.record_replan({"goal_id": "goal-a"})
    with pytest.raises(RuntimeError, match="continuation_limit_reached"):
        continuation.record_work_item({"goal_id": "goal-c"})
    with pytest.raises(RuntimeError, match="replan_limit_reached"):
        replan.record_replan({"goal_id": "goal-a"})


def test_persisted_runtime_state_is_not_overridden_by_nested_payload(tmp_path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path, task_id="nested")
    task["metadata"] = {"status": "finished"}
    task["payload"] = {"status": "failed"}

    state = runtime.ensure_runtime_state(task)
    persisted = json.loads((tmp_path / "tasks" / "nested" / "runtime_state.json").read_text(encoding="utf-8"))

    assert state["status"] == "queued"
    assert persisted["status"] == "queued"
