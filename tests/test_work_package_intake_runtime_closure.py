from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.runtime.work_package_queue import RuntimePackageQueue, RuntimePackageQueueError
from core.runtime.runtime_authority_seal import (

    _RUNTIME_DISPATCHER_ISSUER_TOKEN,
    issue_work_package_completion_authority,
)
from core.tasks.work_package_runtime_intake import build_package_record, validate_package
pytestmark = [pytest.mark.integration]



ROOT = Path(__file__).resolve().parents[1]


def _payload(package_id: str = "closure-package") -> dict:
    return {
        "package_id": package_id,
        "title": "Runtime intake closure",
        "goal": "Queue a complete engineering work package",
        "description": "Preserve the operator contract for runtime execution.",
        "target_files": ["core/runtime/work_package_queue.py"],
        "requirements": ["queue", "status"],
        "hard_boundary": ["no direct execution"],
        "non_mainline_issue_reporting": ["report only"],
        "validation_commands": ["python -m pytest tests/test_work_package_intake_runtime_closure.py -q"],
        "completion_report_format": ["pytest result"],
    }


def test_submit_package_creates_queued_package_with_stable_id(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    first = operator.submit_package(_payload())
    second = operator.submit_package(_payload())
    assert first["status"] == "queued"
    assert first["package_id"] == second["package_id"] == "closure-package"
    assert first["execution_path"]["direct_execution"] is False
    assert first["execution_path"]["runtime_owns_execution"] is True
    assert first["execution_path"]["taskrunner_required"] is True
    assert first["execution_path"]["step_executor_endpoint_only"] is True
    assert first["execution_path"]["authority_path"] == (
        "WorkPackageIntake -> RuntimePackageQueue -> "
        "RuntimeDispatcher -> TaskRunner -> StepExecutor"
    )


def test_generated_package_id_is_stable() -> None:
    payload = _payload()
    payload.pop("package_id")
    assert build_package_record(payload).package_id == build_package_record(payload).package_id


def test_missing_hard_boundary_warns_without_fake_contract_completion() -> None:
    payload = _payload()
    payload.pop("hard_boundary")
    validation = validate_package(payload)
    package = build_package_record(payload).to_dict()
    assert validation["valid"] is True
    assert validation["contract_complete"] is False
    assert package["hard_boundary"] is None
    assert package["warnings"] == ["missing_hard_boundary"]
    assert package["metadata"]["contract_complete"] is False


def test_contract_fields_are_preserved() -> None:
    package = build_package_record(_payload()).to_dict()
    assert package["non_mainline_issue_reporting"] == ["report only"]
    assert package["validation_commands"] == [
        "python -m pytest tests/test_work_package_intake_runtime_closure.py -q"
    ]


def test_status_returns_progress_snapshot(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    operator.submit_package(_payload())
    status = operator.package_status("closure-package")
    assert set(status) >= {
        "package_id",
        "status",
        "current_step",
        "step_count",
        "completion_percent",
        "lifecycle_state",
        "last_transition",
        "runtime_state",
        "blocked_reason",
        "validation_summary",
        "non_mainline_findings",
    }


def test_pause_resume_cancel_and_terminal_rules(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    operator.submit_package(_payload())
    assert operator.pause_package("closure-package")["status"] == "paused"
    assert operator.resume_package("closure-package")["status"] == "queued"
    assert operator.cancel_package("closure-package")["status"] == "cancelled"
    with pytest.raises(RuntimePackageQueueError, match="terminal_package_cannot_resume"):
        operator.resume_package("closure-package")


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
def test_terminal_packages_cannot_resume(tmp_path: Path, terminal: str) -> None:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    queue.enqueue(build_package_record(_payload(terminal)))
    if terminal == "completed":
        queue.complete(
            terminal,
            completion_authority=issue_work_package_completion_authority(
                _RUNTIME_DISPATCHER_ISSUER_TOKEN,
                package_id=terminal,
            ),
        )
    elif terminal == "failed":
        queue.fail(terminal, reason="failure")
    else:
        queue.cancel(terminal)
    with pytest.raises(RuntimePackageQueueError):
        queue.resume(terminal)


def test_operator_api_has_no_direct_step_executor_dependency() -> None:
    path = ROOT / "core/runtime/work_package_operator.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "StepExecutor" not in source
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"execute_step", "execute_steps"}
    ]


def test_cli_submit_and_status_emit_json(tmp_path: Path) -> None:
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
            "closure-package",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert submit.returncode == status.returncode == 0
    assert json.loads(submit.stdout)["result"]["status"] == "queued"
    assert json.loads(status.stdout)["result"]["package_id"] == "closure-package"
