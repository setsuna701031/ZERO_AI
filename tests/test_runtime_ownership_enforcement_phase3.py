from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.runtime.task_runtime import TaskRuntime


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / ".test_tmp" / "runtime_ownership_enforcement_phase3"


def setup_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def teardown_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def _task(task_id: str, steps: list[dict]) -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": task_id,
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": steps,
        "current_step_index": 0,
        "repair_context": {
            "engineering_goal_state": {
                "status": "running",
                "current_subgoal_id": "sg1",
                "subgoals": [
                    {
                        "subgoal_id": "sg1",
                        "title": "probe",
                        "status": "running",
                        "step_indices": [0],
                        "depends_on": [],
                    }
                ],
            }
        },
    }


def test_subgoal_flow_finished_uses_runtime_transition_authority() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("subgoal_finished", [{"type": "final_answer", "content": "done"}])

    state = runtime.ensure_runtime_state(task)
    state["current_step_index"] = 1
    state = runtime.save_runtime_state(task, state)

    result = runtime.prepare_current_subgoal(task=task, current_tick=7)
    saved = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["status"] == "finished"
    assert result["runtime_state"]["status"] == "finished"
    assert saved["status"] == "finished"
    assert saved["current_step_index"] == 1
    assert saved["runtime_owner"] == "task_runtime"
    assert saved["last_transition_owner"] == "task_runtime"
    assert saved["last_transition_action"] == "subgoal_flow_finished"


def test_subgoal_dependency_blocked_uses_runtime_transition_authority() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task(
        "subgoal_blocked",
        [
            {
                "type": "final_answer",
                "content": "blocked",
                "subgoal_id": "sg2",
            }
        ],
    )
    task["repair_context"]["engineering_goal_state"] = {
        "status": "running",
        "current_subgoal_id": "sg2",
        "completed_subgoals": [],
        "subgoals": [
            {
                "subgoal_id": "sg2",
                "title": "blocked probe",
                "status": "pending",
                "step_indices": [0],
                "depends_on": ["missing_dependency"],
            }
        ],
    }

    result = runtime.prepare_current_subgoal(task=task, current_tick=8)
    saved = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["runtime_state"]["status"] == "blocked"
    assert saved["status"] == "blocked"
    assert "missing_dependency" in saved["last_error"]
    assert saved["runtime_owner"] == "task_runtime"
    assert saved["last_transition_owner"] == "task_runtime"
    assert saved["last_transition_action"] == "subgoal_dependency_blocked"
