from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
from core.runtime.work_package_operator import RuntimeWorkPackageOperator
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.llm]




ROOT = Path(__file__).resolve().parents[1]


def _payload(package_id: str = "adaptive-package") -> dict:
    return {
        "package_id": package_id,
        "title": "Adaptive planning bridge",
        "goal": "Turn a work package into runtime steps",
        "description": "Build and preserve a task graph before runtime claim.",
        "target_files": ["core/runtime/work_package_queue.py"],
        "requirements": ["produce planning snapshot", "produce executable steps"],
        "hard_boundary": ["no direct StepExecutor path"],
        "non_mainline_issue_reporting": ["report only"],
        "validation_commands": ["python -m pytest tests/test_work_package_adaptive_planning_bridge.py -q"],
        "completion_report_format": ["planning snapshot", "pytest result"],
    }


class _Planner:
    def plan(self, **_kwargs):
        return {
            "ok": True,
            "intent": "engineering",
            "steps": [
                {"id": "inspect", "type": "llm", "prompt": "inspect"},
                {"id": "validate", "type": "llm", "prompt": "validate"},
            ],
            "meta": {"semantic_type": "multi_step_task", "execution_route": "test"},
        }


class _FailingPlanner:
    def plan(self, **_kwargs):
        raise RuntimeError("planning unavailable")


def test_submit_enters_planning_pipeline_and_produces_runtime_steps(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        planner_bridge=WorkPackagePlannerBridge(planner=_Planner()),
    )
    result = operator.submit_package(_payload())
    assert result["status"] == "queued"
    assert result["planning_status"] == "planned"
    assert result["planning_snapshot"]["executable_steps"]
    assert result["runtime_queue_item"]["steps"] == result["planning_snapshot"]["executable_steps"]
    assert result["runtime_queue_item"]["taskrunner_required"] is True
    assert result["runtime_queue_item"]["step_executor_endpoint_only"] is True


def test_planning_snapshot_builds_sequential_task_graph_and_preserves_identity(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        planner_bridge=WorkPackagePlannerBridge(planner=_Planner()),
    )
    result = operator.submit_package(_payload())
    snapshot = result["planning_snapshot"]
    assert snapshot["package_id"] == result["package_id"]
    assert snapshot["session_id"] == result["session_id"]
    assert snapshot["task_id"] == result["task_id"]
    assert snapshot["task_graph_summary"]["node_count"] == 2
    assert snapshot["task_graph_summary"]["edge_count"] == 1
    assert snapshot["task_graph"]["nodes"][1]["depends_on"] == ["inspect"]
    assert result["transition_history"][0]["to"] == "queued"
    assert result["runtime_queue_item"]["transition_history"] == result["transition_history"]
    assert result["runtime_queue_item"]["last_transition"] == result["last_transition"]


def test_planning_failure_is_blocked_and_preserves_error(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        planner_bridge=WorkPackagePlannerBridge(planner=_FailingPlanner()),
    )
    payload = _payload("planning-failed")
    payload.pop("hard_boundary")
    result = operator.submit_package(payload)
    assert result["status"] == "blocked"
    assert result["planning_status"] == "failed"
    assert result["planning_snapshot"]["runtime_queue_item"] is None
    assert result["planning_snapshot"]["executable_steps"] == []
    assert "planning unavailable" in result["blocked_reason"]
    assert result["planning_snapshot"]["warnings"] == ["missing_hard_boundary"]
    assert result["last_transition"]["to"] == "blocked"


def test_status_exposes_planning_and_task_graph_summary(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        planner_bridge=WorkPackagePlannerBridge(planner=_Planner()),
    )
    operator.submit_package(_payload())
    status = operator.package_status("adaptive-package")
    assert status["planning_status"] == "planned"
    assert status["task_graph_summary"]["node_count"] == 2
    assert len(status["runtime_queue_item"]["steps"]) == 2


def test_runtime_claim_consumes_planned_runtime_queue_item(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        planner_bridge=WorkPackagePlannerBridge(planner=_Planner()),
    )
    submitted = operator.submit_package(_payload())
    claimed = operator.queue.claim_next()
    assert claimed["status"] == "running"
    assert claimed["runtime_state"]["task"] == submitted["runtime_queue_item"]
    assert claimed["runtime_state"]["steps"] == submitted["planning_snapshot"]["executable_steps"]


def test_default_bridge_produces_real_nonempty_plan(tmp_path: Path) -> None:
    result = RuntimeWorkPackageOperator(repo_root=tmp_path).submit_package(_payload("default-plan"))
    assert result["planning_status"] == "planned"
    assert result["planning_snapshot"]["task_graph_summary"]["node_count"] > 0
    assert result["planning_snapshot"]["executable_steps"]


def test_force_read_file_only_generates_read_file_steps(tmp_path: Path) -> None:
    payload = _payload("readonly-plan")
    payload["target_files"] = [
        "core/runtime/work_package_operator.py",
        "core/planning/work_package_planner_bridge.py",
    ]
    payload["metadata"] = {"force_read_file_only": True}

    operator = RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        planner_bridge=WorkPackagePlannerBridge(planner=_Planner()),
    )
    result = operator.submit_package(payload)

    assert result["planning_status"] == "planned"
    steps = result["planning_snapshot"]["executable_steps"]
    assert [step["type"] for step in steps] == ["read_file", "read_file"]
    assert [step["path"] for step in steps] == payload["target_files"]
    assert result["planning_snapshot"]["task_graph_summary"]["step_types"] == ["read_file", "read_file"]
    assert result["runtime_queue_item"]["steps"] == steps


def test_force_read_file_only_does_not_affect_normal_packages(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        planner_bridge=WorkPackagePlannerBridge(planner=_Planner()),
    )
    result = operator.submit_package(_payload("normal-plan"))

    assert result["planning_status"] == "planned"
    assert [step["type"] for step in result["planning_snapshot"]["executable_steps"]] == ["llm", "llm"]


def test_cli_status_is_json_and_contains_planning_summary(tmp_path: Path) -> None:
    package_file = tmp_path / "package.json"
    package_file.write_text(json.dumps(_payload()), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    submit = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.work_package_cli",
            "--repo-root",
            str(tmp_path),
            "submit",
            str(package_file),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    status = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.work_package_cli",
            "--repo-root",
            str(tmp_path),
            "status",
            "adaptive-package",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert submit.returncode == status.returncode == 0
    payload = json.loads(status.stdout)
    assert payload["result"]["planning_status"] == "planned"
    assert payload["result"]["task_graph_summary"]["node_count"] > 0


def test_bridge_operator_and_cli_do_not_directly_execute_steps() -> None:
    for relative in (
        "core/planning/work_package_planner_bridge.py",
        "core/runtime/work_package_operator.py",
        "cli/work_package_cli.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert "StepExecutor" not in source
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"execute_step", "execute_steps"}
        ]
