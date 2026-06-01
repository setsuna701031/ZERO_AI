from __future__ import annotations

from pathlib import Path

from core.tasks.work_package_intake import submit_work_package


def _write_target(repo_root: Path) -> None:
    target = repo_root / "core/agent/agent_loop.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "def run():\n"
        "    previous_result = None\n"
        "    return previous_result\n",
        encoding="utf-8",
    )


def test_explore_mode_is_readonly_audit(tmp_path: Path) -> None:
    _write_target(tmp_path)
    target = tmp_path / "core/agent/agent_loop.py"
    before = target.read_text(encoding="utf-8")

    result = submit_work_package(
        {
            "package_id": "explore_audit",
            "kind": "readonly_audit",
            "mode": "explore",
            "title": "Explore legacy paths",
            "scope_paths": ["core/agent/agent_loop.py"],
            "report_path": "workspace/explore_audit.md",
        },
        repo_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["mode"] == "explore"
    assert result["readonly"] is True
    assert result["mutation_allowed"] is False
    assert result["finding_count"] >= 1
    assert target.read_text(encoding="utf-8") == before
    assert (tmp_path / "workspace/explore_audit.md").exists()


def test_plan_mode_builds_plan_without_mutation(tmp_path: Path) -> None:
    _write_target(tmp_path)
    target = tmp_path / "core/agent/agent_loop.py"
    before = target.read_text(encoding="utf-8")

    result = submit_work_package(
        {
            "package_id": "plan_cleanup",
            "kind": "readonly_audit",
            "mode": "plan",
            "title": "Plan legacy cleanup",
            "scope_paths": ["core/agent/agent_loop.py"],
            "report_path": "workspace/plan_cleanup.md",
        },
        repo_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["mode"] == "plan"
    assert result["readonly"] is True
    assert result["mutation_allowed"] is False
    assert result["plan"]["reason"] == "plan_mode_readonly"
    assert "propose_cleanup_boundaries" in result["plan"]["actions"]
    assert target.read_text(encoding="utf-8") == before
    assert "Plan legacy cleanup" in (tmp_path / "workspace/plan_cleanup.md").read_text(encoding="utf-8")


def test_execute_mode_requires_approval_and_blocks_without_mutation(tmp_path: Path) -> None:
    _write_target(tmp_path)
    target = tmp_path / "core/agent/agent_loop.py"
    before = target.read_text(encoding="utf-8")

    result = submit_work_package(
        {
            "package_id": "execute_cleanup",
            "kind": "readonly_audit",
            "mode": "execute",
            "title": "Execute legacy cleanup",
            "scope_paths": ["core/agent/agent_loop.py"],
            "report_path": "workspace/execute_cleanup.md",
            "approval": False,
        },
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["mode"] == "execute"
    assert result["blocked"] is True
    assert result["approval_required"] is True
    assert result["mutation_allowed"] is False
    assert result["reason"] == "execute_requires_approval"
    assert target.read_text(encoding="utf-8") == before


def test_verify_mode_blocks_mutation_and_writes_report(tmp_path: Path) -> None:
    _write_target(tmp_path)
    target = tmp_path / "core/agent/agent_loop.py"
    before = target.read_text(encoding="utf-8")

    result = submit_work_package(
        {
            "package_id": "verify_cleanup",
            "kind": "readonly_audit",
            "mode": "verify",
            "title": "Verify cleanup",
            "scope_paths": ["core/agent/agent_loop.py"],
            "report_path": "workspace/verify_cleanup.md",
        },
        repo_root=tmp_path,
    )

    assert result["ok"] is True
    assert result["mode"] == "verify"
    assert result["readonly"] is True
    assert result["mutation_allowed"] is False
    assert result["plan"]["reason"] == "verify_mode_no_mutation"
    assert "run_allowed_validation_commands" in result["plan"]["actions"]
    assert target.read_text(encoding="utf-8") == before
    assert (tmp_path / "workspace/verify_cleanup.md").exists()
