from __future__ import annotations

from pathlib import Path

import pytest

from core.tasks.work_package_contract import (
    WorkPackageContractError,
    validate_work_package_request,
)
from core.tasks.work_package_intake import submit_legacy_path_audit_package, submit_work_package


def test_work_package_contract_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(WorkPackageContractError):
        validate_work_package_request(
            {
                "package_id": "bad",
                "kind": "readonly_audit",
                "scope_paths": ["../outside.py"],
                "report_path": "workspace/report.md",
            }
        )


def test_readonly_audit_package_writes_report_without_mutating_scope(tmp_path: Path) -> None:
    repo_root = tmp_path
    source = repo_root / "core/agent/agent_component_invoker.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    original_text = "\n".join(
        [
            "def invoke():",
            "    previous_result = None",
            "    try:",
            "        return runner(previous_result=previous_result)",
            "    except TypeError:",
            "        return legacy_adapter()",
            "",
        ]
    )
    source.write_text(original_text, encoding="utf-8")

    result = submit_work_package(
        {
            "package_id": "legacy_path_audit",
            "kind": "readonly_audit",
            "title": "Read-only legacy path audit",
            "scope_paths": ["core/agent/agent_component_invoker.py"],
            "markers": ["previous_result", "except TypeError", "legacy", "adapter"],
            "report_path": "workspace/legacy_path_audit.md",
        },
        repo_root=repo_root,
    )

    assert result["ok"] is True
    assert result["mutation_allowed"] is False
    assert result["report_path"] == "workspace/legacy_path_audit.md"
    assert result["finding_count"] >= 3

    report = repo_root / "workspace/legacy_path_audit.md"
    assert report.exists()
    report_text = report.read_text(encoding="utf-8")
    assert "Read-only legacy path audit" in report_text
    assert "previous_result" in report_text
    assert "except TypeError" in report_text
    assert "Mutation allowed: `false`" in report_text

    assert source.read_text(encoding="utf-8") == original_text


def test_legacy_path_audit_convenience_entrypoint(tmp_path: Path) -> None:
    repo_root = tmp_path
    target = repo_root / "core/runtime/planner_step_executor_adapter.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "def run():\n"
        "    adapter = None\n"
        "    previous_result = None\n",
        encoding="utf-8",
    )

    result = submit_legacy_path_audit_package(
        repo_root=repo_root,
        scope_paths=["core/runtime/planner_step_executor_adapter.py"],
        report_path="workspace/legacy_path_audit.md",
        instructions="Classify only; do not edit files.",
    )

    assert result["ok"] is True
    assert result["kind"] == "readonly_audit"
    assert result["finding_count"] >= 2

    report_text = (repo_root / "workspace/legacy_path_audit.md").read_text(encoding="utf-8")
    assert "Classify only; do not edit files." in report_text
    assert "core/runtime/planner_step_executor_adapter.py" in report_text


def test_readonly_audit_reports_missing_scope(tmp_path: Path) -> None:
    result = submit_work_package(
        {
            "package_id": "missing_audit",
            "kind": "readonly_audit",
            "scope_paths": ["core/missing.py"],
            "report_path": "workspace/missing_report.md",
        },
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["missing_paths"] == ["core/missing.py"]
    assert (tmp_path / "workspace/missing_report.md").exists()
