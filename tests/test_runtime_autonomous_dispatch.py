from __future__ import annotations

import ast
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
from core.runtime.runtime_dispatcher import RuntimeDispatcher, validate_runtime_transition
from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.runtime.work_package_queue import RuntimePackageQueue
import pytest

pytestmark = [pytest.mark.integration]




ROOT = Path(__file__).resolve().parents[1]


def _payload(package_id: str = "dispatch-package") -> dict:
    return {
        "package_id": package_id,
        "title": "Runtime autonomous dispatch",
        "goal": "Dispatch every planned runtime step",
        "description": "Exercise runtime progress and evidence closure.",
        "target_files": ["core/runtime/runtime_dispatcher.py"],
        "requirements": ["dispatch", "progress", "evidence"],
        "hard_boundary": ["TaskRunner required", "no direct StepExecutor"],
        "non_mainline_issue_reporting": ["report only"],
        "validation_commands": ["python -m pytest tests/test_runtime_autonomous_dispatch.py -q"],
        "completion_report_format": ["runtime progress"],
    }


class _Planner:
    def plan(self, **_kwargs):
        return {
            "ok": True,
            "steps": [
                {"id": "step-1", "type": "inspect"},
                {"id": "step-2", "type": "verify"},
                {"id": "step-3", "type": "respond"},
            ],
            "meta": {"semantic_type": "multi_step_task"},
        }


class _SequenceTaskRunner:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or ["running", "running", "finished"])
        self.calls = []

    def run_task(self, *, task, current_tick=0, **_kwargs):
        self.calls.append(copy.deepcopy(task))
        status = self.outcomes[current_tick]
        ok = status not in {"failed", "blocked"}
        current = current_tick + 1
        evidence = {"ref": f"evidence:{current}", "authority": task["execution_authority"]}
        return {
            "ok": ok,
            "status": status,
            "current_step_index": current,
            "error": None if ok else f"{status}:step-{current}",
            "task": {**copy.deepcopy(task), "current_step_index": current, "status": status},
            "runtime_state": {
                "status": status,
                "current_step_index": current,
                "results": [{"step_index": current - 1, "result": evidence}],
            },
            "evidence_refs": [evidence["ref"]],
        }


def _operator(tmp_path: Path, runner: _SequenceTaskRunner) -> RuntimeWorkPackageOperator:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    dispatcher = RuntimeDispatcher(
        queue=queue,
        task_runner=runner,
        workspace_root=tmp_path / "workspace",
    )
    return RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        queue=queue,
        planner_bridge=WorkPackagePlannerBridge(planner=_Planner()),
        dispatcher=dispatcher,
    )


def test_dispatch_autonomously_runs_all_steps_and_completes(tmp_path: Path) -> None:
    runner = _SequenceTaskRunner()
    operator = _operator(tmp_path, runner)
    operator.submit_package(_payload())
    result = operator.run_package("dispatch-package")
    assert len(runner.calls) == 3
    assert result["status"] == "completed"
    assert result["runtime_lifecycle_state"] == "completed"
    assert [item["to"] for item in result["runtime_lifecycle_history"]] == [
        "planned",
        "claimed",
        "executing",
        "executing",
        "executing",
        "executing",
        "completed",
    ]


def test_progress_updates_after_each_step(tmp_path: Path) -> None:
    operator = _operator(tmp_path, _SequenceTaskRunner())
    operator.submit_package(_payload())
    operator.run_package("dispatch-package")
    progress = operator.package_progress("dispatch-package")
    assert progress["runtime_status"] == "completed"
    assert progress["current_step"] == 3
    assert progress["completed_steps"] == 3
    assert progress["failed_steps"] == 0
    assert progress["remaining_steps"] == 0
    assert progress["percent"] == 100


def test_failure_preserves_root_cause_evidence_and_does_not_fake_success(tmp_path: Path) -> None:
    operator = _operator(tmp_path, _SequenceTaskRunner(["running", "failed", "finished"]))
    operator.submit_package(_payload("failed-package"))
    result = operator.run_package("failed-package")
    assert result["status"] == "failed"
    assert result["runtime_lifecycle_state"] == "failed"
    assert "failed:step-2" in result["root_cause"]
    assert len(result["execution_evidence"]) >= 2
    assert result["progress"]["completed_steps"] == 1
    assert result["progress"]["failed_steps"] == 1
    assert result["progress"]["completion_percent"] < 100


def test_blocked_result_stops_next_step_and_preserves_evidence(tmp_path: Path) -> None:
    runner = _SequenceTaskRunner(["blocked", "running", "finished"])
    operator = _operator(tmp_path, runner)
    operator.submit_package(_payload("blocked-package"))
    result = operator.run_package("blocked-package")
    assert len(runner.calls) == 1
    assert result["status"] == "blocked"
    assert result["runtime_lifecycle_state"] == "blocked"
    assert result["blocked_reason"]
    assert result["execution_evidence"]


def test_authority_and_identity_are_preserved_through_taskrunner(tmp_path: Path) -> None:
    runner = _SequenceTaskRunner()
    operator = _operator(tmp_path, runner)
    submitted = operator.submit_package(_payload())
    result = operator.run_package("dispatch-package")
    task = runner.calls[0]
    assert task["package_id"] == submitted["package_id"]
    assert task["session_id"] == submitted["session_id"]
    assert task["task_id"] == submitted["task_id"]
    assert task["execution_authority"]["authority_source"] == "runtime_dispatcher"
    assert task["execution_authority"]["execution_authority_endpoint"] == "step_executor"
    assert task["authority_context"]["authority_chain"][0]["layer"] == "runtime_dispatcher"
    assert result["execution_session"]["authority"] == task["execution_authority"]


def test_runtime_lifecycle_transition_validation() -> None:
    assert validate_runtime_transition("planned", "claimed") is True
    assert validate_runtime_transition("claimed", "executing") is True
    assert validate_runtime_transition("executing", "completed") is True
    assert validate_runtime_transition("completed", "executing") is False
    assert validate_runtime_transition("failed", "claimed") is False


def test_cli_progress_is_machine_readable_json(tmp_path: Path) -> None:
    package_file = tmp_path / "package.json"
    package_file.write_text(json.dumps(_payload()), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    submit = subprocess.run(
        [sys.executable, "-m", "cli.work_package_cli", "--repo-root", str(tmp_path), "submit", str(package_file)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    progress = subprocess.run(
        [sys.executable, "-m", "cli.work_package_cli", "--repo-root", str(tmp_path), "progress", "dispatch-package"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert submit.returncode == progress.returncode == 0
    payload = json.loads(progress.stdout)
    assert payload["result"]["planning_status"] == "planned"
    assert payload["result"]["runtime_status"] == "planned"


def test_cli_run_dispatches_and_returns_machine_readable_terminal_json(tmp_path: Path) -> None:
    package_file = tmp_path / "package.json"
    package_file.write_text(json.dumps(_payload("cli-run-package")), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    subprocess.run(
        [sys.executable, "-m", "cli.work_package_cli", "--repo-root", str(tmp_path), "submit", str(package_file)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    run = subprocess.run(
        [sys.executable, "-m", "cli.work_package_cli", "--repo-root", str(tmp_path), "run", "cli-run-package"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(run.stdout)
    assert run.returncode == 0
    assert payload["result"]["runtime_lifecycle_state"] in {"completed", "blocked", "failed"}
    assert payload["result"]["runtime_lifecycle_state"] != "planned"


def test_dispatcher_operator_and_cli_have_no_direct_step_executor_calls() -> None:
    for relative in (
        "core/runtime/runtime_dispatcher.py",
        "core/runtime/work_package_operator.py",
        "cli/work_package_cli.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and (
                (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "StepExecutor"
                )
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"execute_step", "execute_steps"}
                )
            )
        ]
