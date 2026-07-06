from __future__ import annotations

import json
import subprocess
from pathlib import Path

from core.runtime.runtime_git_commit_actuator import RuntimeGitCommitActuator
from core.runtime.runtime_governed_commit_adapter import RuntimeGovernedCommitAdapter


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _git(repo, "init").returncode == 0
    assert _git(repo, "config", "user.email", "zero@example.local").returncode == 0
    assert _git(repo, "config", "user.name", "ZERO Runtime").returncode == 0
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    assert _git(repo, "add", "-A").returncode == 0
    assert _git(repo, "commit", "-m", "initial").returncode == 0
    return repo


def _valid_governed_record() -> dict:
    return {
        "schema": "zero.runtime.governed_commit_record.v1",
        "package_id": "pkg-test",
        "task_id": "task-test",
        "run_id": "run-test",
        "adapter_status": "governed_recorded",
        "commit_applied": True,
        "commit_recorded": True,
        "git_diff_recorded": True,
        "validation_passed": True,
        "commit_allowed": True,
        "mutation_allowed": True,
        "controlled_mutation": True,
        "rollback_available": True,
        "real_executor_enabled": True,
        "non_mainline_issues": ["issue-preserved"],
        "evidence_files": [],
        "runtime_commit_apply_status": "governed_commit_recorded",
    }


def test_git_commit_actuator_blocks_without_governed_record(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    actuator = RuntimeGitCommitActuator(
        repo_root=repo,
        report_root=tmp_path / "reports",
    )

    result = actuator.apply_git_commit(
        governed_commit_record={},
        package_id="pkg-test",
        task_id="task-test",
        run_id="run-test",
    )

    assert result["commit_applied"] is False
    assert result["runtime_commit_apply_status"] == "blocked_no_governed_commit_record"
    assert result["denial_reason"] == "governed_commit_record_required"


def test_validation_failed_never_reaches_git_commit_record(tmp_path: Path) -> None:
    adapter = RuntimeGovernedCommitAdapter(report_root=tmp_path / "reports")
    result = adapter.apply_governed_commit(
        runtime_result={
            "validation_passed": False,
            "commit_allowed": True,
            "controlled_mutation": True,
            "mutation_allowed": True,
            "rollback_available": True,
            "real_executor_enabled": True,
        },
        package_id="pkg-test",
        task_id="task-test",
        run_id="run-test",
    )

    assert result["commit_applied"] is False
    assert result["commit_recorded"] is False
    assert result["runtime_commit_apply_status"] == "blocked_by_governed_commit_adapter"
    assert not (tmp_path / "reports" / "governed_commit_record.json").exists()


def test_git_commit_actuator_creates_commit_evidence_and_head_matches(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "runtime_change.txt").write_text("changed\n", encoding="utf-8")

    actuator = RuntimeGitCommitActuator(
        repo_root=repo,
        report_root=tmp_path / "reports",
    )
    result = actuator.apply_git_commit(
        governed_commit_record=_valid_governed_record(),
        package_id="pkg-test",
        task_id="task-test",
        run_id="run-test",
    )

    assert result["commit_applied"] is True
    assert result["runtime_commit_apply_status"] == "git_commit_applied"
    assert result["commit_id"]

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert result["commit_id"] == head

    evidence_path = Path(result["git_commit_actuator_record_path"])
    assert evidence_path.exists()

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["commit_id"] == head
    assert evidence["runtime_commit_apply_status"] == "git_commit_applied"
    assert evidence["non_mainline_issues"] == ["issue-preserved"]


def test_git_commit_actuator_no_diff_is_safe_noop(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    before = _git(repo, "rev-parse", "HEAD").stdout.strip()

    actuator = RuntimeGitCommitActuator(
        repo_root=repo,
        report_root=tmp_path / "reports",
    )
    result = actuator.apply_git_commit(
        governed_commit_record=_valid_governed_record(),
        package_id="pkg-test",
        task_id="task-test",
        run_id="run-test",
    )

    after = _git(repo, "rev-parse", "HEAD").stdout.strip()

    assert result["commit_applied"] is False
    assert result["runtime_commit_apply_status"] == "git_commit_noop_no_diff"
    assert before == after

    evidence_path = Path(result["git_commit_actuator_record_path"])
    assert evidence_path.exists()


def test_executor_and_console_do_not_directly_own_git_commit() -> None:
    console_source = Path("cli/zero_operator_console.py").read_text(encoding="utf-8")
    assert '["git", "commit"' not in console_source
    assert "git commit" not in console_source.lower()
    assert "RuntimeGitCommitActuator" in console_source