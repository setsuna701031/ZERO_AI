from __future__ import annotations

from core.reports.engineering_report_contract import (

    NOT_SAFE_TO_PUSH,
    PUSH_AFTER_REVIEW,
    SAFE_TO_PUSH,
    attach_engineering_report,
    build_engineering_report,
    validate_engineering_report,
)
from core.reports.engineering_report_formatter import format_engineering_report
from core.runtime.planner_runtime_dispatch import dispatch_planner_result_to_persistent_runtime
from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.tasks.engineering_task_runner import run_engineering_task
import pytest

pytestmark = [pytest.mark.contract]



def test_engineering_report_contains_all_operator_usable_sections() -> None:
    report = build_engineering_report(
        {
            "ok": True,
            "status": "completed",
            "completed": ["Implemented shared report formatter"],
            "root_cause": "Engineering results lacked a stable delivery contract.",
            "changed_files": ["core/reports/engineering_report_contract.py"],
            "added_updated_tests": ["tests/test_engineering_report_usability_contract.py"],
            "validation_results": [{"name": "contract tests", "ok": True, "status": "passed"}],
            "execution_path": {"owner": "report_formatter", "authority": "report_only"},
            "commands_to_run": ["python -m pytest tests/test_engineering_report_usability_contract.py -q"],
        }
    )

    assert validate_engineering_report(report)["ok"] is True
    assert report["safe_to_push"] == SAFE_TO_PUSH
    assert report["hard_engineering_boundary"]["truthful_status_required"] is True
    assert report["next_action_package"]["prompt"].startswith("Objective:")
    assert "Commands To Run:" in report["next_action_package"]["prompt"]

    markdown = format_engineering_report(report)
    for heading in (
        "Current Status",
        "Completed",
        "Root Cause",
        "Ownership / Authority / Path Contract Map",
        "Modified Files",
        "Added/Updated Tests",
        "Validation Results",
        "Remaining Failures",
        "Non-Mainline Findings",
        "Safe To Push",
        "Next Action Package",
        "Commands To Run",
    ):
        assert f"## {heading}" in markdown


def test_remaining_failure_contract_is_complete_and_blocks_push() -> None:
    report = build_engineering_report(
        {
            "ok": False,
            "status": "failed",
            "safe_to_push": SAFE_TO_PUSH,
            "remaining_failures": [
                {
                    "test_file": "tests/test_runtime.py",
                    "line": 42,
                    "expected": "status == completed",
                    "actual": "status == failed",
                    "suspected_layer": "runtime_dispatcher",
                    "mainline_blocker": True,
                }
            ],
        }
    )

    failure = report["remaining_failures"][0]
    assert failure == {
        "test_file": "tests/test_runtime.py",
        "line": 42,
        "expected": "status == completed",
        "actual": "status == failed",
        "suspected_layer": "runtime_dispatcher",
        "classification": "mainline_blocker",
        "mainline_blocker": True,
    }
    assert report["safe_to_push"] == NOT_SAFE_TO_PUSH
    assert "tests/test_runtime.py:42" in report["next_action_package"]["prompt"]


def test_non_mainline_finding_is_preserved_and_requires_review() -> None:
    report = build_engineering_report(
        {
            "ok": True,
            "status": "completed",
            "non_mainline_findings": [
                {
                    "test_file": "tests/test_legacy_route.py",
                    "line": 103,
                    "expected": "mode is present",
                    "actual": "mode is missing",
                    "suspected_layer": "AgentLoop legacy route",
                }
            ],
        }
    )

    assert report["remaining_failures"] == []
    assert report["non_mainline_findings"][0]["classification"] == "non_mainline_finding"
    assert report["safe_to_push"] == PUSH_AFTER_REVIEW


def test_attach_engineering_report_preserves_existing_result_fields() -> None:
    attached = attach_engineering_report(
        {
            "ok": True,
            "package_id": "wp-report",
            "status": "completed",
            "changed_files": ["workspace/shared/result.txt"],
        },
        report_type="work_package",
    )

    assert attached["package_id"] == "wp-report"
    assert attached["engineering_report"]["report_type"] == "work_package"
    assert attached["engineering_report_markdown"].startswith("# ZERO Engineering Report")


def test_engineering_task_public_result_attaches_usability_report(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "core.tasks.engineering_task_runner._run_single_engineering_task",
        lambda payload, *, repo_root: {
            "ok": True,
            "status": "completed",
            "package_id": "engineering-report",
            "changed_files": ["workspace/shared/result.txt"],
        },
    )

    result = run_engineering_task(
        {"task_id": "engineering-report", "target_path": "workspace/shared/result.txt", "operation": "write_file"},
        repo_root=tmp_path,
    )

    assert result["engineering_report"]["report_type"] == "engineering"
    assert result["engineering_report"]["contract_validation"]["ok"] is True


def test_aer_dispatch_record_attaches_usability_report(tmp_path) -> None:
    result = dispatch_planner_result_to_persistent_runtime(
        repo_root=tmp_path,
        user_input="Persistent Autonomous Engineering Runtime report contract",
        planner_result={
            "persistent_runtime": True,
            "steps": [{"type": "inspect", "description": "inspect report contract"}],
        },
    )

    report = result["planner_runtime_dispatch"]["engineering_report"]
    assert report["report_type"] == "aer"
    assert report["contract_validation"]["ok"] is True


def test_work_package_operator_report_attaches_usability_report() -> None:
    class Queue:
        @staticmethod
        def runtime_progress(package_id):
            return {
                "package_id": package_id,
                "lifecycle_state": "completed",
                "planning_status": "planned",
                "completed_steps": 1,
                "failed_steps": 0,
                "remaining_steps": 0,
                "percent": 100,
                "task_graph_summary": {"step_types": ["write_file"]},
            }

    operator = object.__new__(RuntimeWorkPackageOperator)
    operator.queue = Queue()

    report_result = operator.package_report("wp-report")

    assert report_result["engineering_report"]["report_type"] == "work_package"
    assert report_result["engineering_report"]["contract_validation"]["ok"] is True
