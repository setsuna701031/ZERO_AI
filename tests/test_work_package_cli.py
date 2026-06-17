from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _execute_payload(
    *,
    package_id: str,
    target_path: str,
    content: str,
    approval: bool = True,
    scope_path: str | None = None,
) -> dict[str, object]:
    return {
        "package_id": package_id,
        "kind": "readonly_audit",
        "mode": "execute",
        "title": "CLI controlled workspace execution",
        "scope_paths": [scope_path or target_path],
        "report_path": f"workspace/{package_id}_report.md",
        "approval": approval,
        "edit": {
            "operation": "create_file",
            "target_path": target_path,
            "content": content,
        },
    }


def _run_cli_submit(tmp_path: Path, payload: dict[str, object]) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    package_file = tmp_path / f"{payload['package_id']}.json"
    package_file.write_text(json.dumps(payload), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.work_package_cli",
            "--repo-root",
            str(tmp_path),
            "submit",
            str(package_file),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, json.loads(completed.stdout)


def test_cli_submit_runs_controlled_workspace_package_end_to_end(tmp_path: Path) -> None:
    completed, payload = _run_cli_submit(
        tmp_path,
        _execute_payload(
            package_id="cli_workspace_create",
            target_path="workspace/cli_created.txt",
            content="created through cli",
        ),
    )

    result = payload["result"]
    execution = result["result"]

    assert completed.returncode == 0
    assert payload["ok"] is True
    assert result["status"] == "completed"
    assert result["completion_authority"]["schema"] == "zero.work_package_completion_authority.summary.v1"
    assert result["completion_authority"]["package_id"] == "cli_workspace_create"
    assert execution["ok"] is True
    assert execution["reason"] == "controlled_workspace_execution_completed"
    assert execution["changed_files"] == ["workspace/cli_created.txt"]
    assert execution["evidence"]["guard"] == "workspace_only"
    assert execution["evidence"]["approval"] is True
    assert (tmp_path / "workspace/cli_created.txt").read_text(encoding="utf-8") == "created through cli"
    assert (tmp_path / "workspace/cli_workspace_create_report.md").is_file()


def test_cli_submit_rejects_illegal_controlled_workspace_target(tmp_path: Path) -> None:
    completed, payload = _run_cli_submit(
        tmp_path,
        _execute_payload(
            package_id="cli_block_core",
            target_path="core/agent/agent_loop.py",
            content="blocked",
            scope_path="workspace/declared_scope.txt",
        ),
    )

    result = payload["result"]
    execution = result["result"]

    assert completed.returncode == 0
    assert payload["ok"] is True
    assert result["status"] == "failed"
    assert result["completion_authority"] is None
    assert execution["ok"] is False
    assert execution["blocked"] is True
    assert "blocked_target_prefix:core" in execution["reason"]
    assert not (tmp_path / "core/agent/agent_loop.py").exists()
