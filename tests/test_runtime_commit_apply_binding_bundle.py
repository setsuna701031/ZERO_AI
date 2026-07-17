from pathlib import Path

from cli import zero_operator_console
from core.runtime.runtime_commit_apply_binding import bind_runtime_commit_apply
from core.runtime.runtime_operator_service import RuntimeOperatorService


class FakeSafeNoMutationAdapter:
    safe_no_mutation_adapter = True

    def execute_controlled_no_mutation(self, request):
        return {
            "adapter_status": "completed",
            "mutation_allowed": False,
            "repo_mutation_enabled": False,
            "output_summary": {
                "requested_changes": [
                    {
                        "path": "core/runtime/commit_target.py",
                        "operation": "governed_repo_edit",
                    }
                ]
            },
            "error_summary": {},
            "non_mainline_issues": [],
        }


class FakeGovernedMutationAdapter:
    safe_governed_mutation_adapter = True

    def __init__(self, *, validation_passed=True, rollback_required=False):
        self.validation_passed = validation_passed
        self.rollback_required = rollback_required

    def execute_governed_mutation(self, request):
        return {
            "mutation_started": True,
            "mutation_completed": True,
            "validation_passed": self.validation_passed,
            "rollback_required": self.rollback_required,
            "rollback_completed": self.rollback_required,
            "changed_files": ["core/runtime/commit_target.py"],
            "non_mainline_issues": [],
        }


class FakeGovernedCommitAdapter:
    safe_governed_commit_adapter = True

    def __init__(self) -> None:
        self.requests = []

    def record_commit_apply(self, request):
        self.requests.append(request)
        return {
            "commit_applied": True,
            "commit_recorded": True,
            "git_diff_recorded": True,
            "commit_id": "fake-commit-0001",
            "non_mainline_issues": [],
        }


class FakeConsoleMutationAdapter:
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
            "changed_files": ["core/runtime/commit_target.py"],
            "non_mainline_issues": [],
        }


def _config(tmp_path: Path):
    return {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "commit-apply-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }


def _mutation_result(tmp_path: Path, *, validation_passed=True, rollback_required=False):
    service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
        controlled_mutation_adapter=FakeGovernedMutationAdapter(
            validation_passed=validation_passed,
            rollback_required=rollback_required,
        ),
    )
    return service.run_goal("commit apply binding")["controlled_mutation_result"]


def _package(tmp_path: Path) -> Path:
    path = tmp_path / "operator-package.json"
    path.write_text(
        """{
  "package_id": "pkg-commit-console",
  "task_id": "task-commit-console",
  "goal": "operator console commit fields",
  "requested_mode": "controlled",
  "authority_context": {"operator": "RuntimeOperatorService"},
  "requested_changes": [
    {"path": "core/runtime/commit_target.py", "operation": "governed_repo_edit"}
  ]
}
""",
        encoding="utf-8",
    )
    return path


def test_consumes_runtime_controlled_mutation_result(tmp_path: Path) -> None:
    mutation = _mutation_result(tmp_path)

    result = bind_runtime_commit_apply(mutation)

    assert result["mutation_request_id"] == mutation["mutation_request_id"]
    assert result["validation_passed"] is True
    assert result["commit_allowed"] is True
    assert result["runtime_commit_apply_status"] == (
        "blocked_no_governed_commit_adapter"
    )


def test_rejects_mutation_without_validation(tmp_path: Path) -> None:
    mutation = _mutation_result(tmp_path, validation_passed=False)

    result = bind_runtime_commit_apply(mutation)

    assert result["runtime_commit_apply_status"] == "rejected"
    assert result["apply_reason"] == "validation_not_passed"
    assert result["commit_applied"] is False


def test_rejects_rollback_required_mutation(tmp_path: Path) -> None:
    mutation = _mutation_result(
        tmp_path,
        validation_passed=True,
        rollback_required=True,
    )

    result = bind_runtime_commit_apply(mutation)

    assert result["runtime_commit_apply_status"] == "rejected"
    assert result["apply_reason"] == "rollback_required"
    assert result["commit_recorded"] is False


def test_blocked_if_no_governed_commit_adapter(tmp_path: Path) -> None:
    mutation = _mutation_result(tmp_path)
    first = bind_runtime_commit_apply(mutation)
    second = bind_runtime_commit_apply(mutation)

    assert first == second
    assert first["runtime_commit_apply_status"] == (
        "blocked_no_governed_commit_adapter"
    )
    assert first["commit_applied"] is False
    assert first["commit_recorded"] is False


def test_success_if_fake_governed_commit_adapter_injected(tmp_path: Path) -> None:
    mutation = _mutation_result(tmp_path)
    adapter = FakeGovernedCommitAdapter()

    result = bind_runtime_commit_apply(mutation, governed_commit_adapter=adapter)

    assert result["runtime_commit_apply_status"] == "commit_apply_recorded"
    assert result["commit_applied"] is True
    assert result["commit_recorded"] is True
    assert result["git_diff_recorded"] is True
    assert result["commit_id"] == "fake-commit-0001"
    assert adapter.requests[0]["mutation_request_id"] == mutation["mutation_request_id"]


def test_rejects_duplicate_apply_for_same_mutation(tmp_path: Path) -> None:
    mutation = _mutation_result(tmp_path)
    first = bind_runtime_commit_apply(
        mutation,
        governed_commit_adapter=FakeGovernedCommitAdapter(),
    )

    duplicate = bind_runtime_commit_apply(
        mutation,
        governed_commit_adapter=FakeGovernedCommitAdapter(),
        existing_commit_applies=[first],
    )

    assert duplicate["runtime_commit_apply_status"] == "rejected"
    assert duplicate["apply_reason"] == "duplicate_commit_apply"


def test_lineage_mismatch_rejected(tmp_path: Path) -> None:
    mutation = _mutation_result(tmp_path)
    mutation["executor_invocation_gate_id"] = "wrong-gate"

    result = bind_runtime_commit_apply(
        mutation,
        governed_commit_adapter=FakeGovernedCommitAdapter(),
    )

    assert result["runtime_commit_apply_status"] == "rejected"
    assert result["apply_reason"] == "lineage_mismatch"


def test_no_cli_direct_commit_call() -> None:
    source = Path("cli/zero_operator_console.py").read_text(encoding="utf-8").lower()
    forbidden = [
        "subprocess",
        "os.system",
        "git commit",
        "gitpython",
        "dulwich",
        "record_commit_apply(",
    ]
    for token in forbidden:
        assert token not in source, f"forbidden token present: {token}"


def test_no_executor_direct_commit() -> None:
    files = [
        Path("core/runtime/runtime_controlled_real_executor_unlock.py"),
        Path("core/runtime/runtime_controlled_mutation_unlock.py"),
    ]
    for file in files:
        source = file.read_text(encoding="utf-8")
        assert "record_commit_apply(" not in source
        assert "commit_apply_recorded" not in source


def test_runtime_operator_service_exposes_commit_apply_status(tmp_path: Path) -> None:
    adapter = FakeGovernedCommitAdapter()
    service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
        controlled_mutation_adapter=FakeGovernedMutationAdapter(),
        governed_commit_adapter=adapter,
    )

    result = service.run_goal("operator service commit apply")
    status = service.status()

    assert result["runtime_commit_apply_status"] == "commit_apply_recorded"
    assert result["commit_applied"] is True
    assert result["commit_recorded"] is True
    assert result["commit_id"] == "fake-commit-0001"
    assert result["git_diff_recorded"] is True
    assert result["runtime_commit_apply_result"]["commit_id"] == "fake-commit-0001"
    assert status["runtime_commit_apply_status"]["commit_recorded"] is True


def test_operator_console_reports_commit_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        zero_operator_console,
        "RuntimeGovernedMutationAdapter",
        FakeConsoleMutationAdapter,
    )

    result = zero_operator_console.run_package(_package(tmp_path), controlled=True)

    assert "commit_allowed" in result
    assert "commit_applied" in result
    assert "commit_recorded" in result
    assert "commit_id" in result
    assert "git_diff_recorded" in result
    assert result["operator_console_available"] is True
    assert result["web_ui_available"] is False


def test_full_chain_reaches_commit_apply(tmp_path: Path) -> None:
    service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
        controlled_mutation_adapter=FakeGovernedMutationAdapter(),
        governed_commit_adapter=FakeGovernedCommitAdapter(),
    )

    result = service.run_goal("executor mutation validation commit apply")

    assert result["real_executor_enabled"] is True
    assert result["controlled_mutation"] is True
    assert result["validation_passed"] is True
    assert result["commit_allowed"] is True
    assert result["runtime_commit_apply_status"] == "commit_apply_recorded"
    assert result["commit_applied"] is True
    assert result["commit_recorded"] is True
