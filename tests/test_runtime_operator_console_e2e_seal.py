from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PACKAGE_PATH = Path("examples") / "runtime_operator_package.example.json"
REPORT_ROOT = (
    Path("workspace")
    / "operator_console"
    / "runtime-operator-package-example"
    / "reports"
)
GOVERNED_COMMIT_RECORD_PATH = REPORT_ROOT / "governed_commit_record.json"
GIT_COMMIT_ACTUATOR_RECORD_PATH = REPORT_ROOT / "git_commit_actuator_record.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_operator_console_e2e_seal() -> None:
    assert PACKAGE_PATH.exists()

    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "faulthandler",
            "-m",
            "cli.zero_operator_console",
            "run",
            str(PACKAGE_PATH),
            "--controlled",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        timeout=240,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["chain"]["result"] == "dry_run_completed"
    assert payload["controlled_mutation"] is True
    assert payload["commit_allowed"] is True
    assert payload["commit_applied"] is True
    assert payload["commit_recorded"] is True
    assert payload["runtime_loop_closed"] is True
    assert payload["runtime_commit_apply_status"] == "git_commit_applied"
    assert "non_mainline_issues" in payload
    assert isinstance(payload["non_mainline_issues"], list)

    assert GOVERNED_COMMIT_RECORD_PATH.exists()
    assert GIT_COMMIT_ACTUATOR_RECORD_PATH.exists()

    governed_commit_record = _read_json(GOVERNED_COMMIT_RECORD_PATH)
    git_commit_actuator_record = _read_json(GIT_COMMIT_ACTUATOR_RECORD_PATH)

    assert governed_commit_record["commit_allowed"] is True
    assert governed_commit_record["commit_applied"] is True
    assert governed_commit_record["commit_recorded"] is True
    assert governed_commit_record["validation_passed"] is True

    assert git_commit_actuator_record["actuator_status"] == "git_commit_applied"
    assert git_commit_actuator_record["commit_applied"] is True
    assert git_commit_actuator_record["commit_id"]
