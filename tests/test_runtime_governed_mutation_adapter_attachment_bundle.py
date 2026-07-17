from pathlib import Path

from cli import zero_operator_console
from core.runtime.runtime_governed_mutation_adapter import (
    RuntimeGovernedMutationAdapter,
)


class FakeGovernedRuntimeResult:
    def __init__(self, *, verified=True, rolled_back=False):
        self.verified = verified
        self.rolled_back = rolled_back

    def to_dict(self):
        return {
            "executed": True,
            "blocked": False,
            "failed": not self.verified,
            "verified": self.verified,
            "rolled_back": self.rolled_back,
            "impacted_files": ["core/runtime/adapter_target.py"],
            "apply_result": {
                "applied": True,
                "applied_paths": ["core/runtime/adapter_target.py"],
                "rollback_paths": ["core/runtime/adapter_target.py"],
            },
        }


class CapturingGovernedRunner:
    def __init__(self, *, verified=True):
        self.verified = verified
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return FakeGovernedRuntimeResult(
            verified=self.verified,
            rolled_back=not self.verified,
        )


class FakeConsoleGovernedAdapter:
    safe_governed_mutation_adapter = True
    instances = []

    def __init__(self, *args, **kwargs):
        self.requests = []
        FakeConsoleGovernedAdapter.instances.append(self)

    def execute_governed_mutation(self, request):
        self.requests.append(request)
        validation_failed = any(
            change.get("force_validation_failure") is True
            for change in request.get("requested_changes", [])
        )
        return {
            "mutation_started": True,
            "mutation_completed": True,
            "validation_passed": not validation_failed,
            "rollback_required": validation_failed,
            "rollback_completed": validation_failed,
            "changed_files": ["core/runtime/console_target.py"],
            "non_mainline_issues": [],
        }


def _package(tmp_path: Path, *, validation_failure=False) -> Path:
    change = {
        "change_id": "change-1",
        "path": "core/runtime/console_target.py",
        "operation": "governed_repo_edit",
        "content": "VALUE = 1\n",
    }
    if validation_failure:
        change["force_validation_failure"] = True
    payload = {
        "package_id": "pkg-governed-adapter",
        "task_id": "task-governed-adapter",
        "goal": "operator console governed adapter",
        "requested_mode": "controlled",
        "authority_context": {
            "operator": "RuntimeOperatorService",
            "validation_required": True,
            "rollback_required": True,
        },
        "requested_changes": [change],
    }
    path = tmp_path / "runtime-package.json"
    path.write_text(__import__("json").dumps(payload), encoding="utf-8")
    return path


def _controlled_request():
    return {
        "execution_id": "exec-1",
        "executor_result_id": "result-1",
        "mutation_request_id": "mutation-1",
        "requested_changes": [
            {
                "path": "core/runtime/adapter_target.py",
                "operation": "governed_repo_edit",
                "content": "VALUE = 2\n",
            }
        ],
        "authority_context": {
            "runtime_operator_service_owner": True,
            "validation_required": True,
            "rollback_required": True,
        },
        "lineage": {"execution_result_id": "result-1"},
    }


def test_controlled_console_attaches_governed_adapter_when_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeConsoleGovernedAdapter.instances = []
    monkeypatch.setattr(
        zero_operator_console,
        "RuntimeGovernedMutationAdapter",
        FakeConsoleGovernedAdapter,
    )

    result = zero_operator_console.run_package(_package(tmp_path), controlled=True)

    assert result["operator_console_available"] is True
    assert result["real_executor_enabled"] is True
    assert result["governed_mutation_adapter_attached"] is True
    assert result["mutation_allowed"] is True
    assert result["controlled_mutation"] is True
    assert FakeConsoleGovernedAdapter.instances
    assert FakeConsoleGovernedAdapter.instances[0].requests


def test_dry_run_never_attaches_adapter(tmp_path: Path, monkeypatch) -> None:
    FakeConsoleGovernedAdapter.instances = []
    monkeypatch.setattr(
        zero_operator_console,
        "RuntimeGovernedMutationAdapter",
        FakeConsoleGovernedAdapter,
    )

    result = zero_operator_console.run_package(_package(tmp_path), controlled=False)

    assert result["real_executor_enabled"] is False
    assert result["mutation_allowed"] is False
    assert result["governed_mutation_adapter_attached"] is False
    assert FakeConsoleGovernedAdapter.instances == []


def test_adapter_uses_existing_governed_mutation_boundary(tmp_path: Path) -> None:
    runner = CapturingGovernedRunner()
    adapter = RuntimeGovernedMutationAdapter(
        workspace_root=tmp_path / "workspace",
        sandbox_source_root=tmp_path / "sandbox",
        rollback_root=tmp_path / "rollback",
        report_root=tmp_path / "reports",
        governed_runtime_runner=runner,
    )

    result = adapter.execute_governed_mutation(_controlled_request())

    assert runner.requests
    request = runner.requests[0]
    assert request.governed_mainline is True
    assert request.relative_paths == ("core/runtime/adapter_target.py",)
    assert result["governed_mutation_adapter_attached"] is True
    assert result["mutation_started"] is True


def test_no_direct_file_write_in_cli_or_adapter() -> None:
    for file in (
        Path("cli/zero_operator_console.py"),
        Path("core/runtime/runtime_governed_mutation_adapter.py"),
    ):
        source = file.read_text(encoding="utf-8").lower()
        forbidden = [
            "write_text",
            "write_bytes",
            "open(",
            "shutil",
            "copy2",
            "direct_write",
            "filesystem_write",
        ]
        for token in forbidden:
            assert token not in source, f"forbidden token present: {token}"


def test_success_path_produces_mutation_allowed_and_commit(tmp_path: Path) -> None:
    adapter = RuntimeGovernedMutationAdapter(
        workspace_root=tmp_path / "workspace",
        sandbox_source_root=tmp_path / "sandbox",
        rollback_root=tmp_path / "rollback",
        report_root=tmp_path / "reports",
        governed_runtime_runner=CapturingGovernedRunner(verified=True),
    )

    result = adapter.execute_governed_mutation(_controlled_request())

    assert result["mutation_started"] is True
    assert result["validation_passed"] is True
    assert result["rollback_completed"] is False
    assert result["commit_allowed"] is True


def test_validation_failure_triggers_rollback_completed(tmp_path: Path) -> None:
    adapter = RuntimeGovernedMutationAdapter(
        workspace_root=tmp_path / "workspace",
        sandbox_source_root=tmp_path / "sandbox",
        rollback_root=tmp_path / "rollback",
        report_root=tmp_path / "reports",
        governed_runtime_runner=CapturingGovernedRunner(verified=False),
    )

    result = adapter.execute_governed_mutation(_controlled_request())

    assert result["validation_passed"] is False
    assert result["rollback_required"] is True
    assert result["rollback_completed"] is True
    assert result["commit_allowed"] is False


def test_missing_adapter_remains_deterministic_blocked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(zero_operator_console, "RuntimeGovernedMutationAdapter", None)

    first = zero_operator_console.run_package(_package(tmp_path), controlled=True)
    second = zero_operator_console.run_package(_package(tmp_path), controlled=True)

    assert first == second
    assert first["real_executor_enabled"] is True
    assert first["governed_mutation_adapter_attached"] is False
    assert first["chain"]["mutation"] == "blocked_no_governed_mutation_adapter"
    assert first["mutation_allowed"] is False


def test_changed_files_are_reported(tmp_path: Path) -> None:
    adapter = RuntimeGovernedMutationAdapter(
        workspace_root=tmp_path / "workspace",
        sandbox_source_root=tmp_path / "sandbox",
        rollback_root=tmp_path / "rollback",
        report_root=tmp_path / "reports",
        governed_runtime_runner=CapturingGovernedRunner(),
    )

    result = adapter.execute_governed_mutation(_controlled_request())

    assert result["changed_files"] == ["core/runtime/adapter_target.py"]


def test_commit_allowed_only_when_validation_passes(tmp_path: Path) -> None:
    success = RuntimeGovernedMutationAdapter(
        workspace_root=tmp_path / "workspace-a",
        sandbox_source_root=tmp_path / "sandbox-a",
        rollback_root=tmp_path / "rollback-a",
        report_root=tmp_path / "reports-a",
        governed_runtime_runner=CapturingGovernedRunner(verified=True),
    ).execute_governed_mutation(_controlled_request())
    failure = RuntimeGovernedMutationAdapter(
        workspace_root=tmp_path / "workspace-b",
        sandbox_source_root=tmp_path / "sandbox-b",
        rollback_root=tmp_path / "rollback-b",
        report_root=tmp_path / "reports-b",
        governed_runtime_runner=CapturingGovernedRunner(verified=False),
    ).execute_governed_mutation(_controlled_request())

    assert success["validation_passed"] is True
    assert success["commit_allowed"] is True
    assert failure["validation_passed"] is False
    assert failure["commit_allowed"] is False


def test_full_operator_console_controlled_run_reaches_mutation_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeConsoleGovernedAdapter.instances = []
    monkeypatch.setattr(
        zero_operator_console,
        "RuntimeGovernedMutationAdapter",
        FakeConsoleGovernedAdapter,
    )

    result = zero_operator_console.run_package(_package(tmp_path), controlled=True)

    assert result["runtime_loop_closed"] is True
    assert result["real_executor_enabled"] is True
    assert result["controlled_mutation_available"] is True
    assert result["governed_mutation_adapter_attached"] is True
    assert result["validation_required"] is True
    assert result["rollback_completed"] is False
    assert result["web_ui_available"] is False
    assert result["chain"]["mutation"] == "controlled_mutation_commit_allowed"
