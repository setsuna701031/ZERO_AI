from __future__ import annotations

import json
from pathlib import Path

from core.runtime.persistent_engineering_session import (

    PersistentEngineeringSession,
    create_persistent_engineering_session_from_runtime_result,
)
import pytest

pytestmark = [pytest.mark.contract]



def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fake_runtime_result(tmp_path: Path) -> dict:
    checkpoint_path = tmp_path / "checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "ok": True,
                "status": "finished",
                "result": {
                    "step": {"type": "tool", "tool_name": "write_file"},
                    "step_executor_result": {"ok": True},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "final_answer": "multi-file engineering workflow finished",
        "planner_runtime_dispatch": {
            "ok": True,
            "status": "dispatched",
            "orchestrator": {
                "ok": True,
                "status": "finished",
                "session_id": "persistent_runtime_demo_session",
                "task_id": "planner_prt_demo",
                "goal": "Persistent Engineering Session demo",
                "session_record_path": str(tmp_path / "orchestrator_session.json"),
                "session_dir": str(tmp_path),
                "multi_cycle_engineering_loop": {
                    "cycle_count": 1,
                    "cycle_result_count": 1,
                    "closure_count": 0,
                    "cycle_results": [
                        {
                            "cycle_id": "cycle_1",
                            "runtime": {
                                "status": "finished",
                                "checkpoint_count": 1,
                                "checkpoints": [
                                    {
                                        "checkpoint_index": 0,
                                        "checkpoint_path": str(checkpoint_path),
                                        "status": "finished",
                                    }
                                ],
                            },
                        }
                    ],
                },
            },
        },
    }


def test_persistent_engineering_session_records_runtime_lineage(tmp_path: Path) -> None:
    result = fake_runtime_result(tmp_path)

    summary = create_persistent_engineering_session_from_runtime_result(
        repo_root=tmp_path,
        runtime_result=result,
        goal="Persistent Engineering Session demo",
    )

    assert summary["ok"] is True
    assert summary["runtime_session_count"] == 1
    assert summary["checkpoint_count"] == 1
    assert summary["status"] == "runtime_attached"
    assert summary["boundary"]["state_only"] is True
    assert summary["boundary"]["does_not_execute"] is True

    saved = read_json(summary["session_record_path"])
    assert saved["schema"] == "zero.aer.persistent_engineering_session.v1"
    assert saved["workflow_id"] == "planner_prt_demo"
    assert saved["session_id"] == "persistent_runtime_demo_session"
    assert saved["runtime_sessions"][0]["status"] == "finished"
    assert saved["checkpoints"][0]["checkpoint_index"] == 0


def test_persistent_engineering_session_resume_and_continue(tmp_path: Path) -> None:
    result = fake_runtime_result(tmp_path)
    session = PersistentEngineeringSession.create_from_runtime_result(
        repo_root=tmp_path,
        runtime_result=result,
        goal="Persistent Engineering Session demo",
    )

    session.record_artifact(
        path="workspace/shared/engineering_multifile_summary.md",
        kind="summary",
        description="multi-file engineering summary",
        source_step="write_file",
    )

    resume = session.create_resume_point(
        reason="operator paused after artifact generation",
        cursor={"next_step": "update_devlog"},
        required_inputs=["operator confirmation"],
    )

    summary = session.summary()
    assert summary["artifact_count"] == 1
    assert summary["resume_point_count"] == 1
    assert summary["open_resume_point_count"] == 1
    assert summary["continuation_count"] == 0

    continuation = session.record_continuation(
        resume_id=resume["resume_id"],
        continuation_result={"ok": True, "next_step": "devlog updated"},
    )

    assert continuation["status"] == "continued"

    final_summary = session.summary()
    assert final_summary["open_resume_point_count"] == 0
    assert final_summary["continuation_count"] == 1
    assert final_summary["status"] == "continued"

    saved = read_json(final_summary["session_record_path"])
    assert saved["resume_points"][0]["status"] == "continued"
    assert saved["continuations"][0]["resume_id"] == resume["resume_id"]
