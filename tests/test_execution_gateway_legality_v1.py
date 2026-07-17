from __future__ import annotations

from dataclasses import dataclass

from core.tasks.execution_gateway import call_execution_gateway


@dataclass(frozen=True)
class FakeGovernanceSnapshot:
    governance_id: str


@dataclass(frozen=True)
class FakeRuntimeConstitution:
    constitution_version: str
    allowed_actions: tuple[str, ...]
    review_required_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]


def _constitution() -> FakeRuntimeConstitution:
    return FakeRuntimeConstitution(
        constitution_version="runtime-constitution-v1",
        allowed_actions=("read_file", "list_directory", "runtime_status", "noop"),
        review_required_actions=("apply_patch", "write_file", "execute_python", "run_python"),
        blocked_actions=("delete_repo", "force_push", "system_wipe"),
    )


def _governance() -> FakeGovernanceSnapshot:
    return FakeGovernanceSnapshot(governance_id="governance-snapshot-001")


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, step):
        self.calls.append(step)
        return {
            "ok": True,
            "action": step.get("type"),
            "message": "executed",
        }


def test_execution_gateway_allows_allowed_step_through_runtime_entry() -> None:
    executor = RecordingExecutor()

    result = call_execution_gateway(
        executor,
        {"type": "read_file", "path": "README.md"},
        governance_snapshot=_governance(),
        constitution=_constitution(),
    )

    assert result.ok is True
    assert result.invoked is True
    assert len(executor.calls) == 1
    assert result.result["action"] == "read_file"


def test_execution_gateway_blocks_review_required_step_before_executor() -> None:
    executor = RecordingExecutor()

    result = call_execution_gateway(
        executor,
        {"type": "apply_patch", "target_path": "core/runtime/example.py"},
        governance_snapshot=_governance(),
        constitution=_constitution(),
    )

    assert result.ok is False
    assert result.invoked is False
    assert result.gateway_error == "execution_step_requires_review"
    assert len(executor.calls) == 0

    decision = result.result["runtime_legality_decision"]
    assert decision["decision"] == "REVIEW"
    assert decision["requires_review"] is True
    assert decision["action_type"] == "apply_patch"
    assert decision["governance_id"] == "governance-snapshot-001"
    assert decision["constitution_version"] == "runtime-constitution-v1"


def test_execution_gateway_blocks_forbidden_step_before_executor() -> None:
    executor = RecordingExecutor()

    result = call_execution_gateway(
        executor,
        {"type": "system_wipe"},
        governance_snapshot=_governance(),
        constitution=_constitution(),
    )

    assert result.ok is False
    assert result.invoked is False
    assert result.gateway_error == "execution_step_blocked"
    assert len(executor.calls) == 0

    decision = result.result["runtime_legality_decision"]
    assert decision["decision"] == "BLOCK"
    assert decision["blocked"] is True
    assert decision["action_type"] == "system_wipe"
    assert "runtime.action.blocked:system_wipe" in decision["violated_rules"]


def test_execution_gateway_can_disable_legality_for_compatibility() -> None:
    executor = RecordingExecutor()

    result = call_execution_gateway(
        executor,
        {"type": "system_wipe"},
        governance_snapshot=_governance(),
        constitution=_constitution(),
        enforce_legality=False,
    )

    assert result.ok is True
    assert result.invoked is True
    assert len(executor.calls) == 1


def test_execution_gateway_without_constitution_keeps_existing_runtime_path() -> None:
    executor = RecordingExecutor()

    result = call_execution_gateway(
        executor,
        {"type": "write_file", "path": "tmp.txt"},
    )

    assert result.ok is True
    assert result.invoked is True
    assert len(executor.calls) == 1
