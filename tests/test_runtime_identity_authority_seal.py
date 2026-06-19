from __future__ import annotations

import pytest

from core.goals.goal_lineage_contract import (
    attach_goal_lineage,
    canonical_work_identity,
    extract_goal_lineage,
    extract_runtime_identity,
    runtime_identity_matches,
)
from core.runtime.runtime_session_resume import RuntimeSessionResume


def _lineage(
    root: str,
    *,
    session: str,
    runtime: str,
    branch_type: str = "root",
    branch_id: str | None = None,
) -> dict[str, str]:
    return extract_goal_lineage(
        {
            "root_goal_id": root,
            "source_goal_id": root,
            "goal_id": root,
            "branch_type": branch_type,
            "branch_id": branch_id or root,
            "session_id": session,
            "runtime_session_id": runtime,
        },
        require_complete=True,
    )


def test_strict_runtime_identity_rejects_missing_runtime_session_id() -> None:
    legacy_lineage = {
        "root_goal_id": "goal-a",
        "source_goal_id": "goal-a",
        "goal_id": "goal-a",
        "branch_type": "root",
        "branch_id": "goal-a",
        "session_id": "session-a",
    }

    with pytest.raises(ValueError) as lineage_exc:
        extract_goal_lineage(legacy_lineage, require_complete=True)

    assert str(lineage_exc.value) == "goal_lineage_missing_fields:runtime_session_id"

    with pytest.raises(ValueError) as exc:
        extract_runtime_identity(legacy_lineage, require_complete=True)

    assert str(exc.value) == "runtime_identity_missing_fields:runtime_session_id"


def test_strict_runtime_identity_accepts_explicit_runtime_session_id() -> None:
    lineage = _lineage("goal-a", session="session-a", runtime="runtime-a")

    identity = extract_runtime_identity(lineage, require_complete=True)

    assert identity["session_id"] == "session-a"
    assert identity["runtime_session_id"] == "runtime-a"


def test_runtime_identity_match_does_not_treat_session_as_runtime_session() -> None:
    left = {"session_id": "session-a", "runtime_session_id": "runtime-a"}
    same = {"session_id": "session-a", "runtime_session_id": "runtime-a"}
    missing_runtime = {"session_id": "session-a"}
    different_runtime = {"session_id": "session-a", "runtime_session_id": "runtime-b"}

    assert runtime_identity_matches(left, same) is True
    assert runtime_identity_matches(left, missing_runtime) is False
    assert runtime_identity_matches(left, different_runtime) is False


def test_canonical_work_identity_separates_same_session_different_runtime_session() -> None:
    a = attach_goal_lineage(
        {"task_id": "shared"},
        _lineage(
            "goal-a",
            session="session-a",
            runtime="runtime-a",
            branch_type="continuation",
            branch_id="branch-1",
        ),
    )
    b = attach_goal_lineage(
        {"task_id": "shared"},
        _lineage(
            "goal-a",
            session="session-a",
            runtime="runtime-b",
            branch_type="continuation",
            branch_id="branch-1",
        ),
    )

    assert canonical_work_identity(a) != canonical_work_identity(b)


def test_resume_dedupe_keeps_same_session_different_runtime_session(tmp_path) -> None:
    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json")
    task_a = attach_goal_lineage(
        {"task_id": "shared-a", "status": "running"},
        _lineage(
            "goal-a",
            session="session-a",
            runtime="runtime-a",
            branch_type="continuation",
            branch_id="branch-1",
        ),
    )
    task_b = attach_goal_lineage(
        {"task_id": "shared-b", "status": "running"},
        _lineage(
            "goal-a",
            session="session-a",
            runtime="runtime-b",
            branch_type="continuation",
            branch_id="branch-1",
        ),
    )

    plan = runtime.build_resume_plan(session_id="session-a", tasks=[task_a, task_b])

    assert plan["snapshot_count"] == 2
    assert plan["duplicate_task_ids"] == []
    assert plan["lineage_by_task_id"]["shared-a"]["runtime_session_id"] == "runtime-a"
    assert plan["lineage_by_task_id"]["shared-b"]["runtime_session_id"] == "runtime-b"


def test_resume_dedupe_treats_same_runtime_identity_and_branch_as_duplicate(tmp_path) -> None:
    runtime = RuntimeSessionResume(workspace_root=tmp_path, storage_path=tmp_path / "resume.json")
    lineage = _lineage(
        "goal-a",
        session="session-a",
        runtime="runtime-a",
        branch_type="continuation",
        branch_id="branch-1",
    )
    task_a = attach_goal_lineage({"task_id": "shared", "status": "running", "attempt": 1}, lineage)
    task_b = attach_goal_lineage({"task_id": "renamed", "status": "running", "attempt": 2}, lineage)

    plan = runtime.build_resume_plan(session_id="session-a", tasks=[task_a, task_b])

    assert plan["snapshot_count"] == 1
    assert plan["duplicate_task_ids"] == ["renamed"]
