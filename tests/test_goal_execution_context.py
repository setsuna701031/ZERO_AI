from pathlib import Path

from core.goals import (
    GoalExecutionContext,
    GoalOrchestrator,
    GoalRepository,
    GoalResumePoint,
    PersistentGoal,
    PersistentSubgoal,
)


def test_execution_context_is_planner_facing_and_preserves_resume_point(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Ship feature", "Long horizon goal", evidence_refs=["goal-ev"]))
    repository.append_subgoal(
        PersistentSubgoal(
            "subgoal-1",
            "goal-1",
            "Implement",
            status="blocked",
            resume_point=GoalResumePoint("goal-1", "subgoal-1", "task-1", "step-2"),
            evidence_refs=["subgoal-ev"],
        )
    )

    context = GoalOrchestrator(repository).build_execution_context(
        "goal-1",
        related_memory_context={"related": ["opaque-memory-context"]},
    )

    assert isinstance(context, GoalExecutionContext)
    assert context.subgoal_id == "subgoal-1"
    assert context.resume_point["step_id"] == "step-2"
    assert context.evidence_refs == ["goal-ev", "subgoal-ev"]
    assert context.related_memory_context == {"related": ["opaque-memory-context"]}
