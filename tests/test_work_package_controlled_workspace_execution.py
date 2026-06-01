from __future__ import annotations

from pathlib import Path

from core.tasks.work_package_intake import submit_work_package
from core.tasks.work_package_scheduler import WorkPackageScheduler


def _execute_payload(
    *,
    package_id: str,
    operation: str,
    target_path: str,
    content: str,
    approval: bool = True,
    scope_path: str | None = None,
) -> dict[str, object]:
    return {
        "package_id": package_id,
        "kind": "readonly_audit",
        "mode": "execute",
        "title": "Controlled workspace execution",
        "scope_paths": [scope_path or target_path],
        "report_path": f"workspace/{package_id}_report.md",
        "approval": approval,
        "edit": {
            "operation": operation,
            "target_path": target_path,
            "content": content,
        },
    }


def test_execute_requires_approval_before_workspace_write(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="blocked_no_approval",
            operation="write_file",
            target_path="workspace/no_approval.txt",
            content="blocked",
            approval=False,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["approval_required"] is True
    assert not (tmp_path / "workspace/no_approval.txt").exists()


def test_execute_blocks_core_files_even_with_approval(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="blocked_core",
            operation="write_file",
            target_path="core/agent/agent_loop.py",
            content="bad",
            approval=True,
            scope_path="workspace/declared_scope.txt",
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert "blocked_target_prefix:core" in result["reason"]
    assert not (tmp_path / "core/agent/agent_loop.py").exists()


def test_execute_blocks_path_escape(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="blocked_escape",
            operation="write_file",
            target_path="../escape.txt",
            content="bad",
            approval=True,
            scope_path="workspace/declared_scope.txt",
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert "path_must_not_escape_repo" in result["reason"]


def test_execute_write_file_allows_workspace_target_and_generates_evidence(tmp_path: Path) -> None:
    result = submit_work_package(
        _execute_payload(
            package_id="write_workspace",
            operation="write_file",
            target_path="workspace/output.txt",
            content="hello",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["reason"] == "controlled_workspace_execution_completed"
    assert result["changed_files"] == ["workspace/output.txt"]
    assert result["evidence"]["guard"] == "workspace_only"
    assert result["evidence"]["changed"] is True
    assert (tmp_path / "workspace/output.txt").read_text(encoding="utf-8") == "hello"
    assert (tmp_path / "workspace/write_workspace_report.md").exists()


def test_execute_append_file_allows_workspace_target(tmp_path: Path) -> None:
    target = tmp_path / "workspace/log.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("a", encoding="utf-8")

    result = submit_work_package(
        _execute_payload(
            package_id="append_workspace",
            operation="append_file",
            target_path="workspace/log.txt",
            content="b",
            approval=True,
        ),
        repo_root=tmp_path,
    )

    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "ab"


def test_scheduler_runs_controlled_workspace_execute_package(tmp_path: Path) -> None:
    scheduler = WorkPackageScheduler(repo_root=tmp_path)

    result = scheduler.submit(
        _execute_payload(
            package_id="scheduler_execute_workspace",
            operation="create_file",
            target_path="workspace/scheduler_created.txt",
            content="created by scheduler",
            approval=True,
        )
    )

    assert result["status"] == "completed"
    assert result["result"]["ok"] is True
    assert (tmp_path / "workspace/scheduler_created.txt").read_text(encoding="utf-8") == "created by scheduler"
