from __future__ import annotations

from pathlib import Path
from typing import Any

from core.tasks.work_package_intake import submit_work_package


def _execute_payload(
    *,
    package_id: str,
    operation: str,
    target_path: str,
    content: str = "x = 1\n",
    approval: bool = True,
) -> dict[str, Any]:
    return {
        "package_id": package_id,
        "kind": "controlled_core_write_test",
        "title": package_id,
        "mode": "execute",
        "approval": approval,
        "mutation_allowed": True,
        "readonly": False,
        "scope_paths": [target_path],
        "report_path": f"workspace/reports/{package_id}.md",
        "edit": {
            "operation": operation,
            "target_path": target_path,
            "content": content,
        },
    }


def test_execute_approval_true_allows_work_package_core_write(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="allow_work_package_core_write",
            operation="write_file",
            target_path="core/tasks/work_package_generated.py",
            content="# generated\n",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["blocked"] is False
    assert result["reason"] == "controlled_write_execution_completed"
    assert result["evidence"]["guard"] == "controlled_core_write_v6_3"
    assert result["evidence"]["policy_reason"] == "controlled_core_write_allowed"
    assert result["changed_files"] == ["core/tasks/work_package_generated.py"]
    assert (tmp_path / "core/tasks/work_package_generated.py").read_text(encoding="utf-8") == "# generated\n"
    assert (tmp_path / result["report_path"]).exists()


def test_execute_approval_false_blocks_work_package_core_write(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="block_without_approval",
            operation="write_file",
            target_path="core/tasks/work_package_generated.py",
            content="# generated\n",
            approval=False,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["approval_required"] is True
    assert result["reason"] == "execute_requires_approval"
    assert not (tmp_path / "core/tasks/work_package_generated.py").exists()


def test_execute_approval_true_blocks_runtime_path(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="block_runtime",
            operation="write_file",
            target_path="core/runtime/x.py",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["reason"] == "blocked_target_prefix:core/runtime"
    assert not (tmp_path / "core/runtime/x.py").exists()


def test_execute_approval_true_blocks_agent_path(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="block_agent",
            operation="write_file",
            target_path="core/agent/x.py",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["reason"] == "blocked_target_prefix:core/agent"
    assert not (tmp_path / "core/agent/x.py").exists()


def test_execute_approval_true_blocks_scheduler_path(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="block_scheduler",
            operation="write_file",
            target_path="core/tasks/scheduler.py",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["reason"] == "blocked_target_prefix:core/tasks/scheduler.py"
    assert not (tmp_path / "core/tasks/scheduler.py").exists()


def test_execute_approval_true_blocks_tests_path(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="block_tests",
            operation="write_file",
            target_path="tests/x.py",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["reason"] == "blocked_target_prefix:tests"
    assert not (tmp_path / "tests/x.py").exists()


def test_execute_approval_true_blocks_path_escape(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="block_escape",
            operation="write_file",
            target_path="../escape.py",
            content="bad\n",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["reason"] == "path_must_not_escape_repo"
    assert not (tmp_path.parent / "escape.py").exists()


def test_blocked_result_has_explicit_reason(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="blocked_reason",
            operation="write_file",
            target_path="core/runtime/x.py",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert isinstance(result["reason"], str)
    assert result["reason"]
    assert result["error"] == result["reason"]


def test_allowed_write_emits_evidence_and_report(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="evidence_record",
            operation="write_file",
            target_path="core/tasks/work_package_generated.py",
            content="# evidence\n",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    evidence = result["evidence"]
    assert evidence["schema"] == "zero.work_package.controlled_write_execution_evidence.v6_3"
    assert evidence["package_id"] == "evidence_record"
    assert evidence["operation"] == "write_file"
    assert evidence["target_path"] == "core/tasks/work_package_generated.py"
    assert evidence["approval"] is True
    assert evidence["changed"] is True
    assert evidence["after_size"] == len("# evidence\n")
    assert (tmp_path / result["report_path"]).exists()
    assert "Evidence" in (tmp_path / result["report_path"]).read_text(encoding="utf-8")
