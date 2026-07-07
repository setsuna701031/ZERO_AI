from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PACKAGE_PATH = Path("examples/runtime_operator_package.example.json")
REPORT_ROOT = Path("workspace/operator_console/runtime-operator-package-example/reports")
_ALLOWED_COMMIT_STATUSES = {"git_commit_applied", "git_commit_noop_no_diff"}


def _read_json(path: Path) -> dict:
    assert path.exists(), f"missing report: {path}"
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
    assert payload["mutation_allowed"] is True
    assert payload["commit_allowed"] is True
    assert payload["commit_recorded"] is True
    assert payload["runtime_commit_apply_status"] in _ALLOWED_COMMIT_STATUSES
    assert payload["runtime_loop_closed"] is True
    assert payload["duplicate_mutation"] is False
    assert payload["duplicate_commit"] is False
    assert payload["duplicate_git_actuator_execution"] is False
    assert isinstance(payload["non_mainline_issues"], list)

    if payload["runtime_commit_apply_status"] == "git_commit_applied":
        assert payload["commit_applied"] is True
        assert payload["commit_id"]
    else:
        assert payload["commit_applied"] is False
        assert payload["commit_id"] == ""

    governed_report_path = Path(payload["governed_commit_record_path"])
    actuator_report_path = Path(payload["git_commit_actuator_record_path"])

    governed = _read_json(governed_report_path)
    actuator = _read_json(actuator_report_path)

    assert governed_report_path == REPORT_ROOT / "governed_commit_record.json"
    assert actuator_report_path == REPORT_ROOT / "git_commit_actuator_record.json"

    assert governed["commit_allowed"] is True
    assert governed["commit_recorded"] is True
    assert governed["controlled_mutation"] is True
    assert governed["mutation_allowed"] is True
    assert governed["validation_passed"] is True
    assert isinstance(governed["non_mainline_issues"], list)

    assert actuator["runtime_commit_apply_status"] in _ALLOWED_COMMIT_STATUSES
    assert isinstance(actuator["non_mainline_issues"], list)

    if actuator["runtime_commit_apply_status"] == "git_commit_applied":
        assert actuator["actuator_status"] == "git_commit_applied"
        assert actuator["commit_applied"] is True
        assert actuator["commit_id"]
    else:
        assert actuator["actuator_status"] == "git_commit_noop_no_diff"
        assert actuator["commit_applied"] is False
        assert actuator.get("commit_id", "") == ""

    assert not (REPORT_ROOT / "operator_failure_evidence.json").exists()
