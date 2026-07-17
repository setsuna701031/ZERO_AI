from __future__ import annotations

import json
from pathlib import Path

from core.runtime.long_engineering_runtime import execute_long_engineering_runtime
from core.runtime.recovery_replay_closure import (

    close_latest_recovery_replay,
    run_multi_cycle_engineering_loop,
)
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_recovery_replay_closure_closes_latest_failed_long_runtime(tmp_path: Path) -> None:
    failed_task = {
        "id": "closure_source",
        "goal": "create recoverable source",
        "target_groups": [["prepare"], ["fail once"], ["continue"]],
    }

    failed = execute_long_engineering_runtime(
        repo_root=tmp_path,
        task=failed_task,
        task_id="closure_source",
        goal="create recoverable source",
        fail_group_index=1,
    )

    assert failed["ok"] is False
    failed_runtime = failed["long_engineering_runtime"]
    assert Path(failed_runtime["recovery_marker_path"]).exists()

    closed = close_latest_recovery_replay(
        repo_root=tmp_path,
        task={"id": "closure_resume", "goal": "resume closure"},
        task_id="closure_resume",
        goal="resume closure",
    )

    closure = closed["recovery_replay_closure"]

    assert closed["ok"] is True
    assert closure["ok"] is True
    assert closure["status"] == "closed"
    assert closure["source_session_id"] == failed_runtime["session_id"]
    assert closure["resumed_session_id"]

    log_path = Path(closure["closure_log_path"])
    assert log_path.exists()
    log = read_json(str(log_path))
    assert log["schema"] == "zero.aer.recovery_replay_closure.v1"
    assert log["closures"][-1]["status"] == "closed"

    superseded = (
        tmp_path
        / "workspace"
        / "long_engineering_runtime"
        / failed_runtime["session_id"]
        / "recovery_marker.superseded.json"
    )
    assert superseded.exists()


def test_multi_cycle_engineering_loop_runs_multiple_cycles(tmp_path: Path) -> None:
    task = {
        "id": "multi_cycle_ok",
        "goal": "persistent autonomous engineering runtime",
        "cycles": [
            {
                "cycle_id": "cycle_prepare",
                "goal": "prepare",
                "target_groups": [["prepare files"], ["verify prepare"]],
            },
            {
                "cycle_id": "cycle_execute",
                "goal": "execute",
                "target_groups": [["execute work"], ["verify work"]],
            },
            {
                "cycle_id": "cycle_summarize",
                "goal": "summarize",
                "target_groups": [["write continuity summary"]],
            },
        ],
    }

    result = run_multi_cycle_engineering_loop(repo_root=tmp_path, task=task)

    loop = result["multi_cycle_engineering_loop"]

    assert result["ok"] is True
    assert loop["ok"] is True
    assert loop["status"] == "finished"
    assert loop["cycle_count"] == 3
    assert loop["cycle_result_count"] == 3
    assert loop["closure_count"] == 0

    log = read_json(loop["loop_log_path"])
    assert log["status"] == "finished"
    assert log["boundary"]["uses_long_engineering_runtime"] is True
    assert log["boundary"]["uses_recovery_replay_closure"] is True


def test_multi_cycle_engineering_loop_failure_recovery_resume_then_continue(tmp_path: Path) -> None:
    task = {
        "id": "multi_cycle_recovery",
        "goal": "failure recovery resume then continue",
        "cycles": [
            {
                "cycle_id": "cycle_one",
                "goal": "cycle one",
                "target_groups": [["one prepare"], ["one verify"]],
            },
            {
                "cycle_id": "cycle_two",
                "goal": "cycle two",
                "target_groups": [["two prepare"], ["two recoverable fail"], ["two continue"]],
            },
            {
                "cycle_id": "cycle_three",
                "goal": "cycle three",
                "target_groups": [["three continue after resume"]],
            },
        ],
    }

    result = run_multi_cycle_engineering_loop(
        repo_root=tmp_path,
        task=task,
        fail_cycle_index=1,
        fail_group_index=1,
    )

    loop = result["multi_cycle_engineering_loop"]

    assert result["ok"] is True
    assert loop["status"] == "finished"
    assert loop["cycle_count"] == 3
    assert loop["cycle_result_count"] == 3
    assert loop["closure_count"] == 1

    failed_cycle = loop["cycle_results"][1]
    closure = loop["closure_results"][0]["closure"]

    assert failed_cycle["runtime"]["status"] == "recoverable_failure"
    assert closure["status"] == "closed"
    assert closure["ok"] is True
    assert closure["source_session_id"] == failed_cycle["runtime"]["session_id"]
    assert closure["resume"]["remaining_groups"] == [
        ["two recoverable fail"],
        ["two continue"],
    ]

    final_cycle = loop["cycle_results"][2]
    assert final_cycle["runtime"]["status"] == "finished"

    log = read_json(loop["loop_log_path"])
    assert log["status"] == "finished"
    assert len(log["closure_results"]) == 1
