from __future__ import annotations

import json
from pathlib import Path

from core.runtime.long_engineering_runtime import (
    execute_long_engineering_runtime,
    find_latest_long_runtime_recovery,
    resume_long_engineering_runtime,
)


def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_long_engineering_runtime_finishes_and_writes_persistent_journal(tmp_path: Path) -> None:
    task = {
        "id": "aer_long_loop_ok",
        "goal": "Persistent Autonomous Engineering Runtime final loop",
        "target_groups": [
            ["prepare runtime plan"],
            ["execute step and verify"],
            ["write continuity summary"],
        ],
    }

    result = execute_long_engineering_runtime(
        repo_root=tmp_path,
        task=task,
        task_id="aer_long_loop_ok",
        goal=task["goal"],
    )

    runtime = result["long_engineering_runtime"]

    assert result["ok"] is True
    assert runtime["ok"] is True
    assert runtime["status"] == "finished"
    assert runtime["plan_group_count"] == 3
    assert runtime["executed_group_count"] == 3
    assert runtime["checkpoint_count"] == 3
    assert runtime["recoverable"] is False

    journal = read_json(runtime["session_journal_path"])
    state = read_json(runtime["session_state_path"])

    assert journal["schema"] == "zero.aer.long_engineering_runtime.v1"
    assert journal["status"] == "finished"
    assert state["status"] == "finished"
    assert state["executed_group_count"] == 3
    assert journal["boundary"]["scheduler_remains_orchestration"] is True
    assert journal["boundary"]["step_executor_remains_execution_endpoint"] is True


def test_long_engineering_runtime_recovery_then_resume_closes_failure_loop(tmp_path: Path) -> None:
    task = {
        "id": "aer_long_loop_recovery",
        "goal": "Failure Recovery Resume closure",
        "target_groups": [
            ["group one"],
            ["group two fails once"],
            ["group three continues after resume"],
        ],
    }

    failed = execute_long_engineering_runtime(
        repo_root=tmp_path,
        task=task,
        task_id="aer_long_loop_recovery",
        goal=task["goal"],
        fail_group_index=1,
    )

    failed_runtime = failed["long_engineering_runtime"]

    assert failed["ok"] is False
    assert failed_runtime["status"] == "recoverable_failure"
    assert failed_runtime["recoverable"] is True
    assert failed_runtime["executed_group_count"] == 1
    assert failed_runtime["checkpoint_count"] == 2
    assert Path(failed_runtime["recovery_marker_path"]).exists()

    marker = find_latest_long_runtime_recovery(tmp_path)
    assert marker["status"] == "recoverable_failure"
    assert marker["failed_group_index"] == 1
    assert marker["failed_plan_index"] == 2

    resumed = resume_long_engineering_runtime(
        repo_root=tmp_path,
        task={"id": "aer_long_loop_resume", "goal": "resume from recoverable failure"},
        task_id="aer_long_loop_resume",
        goal="resume from recoverable failure",
    )

    resume = resumed["long_engineering_runtime_resume"]
    resumed_runtime = resume["resumed_runtime"]

    assert resumed["ok"] is True
    assert resume["ok"] is True
    assert resume["status"] == "resumed"
    assert resume["source_session_id"] == failed_runtime["session_id"]
    assert resume["remaining_groups"] == [
        ["group two fails once"],
        ["group three continues after resume"],
    ]
    assert resumed_runtime["status"] == "finished"
    assert resumed_runtime["executed_group_count"] == 2
    assert resumed_runtime["checkpoint_count"] == 2
    assert resume["boundary"]["creates_new_linked_session"] is True

    superseded = (
        tmp_path
        / "workspace"
        / "long_engineering_runtime"
        / failed_runtime["session_id"]
        / "recovery_marker.superseded.json"
    )
    assert superseded.exists()
    superseded_marker = json.loads(superseded.read_text(encoding="utf-8"))
    assert superseded_marker["resume_ok"] is True
    assert superseded_marker["superseded_by_session_id"] == resumed_runtime["session_id"]


def test_long_engineering_runtime_executor_failure_creates_recoverable_marker(tmp_path: Path) -> None:
    task = {
        "id": "aer_long_loop_executor_failure",
        "goal": "executor failure creates recovery marker",
        "target_groups": [["ok"], ["boom"], ["after"]],
    }

    def executor(group: list[str], group_index: int, session: object) -> dict:
        if group_index == 1:
            return {"ok": False, "status": "failed", "message": "executor failed"}
        return {"ok": True, "status": "finished", "message": "executor ok"}

    result = execute_long_engineering_runtime(
        repo_root=tmp_path,
        task=task,
        task_id="aer_long_loop_executor_failure",
        goal=task["goal"],
        executor=executor,
    )

    runtime = result["long_engineering_runtime"]

    assert result["ok"] is False
    assert runtime["status"] == "recoverable_failure"
    assert runtime["failure_count"] == 1
    assert Path(runtime["recovery_marker_path"]).exists()

    marker = json.loads(Path(runtime["recovery_marker_path"]).read_text(encoding="utf-8"))
    assert marker["failure_result"]["message"] == "executor failed"
    assert marker["failed_group"] == ["boom"]
