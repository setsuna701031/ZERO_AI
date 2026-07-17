from copy import deepcopy
from pathlib import Path

from core.runtime.runtime_controlled_mutation_unlock import (
    ZERO_RUNTIME_CONTROLLED_MUTATION_UNLOCK_SCHEMA,
    unlock_controlled_mutation,
)
from core.runtime.runtime_operator_service import RuntimeOperatorService


class FakeSafeNoMutationAdapter:
    safe_no_mutation_adapter = True

    def execute_controlled_no_mutation(self, request):
        return {
            "adapter_status": "completed",
            "mutation_allowed": False,
            "repo_mutation_enabled": False,
            "output_summary": {
                "summary": "fake_controlled_execution_complete",
                "requested_changes": [
                    {
                        "change_id": "change-runtime-alpha",
                        "path": "core/runtime/alpha.py",
                        "operation": "governed_repo_edit",
                    }
                ],
            },
            "error_summary": {},
            "non_mainline_issues": [],
        }


class FakeGovernedMutationAdapter:
    safe_governed_mutation_adapter = True

    def __init__(self, *, validation_passed: bool = True) -> None:
        self.validation_passed = validation_passed
        self.requests = []
        self.state = {"core/runtime/alpha.py": "before"}

    def execute_governed_mutation(self, request):
        self.requests.append(request)
        before = dict(self.state)
        self.state["core/runtime/alpha.py"] = "after"
        if not self.validation_passed:
            self.state = before
            return {
                "mutation_started": True,
                "mutation_completed": True,
                "validation_passed": False,
                "rollback_required": True,
                "rollback_completed": True,
                "changed_files": ["core/runtime/alpha.py"],
                "previous_state": before,
                "restored_state": dict(self.state),
                "non_mainline_issues": [],
            }
        return {
            "mutation_started": True,
            "mutation_completed": True,
            "validation_passed": True,
            "rollback_required": False,
            "rollback_completed": False,
            "changed_files": ["core/runtime/alpha.py"],
            "previous_state": before,
            "restored_state": dict(self.state),
            "non_mainline_issues": [],
        }


class NotGovernedMutationAdapter:
    def __init__(self) -> None:
        self.called = False

    def execute_governed_mutation(self, request):
        self.called = True
        return {"mutation_started": True}


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "controlled-mutation-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _executor_unlock(tmp_path: Path) -> dict[str, object]:
    service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
    )
    result = service.run_goal("controlled mutation unlock")
    return result["controlled_real_executor_result"]


def test_mutation_consumes_controlled_real_executor_unlock_result(
    tmp_path: Path,
) -> None:
    unlock = _executor_unlock(tmp_path)
    adapter = FakeGovernedMutationAdapter()

    result = unlock_controlled_mutation(
        unlock,
        governed_mutation_adapter=adapter,
        runtime_operator_service_authorized=True,
    )

    assert result["schema"] == ZERO_RUNTIME_CONTROLLED_MUTATION_UNLOCK_SCHEMA
    assert result["controlled_mutation_status"] == (
        "controlled_mutation_commit_allowed"
    )
    assert result["mutation_request"]["executor_result_id"] == unlock[
        "execution_result_id"
    ]
    assert result["mutation_allowed"] is True
    assert result["commit_allowed"] is True


def test_cannot_mutate_before_executor_unlock() -> None:
    result = unlock_controlled_mutation(
        None,
        runtime_operator_service_authorized=True,
    )

    assert result["controlled_mutation_status"] == "rejected"
    assert result["controlled_mutation_result"]["mutation_reason"] == (
        "missing_executor_unlock"
    )
    assert result["mutation_allowed"] is False


def test_cannot_bypass_runtime_operator_service(tmp_path: Path) -> None:
    unlock = _executor_unlock(tmp_path)
    adapter = FakeGovernedMutationAdapter()

    result = unlock_controlled_mutation(unlock, governed_mutation_adapter=adapter)

    assert result["controlled_mutation_status"] == "rejected"
    assert result["controlled_mutation_result"]["mutation_reason"] == (
        "runtime_operator_service_required"
    )
    assert result["mutation_started"] is False
    assert adapter.requests == []


def test_cannot_direct_write_files(tmp_path: Path) -> None:
    unlock = deepcopy(_executor_unlock(tmp_path))
    unlock["adapter_result"]["output_summary"]["requested_changes"] = [
        {
            "path": "core/runtime/alpha.py",
            "operation": "direct_write",
            "direct_filesystem_write": True,
        }
    ]

    result = unlock_controlled_mutation(
        unlock,
        governed_mutation_adapter=FakeGovernedMutationAdapter(),
        runtime_operator_service_authorized=True,
    )

    assert result["controlled_mutation_status"] == "rejected"
    assert result["controlled_mutation_result"]["mutation_reason"] == (
        "direct_filesystem_mutation_forbidden"
    )
    assert result["mutation_started"] is False


def test_uses_governed_mutation_adapter_only(tmp_path: Path) -> None:
    unlock = _executor_unlock(tmp_path)
    adapter = NotGovernedMutationAdapter()

    result = unlock_controlled_mutation(
        unlock,
        governed_mutation_adapter=adapter,
        runtime_operator_service_authorized=True,
    )

    assert result["controlled_mutation_status"] == (
        "blocked_no_governed_mutation_adapter"
    )
    assert adapter.called is False
    assert result["mutation_allowed"] is False


def test_success_validation_path_through_operator_service(tmp_path: Path) -> None:
    mutation_adapter = FakeGovernedMutationAdapter(validation_passed=True)
    service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
        controlled_mutation_adapter=mutation_adapter,
    )

    result = service.run_goal("controlled mutation success")
    status = service.status()

    assert result["real_executor_ready"] is True
    assert result["real_executor_enabled"] is True
    assert result["execution_real"] is True
    assert result["mutation_allowed"] is True
    assert result["controlled_mutation"] is True
    assert result["mutation_started"] is True
    assert result["mutation_completed"] is True
    assert result["validation_passed"] is True
    assert result["rollback_completed"] is False
    assert result["commit_allowed"] is True
    assert result["rollback_available"] is True
    assert result["validation_required"] is True
    assert result["autonomous_runtime_loop_closed"] is True
    assert status["controlled_mutation_status"]["commit_allowed"] is True


def test_failure_validation_path_rolls_back(tmp_path: Path) -> None:
    mutation_adapter = FakeGovernedMutationAdapter(validation_passed=False)
    service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
        controlled_mutation_adapter=mutation_adapter,
    )

    result = service.run_goal("controlled mutation rollback")

    assert result["mutation_allowed"] is True
    assert result["mutation_started"] is True
    assert result["mutation_completed"] is True
    assert result["validation_passed"] is False
    assert result["controlled_mutation_result"]["rollback_required"] is True
    assert result["rollback_completed"] is True
    assert result["commit_allowed"] is False
    assert mutation_adapter.state["core/runtime/alpha.py"] == "before"


def test_lineage_mismatch_rejected(tmp_path: Path) -> None:
    unlock = deepcopy(_executor_unlock(tmp_path))
    unlock["gate_id"] = "wrong-gate"

    result = unlock_controlled_mutation(
        unlock,
        governed_mutation_adapter=FakeGovernedMutationAdapter(),
        runtime_operator_service_authorized=True,
    )

    assert result["controlled_mutation_status"] == "rejected"
    assert result["controlled_mutation_result"]["mutation_reason"] == (
        "invalid_lineage"
    )


def test_duplicate_mutation_rejected(tmp_path: Path) -> None:
    unlock = _executor_unlock(tmp_path)
    first = unlock_controlled_mutation(
        unlock,
        governed_mutation_adapter=FakeGovernedMutationAdapter(),
        runtime_operator_service_authorized=True,
    )
    duplicate = unlock_controlled_mutation(
        unlock,
        governed_mutation_adapter=FakeGovernedMutationAdapter(),
        existing_mutations=[first],
        runtime_operator_service_authorized=True,
    )

    assert duplicate["controlled_mutation_status"] == "rejected"
    assert duplicate["controlled_mutation_result"]["mutation_reason"] == (
        "duplicate_mutation_request"
    )


def test_changed_files_tracked_and_rollback_restores_previous_state(
    tmp_path: Path,
) -> None:
    mutation_adapter = FakeGovernedMutationAdapter(validation_passed=False)
    service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
        controlled_mutation_adapter=mutation_adapter,
    )

    result = service.run_goal("controlled mutation changed files")
    mutation = result["controlled_mutation_result"]

    assert mutation["changed_files"] == ["core/runtime/alpha.py"]
    assert mutation["controlled_mutation_result"]["changed_files"] == [
        "core/runtime/alpha.py"
    ]
    assert mutation_adapter.state == {"core/runtime/alpha.py": "before"}
    assert result["rollback_completed"] is True


def test_full_runtime_chain_reaches_mutation(tmp_path: Path) -> None:
    service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
        controlled_mutation_adapter=FakeGovernedMutationAdapter(),
    )

    result = service.run_goal("approval gate invocation dispatch mutation")

    assert result["executor_invocation_approved"] is True
    assert result["executor_invocation_gate_open"] is True
    assert result["executor_invocation_recorded"] is True
    assert result["executor_invoked"] is True
    assert result["executor_invocation_dispatch_status"] == "dispatch_bound"
    assert result["runtime_execution_session_start_status"] == "dry_run_started"
    assert result["runtime_execution_result_capture_status"] == "dry_run_completed"
    assert result["runtime_executor_closure_status"] == "dry_run_runtime_closed"
    assert result["controlled_real_executor_unlock_status"] == (
        "controlled_real_executor_unlocked"
    )
    assert result["controlled_mutation_status"] == (
        "controlled_mutation_commit_allowed"
    )
    assert result["controlled_mutation"] is True
