from __future__ import annotations

import json
from pathlib import Path

from core.runtime.persistent_runtime_orchestrator import (
    run_persistent_runtime_orchestrator,
    should_route_persistent_runtime,
)


def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_persistent_runtime_orchestrator_routing_policy() -> None:
    assert should_route_persistent_runtime({"persistent_runtime": True}) is True
    assert should_route_persistent_runtime({"cycles": [{"goal": "cycle"}]}) is True
    assert should_route_persistent_runtime({"goal": "Persistent Autonomous Engineering Runtime"}) is True
    assert should_route_persistent_runtime({"goal": "Failure Recovery Resume"}) is True
    assert should_route_persistent_runtime({"goal": "normal short task"}) is False


def test_persistent_runtime_orchestrator_runs_multicycle_session(tmp_path: Path) -> None:
    task = {
        "id": "orchestrator_ok",
        "goal": "Persistent Autonomous Engineering Runtime",
        "persistent_runtime": True,
        "cycles": [
            {
                "cycle_id": "prepare",
                "goal": "prepare",
                "target_groups": [["prepare runtime"], ["verify prepare"]],
            },
            {
                "cycle_id": "execute",
                "goal": "execute",
                "target_groups": [["execute runtime"], ["verify execute"]],
            },
        ],
    }

    result = run_persistent_runtime_orchestrator(
        repo_root=tmp_path,
        task=task,
    )

    orchestrator = result["persistent_runtime_orchestrator"]

    assert result["ok"] is True
    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "finished"
    assert orchestrator["routed"] is True
    assert orchestrator["cycle_count"] == 2
    assert orchestrator["cycle_result_count"] == 2
    assert orchestrator["closure_count"] == 0
    assert orchestrator["boundary"]["does_not_modify_execution_gateway"] is True
    assert orchestrator["boundary"]["does_not_modify_step_executor"] is True

    session_record = read_json(orchestrator["session_record_path"])
    assert session_record["schema"] == "zero.aer.persistent_runtime_orchestrator.v1"
    assert session_record["status"] == "finished"
    assert session_record["multi_cycle_engineering_loop"]["status"] == "finished"


def test_persistent_runtime_orchestrator_failure_recovery_resume_continue(tmp_path: Path) -> None:
    task = {
        "id": "orchestrator_recovery",
        "goal": "Failure Recovery Resume persistent runtime",
        "persistent_runtime": True,
        "cycles": [
            {
                "cycle_id": "cycle_one",
                "goal": "cycle one",
                "target_groups": [["one prepare"], ["one verify"]],
            },
            {
                "cycle_id": "cycle_two",
                "goal": "cycle two",
                "target_groups": [["two prepare"], ["two fail once"], ["two continue"]],
            },
            {
                "cycle_id": "cycle_three",
                "goal": "cycle three",
                "target_groups": [["three continue"]],
            },
        ],
    }

    result = run_persistent_runtime_orchestrator(
        repo_root=tmp_path,
        task=task,
        fail_cycle_index=1,
        fail_group_index=1,
    )

    orchestrator = result["persistent_runtime_orchestrator"]
    loop = orchestrator["multi_cycle_engineering_loop"]

    assert result["ok"] is False
    assert orchestrator["status"] == "recoverable_failure"
    assert orchestrator["cycle_count"] == 3
    assert orchestrator["closure_count"] == 1

    failed_cycle = loop["cycle_results"][1]
    closure = loop["closure_results"][0]["closure"]

    assert failed_cycle["runtime"]["status"] == "recoverable_failure"
    assert closure["status"] == "closed"
    assert closure["ok"] is True
    assert loop["cycle_results"][2]["runtime"]["status"] == "finished"

    session_record = read_json(orchestrator["session_record_path"])
    assert session_record["status"] == "recoverable_failure"
    assert session_record["boundary"]["delegates_to_multi_cycle_engineering_loop"] is True


def test_persistent_runtime_orchestrator_refuses_normal_task_without_force(tmp_path: Path) -> None:
    result = run_persistent_runtime_orchestrator(
        repo_root=tmp_path,
        task={"id": "normal", "goal": "normal short task"},
    )

    orchestrator = result["persistent_runtime_orchestrator"]

    assert result["ok"] is False
    assert orchestrator["status"] == "not_persistent_runtime_task"
    assert orchestrator["routed"] is False


def test_persistent_runtime_orchestrator_force_runs_normal_task(tmp_path: Path) -> None:
    result = run_persistent_runtime_orchestrator(
        repo_root=tmp_path,
        task={"id": "forced", "goal": "normal short task"},
        force=True,
    )

    orchestrator = result["persistent_runtime_orchestrator"]

    assert result["ok"] is True
    assert orchestrator["status"] == "finished"
    assert orchestrator["routed"] is True
    assert orchestrator["cycle_count"] == 1
