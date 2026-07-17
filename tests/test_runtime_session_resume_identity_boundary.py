from __future__ import annotations

import pytest

from core.runtime.runtime_session_resume import RuntimeSessionResume, RuntimeSessionResumeStoreError


def _task(*, runtime_identity, runtime: str = "runtime-a", lineage_id: str = "lineage-a"):
    lineage = {
        "root_goal_id": "goal-a",
        "goal_lineage_id": lineage_id,
        "branch_type": "root",
        "branch_id": "goal-a",
        "session_id": "session-a",
        "runtime_session_id": "runtime-a",
    }
    return {
        "task_id": "task-a",
        "goal_id": "goal-a",
        "status": "running",
        "root_goal_id": "goal-a",
        "goal_lineage_id": "lineage-a",
        "branch_type": "root",
        "branch_id": "goal-a",
        "session_id": "session-a",
        "runtime_session_id": runtime,
        "runtime_identity": runtime_identity,
        "goal_lineage": lineage,
    }


def test_session_id_missing_is_rejected_before_identity_mismatch(tmp_path) -> None:
    task = _task(runtime_identity={"runtime_session_id": "runtime-b"}, runtime="runtime-b")

    with pytest.raises(RuntimeSessionResumeStoreError, match="^session_id_missing$"):
        RuntimeSessionResume(workspace_root=tmp_path).create_session_record(
            session_id="session-a",
            tasks=[task],
        )


def test_session_record_without_session_id_is_rejected(tmp_path) -> None:
    with pytest.raises(RuntimeSessionResumeStoreError, match="^session_id_missing$"):
        RuntimeSessionResume(workspace_root=tmp_path).create_session_record(
            tasks=[{"task_id": "legacy", "status": "running"}],
        )


def test_runtime_session_id_missing_is_rejected_before_lineage_mismatch(tmp_path) -> None:
    task = _task(runtime_identity={"session_id": "session-a"}, lineage_id="lineage-b")

    with pytest.raises(RuntimeSessionResumeStoreError, match="^runtime_session_id_missing$"):
        RuntimeSessionResume(workspace_root=tmp_path).create_session_record(
            session_id="session-a",
            tasks=[task],
        )


def test_runtime_identity_mismatch_is_not_reported_as_lineage_mismatch(tmp_path) -> None:
    task = _task(
        runtime_identity={"session_id": "session-a", "runtime_session_id": "runtime-a"},
        runtime="runtime-b",
        lineage_id="lineage-b",
    )

    with pytest.raises(RuntimeSessionResumeStoreError, match="^runtime_identity_mismatch$"):
        RuntimeSessionResume(workspace_root=tmp_path).create_session_record(
            session_id="session-a",
            tasks=[task],
        )


def test_lineage_mismatch_remains_distinct_after_identity_matches(tmp_path) -> None:
    task = _task(
        runtime_identity={"session_id": "session-a", "runtime_session_id": "runtime-a"},
        lineage_id="lineage-b",
    )

    with pytest.raises(RuntimeSessionResumeStoreError, match="^lineage_mismatch$"):
        RuntimeSessionResume(workspace_root=tmp_path).create_session_record(
            session_id="session-a",
            tasks=[task],
        )


def test_legacy_task_without_runtime_identity_section_remains_compatible(tmp_path) -> None:
    legacy = {"task_id": "legacy", "status": "running"}

    record = RuntimeSessionResume(workspace_root=tmp_path).create_session_record(
        session_id="session-a",
        tasks=[legacy],
    )

    assert record.snapshots[0].task["session_id"] == "session-a"
    assert "runtime_session_id" not in record.snapshots[0].task
