import json
import subprocess
import sys
from pathlib import Path

from cli import zero_operator_console


class FakeConsoleGovernedMutationAdapter:
    safe_governed_mutation_adapter = True

    def __init__(self, *args, **kwargs):
        pass

    def execute_governed_mutation(self, request):
        return {
            "mutation_started": True,
            "mutation_completed": True,
            "validation_passed": True,
            "rollback_required": False,
            "rollback_completed": False,
            "changed_files": ["core/runtime/console_target.py"],
            "non_mainline_issues": [],
        }


def _package(tmp_path: Path, **overrides) -> Path:
    payload = {
        "package_id": "pkg-console-1",
        "task_id": "task-console-1",
        "goal": "operator console package",
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
                "change_id": "change-1",
                "path": "core/runtime/console_target.py",
                "operation": "governed_repo_edit",
            }
        ],
    }
    payload.update(overrides)
    path = tmp_path / "runtime-package.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_submit_parses_package_json(tmp_path: Path) -> None:
    package = _package(tmp_path)

    result = zero_operator_console.submit_package(package)

    assert result["operator_console_available"] is True
    assert result["web_ui_available"] is False
    assert result["command"] == "submit"
    assert result["package_id"] == "pkg-console-1"
    assert result["run_id"]
    assert result["chain"]["closure"] == "dry_run_runtime_closed"
    assert result["runtime_loop_closed"] is True


def test_status_renders_canonical_chain(tmp_path: Path) -> None:
    package = _package(tmp_path)
    submitted = zero_operator_console.submit_package(package)

    status = zero_operator_console.status_run(submitted["run_id"])

    assert status["command"] == "status"
    assert list(status["chain"].keys()) == list(zero_operator_console.CHAIN_FIELDS)
    assert status["chain"]["intake"] == "accepted"
    assert status["chain"]["approval"] == "approved"
    assert status["chain"]["gate"] == "opened"
    assert status["chain"]["invocation"] == "recorded"
    assert status["chain"]["dispatch"] == "dispatch_bound"
    assert status["chain"]["session"] == "dry_run_started"
    assert status["chain"]["result"] == "dry_run_completed"
    assert status["chain"]["closure"] == "dry_run_runtime_closed"


def test_run_dry_run_does_not_enable_mutation(tmp_path: Path) -> None:
    package = _package(tmp_path)

    result = zero_operator_console.run_package(package, controlled=False)

    assert result["command"] == "run"
    assert result["console_mode"] == "dry_run"
    assert result["real_executor_enabled"] is False
    assert result["execution_real"] is False
    assert result["mutation_allowed"] is False
    assert result["chain"]["executor"] == "blocked_no_safe_executor_adapter"


def test_run_controlled_attaches_governed_adapter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        zero_operator_console,
        "RuntimeGovernedMutationAdapter",
        FakeConsoleGovernedMutationAdapter,
    )
    package = _package(tmp_path)

    result = zero_operator_console.run_package(package, controlled=True)

    assert result["console_mode"] == "controlled"
    assert result["real_executor_enabled"] is True
    assert result["execution_real"] is True
    assert result["governed_mutation_adapter_attached"] is True
    assert result["mutation_allowed"] is True
    assert result["controlled_mutation"] is True
    assert result["chain"]["mutation"] == "controlled_mutation_commit_allowed"
    assert result["commit_allowed"] is True


def test_invalid_package_rejected_deterministically(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"package_id": "bad"}), encoding="utf-8")

    first = zero_operator_console.submit_package(path)
    second = zero_operator_console.submit_package(path)

    assert first == second
    assert first["ok"] is False
    assert first["denial_reason"] == "invalid_package"
    assert "missing_task_id" in first["non_mainline_issues"]
    assert first["chain"]["intake"] == "rejected"


def test_cli_has_no_direct_process_or_file_mutation_surface() -> None:
    source = Path("cli/zero_operator_console.py").read_text(encoding="utf-8").lower()
    forbidden = [
        "popen",
        "system(",
        "run_shell",
        "exec(",
        "eval(",
        "write_bytes",
        "repo_mutation_enabled=true",
        "direct_write",
        "filesystem_write",
    ]
    for token in forbidden:
        assert token not in source, f"forbidden token present: {token}"


def test_cli_routes_through_runtime_operator_service_only() -> None:
    source = Path("cli/zero_operator_console.py").read_text(encoding="utf-8")

    assert "RuntimeOperatorService" in source
    assert "run_goal(" in source
    assert "run_governed_mutation_runtime" not in source
    assert "mutation_patch_apply" not in source
    assert "repo_edit_tool" not in source


def test_controlled_example_cli_completes_without_hanging() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.zero_operator_console",
            "run",
            "examples/runtime_operator_package.example.json",
            "--controlled",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        timeout=240,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "run"
    assert payload["console_mode"] == "controlled"
    assert payload["runtime_loop_closed"] is True
