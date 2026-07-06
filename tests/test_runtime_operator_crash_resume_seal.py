from __future__ import annotations

import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from core.runtime.runtime_journal import RuntimeJournal


def _stable_run_id(package_id: str, task_id: str, mode: str = "controlled") -> str:
    body = "|".join([package_id, task_id, mode])
    return "operator-console-run-" + sha256(body.encode("utf-8")).hexdigest()[:16]


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_operator_crash_resume_preserves_completed_commit(
    tmp_path: Path,
) -> None:
    package_id = f"runtime-operator-crash-resume-{tmp_path.name}"
    task_id = "runtime-operator-crash-resume-task"
    run_id = _stable_run_id(package_id, task_id)
    original_commit_id = "commit-before-crash-123"

    package_path = tmp_path / "runtime_operator_crash_resume_package.json"
    package_path.write_text(
        json.dumps(
            {
                "package_id": package_id,
                "task_id": task_id,
                "goal": "Resume already completed controlled operator run",
                "requested_mode": "controlled",
                "authority_context": {
                    "operator": "RuntimeOperatorService",
                    "approval_required": True,
                    "governed_mutation_adapter_required": True,
                    "validation_required": True,
                    "rollback_required": True,
                },
                "requested_changes": [
                    {
                        "change_id": "resume-change-1",
                        "path": "core/runtime/resume_target.py",
                        "operation": "governed_repo_edit",
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    root = Path("workspace") / "operator_console" / package_id
    report_root = root / "reports"
    report_root.mkdir(parents=True, exist_ok=True)

    checkpoint_path = Path("workspace") / "operator_console" / f"{package_id}-checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "package_id": package_id,
                "task_id": task_id,
                "run_id": run_id,
                "phase": "commit_recorded",
                "mutation_completed": True,
                "commit_recorded": True,
                "commit_id": original_commit_id,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    journal = RuntimeJournal(report_root / "runtime.wal.jsonl")
    journal.append(
        "operator_controlled_mutation",
        payload={
            "package_id": package_id,
            "task_id": task_id,
            "run_id": run_id,
            "controlled_mutation": True,
            "mutation_completed": True,
            "validation_passed": True,
            "commit_allowed": True,
        },
        metadata={"phase": "before_crash"},
    )
    journal.append(
        "operator_commit_recorded",
        payload={
            "package_id": package_id,
            "task_id": task_id,
            "run_id": run_id,
            "commit_recorded": True,
            "commit_applied": True,
            "commit_id": original_commit_id,
        },
        metadata={"phase": "before_crash"},
    )

    governed_commit_record_path = report_root / "governed_commit_record.json"
    git_actuator_record_path = report_root / "git_commit_actuator_record.json"
    governed_commit_record_path.write_text(
        json.dumps(
            {
                "schema": "zero.runtime.governed_commit_record.v1",
                "package_id": package_id,
                "task_id": task_id,
                "run_id": run_id,
                "adapter_status": "governed_recorded",
                "commit_allowed": True,
                "commit_applied": True,
                "commit_recorded": True,
                "controlled_mutation": True,
                "mutation_allowed": True,
                "validation_passed": True,
                "rollback_available": True,
                "real_executor_enabled": True,
                "non_mainline_issues": [],
                "runtime_commit_apply_status": "governed_commit_recorded",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    git_actuator_record_path.write_text(
        json.dumps(
            {
                "schema": "zero.runtime.git_commit_actuator.v1",
                "package_id": package_id,
                "task_id": task_id,
                "run_id": run_id,
                "actuator_status": "git_commit_applied",
                "commit_applied": True,
                "commit_id": original_commit_id,
                "runtime_commit_apply_status": "git_commit_applied",
                "git_diff_recorded": True,
                "non_mainline_issues": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    governed_before = governed_commit_record_path.read_text(encoding="utf-8")
    actuator_before = git_actuator_record_path.read_text(encoding="utf-8")
    journal_record_count_before = len(RuntimeJournal(report_root / "runtime.wal.jsonl").records)

    head_before = _git_head()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.zero_operator_console",
            "run",
            str(package_path),
            "--controlled",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        timeout=60,
    )
    head_after = _git_head()

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["resume_restored"] is True
    assert payload["run_id"] == run_id
    assert payload["task_id"] == task_id
    assert payload["commit_id"] == original_commit_id
    assert payload["controlled_mutation"] is True
    assert payload["commit_recorded"] is True
    assert payload["commit_applied"] is True
    assert payload["runtime_commit_apply_status"] == "git_commit_applied"
    assert payload["duplicate_mutation"] is False
    assert payload["duplicate_commit"] is False
    assert payload["duplicate_git_actuator_execution"] is False
    assert "non_mainline_issues" in payload
    assert isinstance(payload["non_mainline_issues"], list)

    resume_evidence_path = Path(payload["resume_evidence_path"])
    assert resume_evidence_path.exists()
    resume_evidence = _read_json(resume_evidence_path)
    assert resume_evidence["resume_restored"] is True
    assert resume_evidence["run_id"] == run_id
    assert resume_evidence["commit_id"] == original_commit_id
    assert resume_evidence["duplicate_mutation"] is False
    assert resume_evidence["duplicate_commit"] is False
    assert resume_evidence["duplicate_git_actuator_execution"] is False

    assert governed_commit_record_path.read_text(encoding="utf-8") == governed_before
    assert git_actuator_record_path.read_text(encoding="utf-8") == actuator_before
    assert len(RuntimeJournal(report_root / "runtime.wal.jsonl").records) == journal_record_count_before
    assert head_after == head_before
