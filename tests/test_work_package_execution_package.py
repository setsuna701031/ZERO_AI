from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.runtime.work_package_operator import RuntimeWorkPackageOperator


ROOT = Path(__file__).resolve().parents[1]


def _payload(package_id: str = "execution-package-v1") -> dict:
    return {
        "package_id": package_id,
        "title": "Execution package V1",
        "goal": "Convert an approved proposal into an execution package",
        "description": "Produce package artifacts without mutating the repository.",
        "target_files": ["core/runtime/work_package_operator.py"],
        "requirements": ["approval model", "execution package artifact"],
        "hard_boundary": ["do not mutate repo"],
        "non_mainline_issue_reporting": ["report all"],
        "validation_commands": [
            "python -m pytest tests/test_work_package_execution_package.py -q"
        ],
        "completion_report_format": ["execution package summary"],
    }


def test_approve_proposal_records_readonly_approval_model(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    operator.submit_package(_payload())

    result = operator.approve_proposal("execution-package-v1")
    record = operator.queue.status("execution-package-v1")

    approval = result["approval"]
    assert approval["package_id"] == "execution-package-v1"
    assert approval["proposal_id"] == record["execution_proposal"]["proposal_id"]
    assert approval["approved"] is True
    assert approval["approved_by"] == "operator"
    assert approval["approved_at"]
    assert approval["approval_scope"] == "execution_package_generation"
    assert approval["mutation_allowed"] is False
    assert record["approval_status"]["approved"] is True
    assert record["approval_status"]["mutation_allowed"] is False


def test_execution_package_requires_approved_proposal(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    operator.submit_package(_payload())

    with pytest.raises(PermissionError, match="proposal_approval_required"):
        operator.execution_package("execution-package-v1")


def test_execution_package_is_recorded_without_repo_mutation_authority(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    submitted = operator.submit_package(_payload())
    operator.approve_proposal("execution-package-v1")

    result = operator.execution_package("execution-package-v1")
    package = result["execution_package"]
    record = operator.queue.status("execution-package-v1")

    assert package["schema"] == "zero.work_package.execution_package.v1"
    assert package["package_id"] == "execution-package-v1"
    assert package["objective"] == _payload()["goal"]
    assert package["approved_proposal"]["proposal_id"] == record["execution_proposal"]["proposal_id"]
    assert package["executable_steps"]
    assert package["validation_commands"] == _payload()["validation_commands"]
    assert package["mutation_allowed"] is False
    assert package["required_operator_approval"] is True
    assert package["non_mainline_reporting_enabled"] is True
    assert package["repo_mutation_performed_by_zero"] is False
    assert record["execution_package"] == package
    assert record["execution_package_summary"]["step_count"] == len(package["executable_steps"])
    assert record["runtime_queue_item"] == submitted["runtime_queue_item"]


def test_report_includes_proposal_approval_and_execution_package_sections(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    operator.submit_package(_payload())
    operator.approve_proposal("execution-package-v1")
    operator.execution_package("execution-package-v1")

    report = operator.package_report("execution-package-v1")

    assert report["proposal_summary"]["proposal_id"]
    assert report["approval_status"]["approved"] is True
    assert report["approval_status"]["mutation_allowed"] is False
    assert report["execution_package_summary"]["created"] is True
    assert report["execution_package_summary"]["mutation_allowed"] is False


def test_cli_approval_execution_package_and_report_markdown(tmp_path: Path) -> None:
    package_file = tmp_path / "package.json"
    package_file.write_text(json.dumps(_payload()), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.work_package_cli",
                "--repo-root",
                str(tmp_path),
                *args,
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    assert run("submit", str(package_file)).returncode == 0
    approval = run("approve-proposal", "execution-package-v1")
    execution = run("execution-package", "execution-package-v1")
    report = run("report", "execution-package-v1", "--format", "markdown")

    assert approval.returncode == execution.returncode == report.returncode == 0
    assert json.loads(approval.stdout)["result"]["approval"]["mutation_allowed"] is False
    assert json.loads(execution.stdout)["result"]["execution_package"]["mutation_allowed"] is False
    assert "## Proposal Summary" in report.stdout
    assert "## Approval Status" in report.stdout
    assert "## Execution Package Summary" in report.stdout
