from __future__ import annotations

from pathlib import Path

import pytest

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime


pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]

LINEAGE = {
    "root_goal_id": "root-goal",
    "source_goal_id": "root-goal",
    "goal_id": "root-goal",
    "goal_lineage_id": "lineage-001",
    "branch_type": "root",
    "branch_id": "root-goal",
    "session_id": "session-001",
    "runtime_session_id": "runtime-session-001",
}


def test_continuation_runtime_preserves_runtime_identity() -> None:
    runtime = ContinuationRuntime.start(
        "root-goal",
        continuation_count=0,
        max_continuations=2,
        goal_lineage=LINEAGE,
    )

    assert runtime.root_goal_id == "root-goal"
    assert runtime.goal_lineage_id == "lineage-001"
    assert runtime.session_id == "session-001"
    assert runtime.runtime_session_id == "runtime-session-001"

    next_runtime = runtime.record_work_item({"goal_id": "root-goal__continuation_1"})

    assert next_runtime.current_goal_id == "root-goal__continuation_1"
    assert next_runtime.root_goal_id == runtime.root_goal_id
    assert next_runtime.goal_lineage_id == runtime.goal_lineage_id
    assert next_runtime.session_id == runtime.session_id
    assert next_runtime.runtime_session_id == runtime.runtime_session_id


def test_replan_runtime_preserves_runtime_identity() -> None:
    runtime = ReplanRuntime.start(
        replan_count=0,
        max_replans=2,
        goal_lineage=LINEAGE,
    )

    assert runtime.root_goal_id == "root-goal"
    assert runtime.goal_lineage_id == "lineage-001"
    assert runtime.session_id == "session-001"
    assert runtime.runtime_session_id == "runtime-session-001"

    next_runtime = runtime.record_replan({"request_id": "replan-1"})

    assert next_runtime.replan_count == 1
    assert next_runtime.root_goal_id == runtime.root_goal_id
    assert next_runtime.goal_lineage_id == runtime.goal_lineage_id
    assert next_runtime.session_id == runtime.session_id
    assert next_runtime.runtime_session_id == runtime.runtime_session_id


def test_runtime_identity_cannot_be_mutated_without_owner_method() -> None:
    runtime = ContinuationRuntime.start("root-goal", goal_lineage=LINEAGE)

    with pytest.raises(PermissionError, match="continuation_mutation_authority_required"):
        runtime.replace(session_id="session-drift")

    replan = ReplanRuntime.start(goal_lineage=LINEAGE)

    with pytest.raises(PermissionError, match="replan_mutation_authority_required"):
        replan.replace(runtime_session_id="runtime-drift")


def test_engineering_goal_loop_injects_lineage_into_adaptive_runtimes() -> None:
    source = Path("core/tasks/engineering_goal_loop.py").read_text(encoding="utf-8-sig")

    assert "ContinuationRuntime.start(" in source
    assert "ReplanRuntime.start(" in source
    assert "goal_lineage=current_lineage" in source
