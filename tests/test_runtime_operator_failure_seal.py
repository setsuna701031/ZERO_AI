from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


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


def test_runtime_operator_invalid_package_failure_seal(tmp_path: Path) -> None:
    package_id = f"runtime-operator-failure-seal-{tmp_path.name}"
    bad_package = tmp_path / "bad_runtime_operator_package.json"
    bad_package.write_text(
        json.dumps(
            {
                "package_id": package_id,
                "task_id": "runtime-operator-failure-task",
                "goal": "Denied controlled mutation package",
                "requested_mode": "controlled",
                "requested_changes": [
                    {
                        "change_id": "bad-change-1",
                        "path": "core/runtime/should_not_mutate.py",
                        "operation": "governed_repo_edit",
                        "force_validation_failure": True,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    report_root = Path("workspace") / "operator_console" / package_id / "reports"
    failure_evidence_path = report_root / "operator_failure_evidence.json"
    governed_commit_record_path = report_root / "governed_commit_record.json"
    git_actuator_record_path = report_root / "git_commit_actuator_record.json"

    head_before = _git_head()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.zero_operator_console",
            "run",
            str(bad_package),
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

    assert payload["ok"] is False
    assert payload["chain"]["result"] != "dry_run_completed"
    assert payload["controlled_mutation"] is not True
    assert payload["commit_allowed"] is False
    assert payload["commit_applied"] is False
    assert payload["commit_recorded"] is False
    assert payload["runtime_commit_apply_status"] != "git_commit_applied"
    assert "non_mainline_issues" in payload
    assert isinstance(payload["non_mainline_issues"], list)
    assert payload["non_mainline_issues"]

    assert failure_evidence_path.exists()
    failure_evidence = _read_json(failure_evidence_path)
    assert failure_evidence["ok"] is False
    assert failure_evidence["controlled_mutation"] is False
    assert failure_evidence["commit_allowed"] is False
    assert failure_evidence["commit_applied"] is False
    assert failure_evidence["actuator_executed"] is False
    assert isinstance(failure_evidence["non_mainline_issues"], list)
    assert "missing_authority_context" in failure_evidence["non_mainline_issues"]

    assert not governed_commit_record_path.exists()
    assert not git_actuator_record_path.exists()
    assert head_after == head_before
