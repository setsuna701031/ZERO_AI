from __future__ import annotations

import json
from pathlib import Path

import cli.zero_natural_task as natural_task_cli


def _fake_accept(
    self,
    task: str,
    *,
    mode: str,
    target_root: str,
) -> dict:
    root = Path(self.workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    package_path = root / "package-test.json"
    package = {
        "schema": "zero.runtime.operator_package.v1",
        "package_id": "runtime-package-test",
        "task_id": "task-test",
        "goal": task,
        "requested_mode": mode,
        "target_root": target_root,
        "validation_required": True,
        "rollback_required": True,
    }
    package_path.write_text(json.dumps(package), encoding="utf-8")
    return {
        "ok": True,
        "intake_id": "intake-test",
        "intake_path": str(root / "intake-test.json"),
        "package_path": str(package_path),
        "package": package,
    }


def _blocked_operator_result(
    package_path: Path,
    *,
    controlled: bool,
) -> dict:
    _ = package_path
    _ = controlled
    return {
        "schema": "zero.operator_console.v1",
        "ok": True,
        "task_id": "task-test",
        "execution_real": False,
        "real_executor_enabled": False,
        "changed_files": [],
        "validation_passed": False,
        "rollback_completed": False,
        "denial_reason": "safe_no_mutation_adapter_unavailable",
        "controlled_mutation_result": {
            "ok": False,
            "mutation_completed": False,
            "validation_passed": False,
            "rollback_completed": False,
            "changed_files": [],
            "denial_reason": "real_executor_not_enabled",
        },
    }


def test_natural_task_records_blocked_operator_activity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        natural_task_cli.RuntimeNaturalTaskIntake,
        "accept",
        _fake_accept,
    )
    monkeypatch.setattr(
        natural_task_cli,
        "run_package",
        _blocked_operator_result,
    )

    workspace_root = tmp_path / "workspace" / "operator_intake"
    result = natural_task_cli.run_natural_task(
        "create sentinel activity check",
        controlled=False,
        workspace_root=workspace_root,
    )

    activity_path = (
        tmp_path
        / "workspace"
        / "operator_activity"
        / "activity.jsonl"
    )

    assert result["ok"] is False
    assert result["activity_recorded"] is True
    assert result["activity_log_path"] == str(activity_path)
    assert activity_path.exists()

    records = [
        json.loads(line)
        for line in activity_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(records) == 1
    assert records[0]["goal"] == "create sentinel activity check"
    assert records[0]["task_id"] == "task-test"
    assert records[0]["source"] == "cli.zero_natural_task"
    assert records[0]["status"] == "failed"
    assert records[0]["changed_files"] == []
    assert records[0]["denial_reason"] == (
        "safe_no_mutation_adapter_unavailable"
    )
