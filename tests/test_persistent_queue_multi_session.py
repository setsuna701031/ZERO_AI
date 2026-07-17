from __future__ import annotations

from core.goals.goal_lineage_contract import attach_goal_lineage, extract_goal_lineage
from core.runtime.work_package_queue import RuntimePackageQueue


def _package(root_goal_id: str, session_id: str, package_id: str) -> dict:
    lineage = extract_goal_lineage(
        {
            "root_goal_id": root_goal_id,
            "source_goal_id": root_goal_id,
            "goal_id": f"{root_goal_id}-child",
            "branch_type": "continuation",
            "branch_id": "continuation-1",
            "session_id": session_id,
            "runtime_session_id": f"runtime-{session_id}",
        },
        require_complete=True,
    )
    return attach_goal_lineage(
        {"package_id": package_id, "task_id": "shared-task", "status": "queued"},
        lineage,
    )


def test_persistent_queue_reload_keeps_same_ids_in_separate_goal_lineages(tmp_path):
    queue = RuntimePackageQueue(repo_root=tmp_path)
    queue.enqueue(_package("goal-a", "session-a", "package-a"))
    queue.enqueue(_package("goal-b", "session-b", "package-b"))

    restored = RuntimePackageQueue(repo_root=tmp_path)
    records = {record["package_id"]: record for record in restored.list_packages()}

    assert set(records) == {"package-a", "package-b"}
    assert records["package-a"]["root_goal_id"] == "goal-a"
    assert records["package-b"]["root_goal_id"] == "goal-b"
    assert records["package-a"]["goal_lineage_id"] != records["package-b"]["goal_lineage_id"]


def test_persistent_queue_retry_is_idempotent_only_inside_exact_lineage(tmp_path):
    queue = RuntimePackageQueue(repo_root=tmp_path)
    original = queue.enqueue(_package("goal-a", "session-a", "package-a"))
    duplicate = queue.enqueue(_package("goal-a", "session-a", "package-a-retry"))
    distinct = queue.enqueue(_package("goal-b", "session-a", "package-b"))

    assert duplicate["package_id"] == original["package_id"]
    assert duplicate["queue_admission"]["result"] == "duplicate_idempotent"
    assert distinct["package_id"] == "package-b"
    assert len(queue.list_packages()) == 2
