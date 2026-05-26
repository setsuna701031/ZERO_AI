from __future__ import annotations

from dataclasses import dataclass

from core.runtime.step_executor import StepExecutor


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
        allowed_actions=("read_file", "noop"),
        review_required_actions=("apply_patch",),
        blocked_actions=("system_wipe",),
    )


def _governance() -> FakeGovernanceSnapshot:
    return FakeGovernanceSnapshot(
        governance_id="governance-snapshot-001"
    )


def test_step_executor_runtime_legality_blocks_execution() -> None:
    executor = StepExecutor()

    result = executor.execute_step(
        step={"type": "system_wipe"},
        context={
            "governance_snapshot": _governance(),
            "constitution": _constitution(),
        },
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "execution_step_blocked"

    decision = result["result"]["runtime_legality_decision"]

    assert decision["decision"] == "BLOCK"
    assert decision["blocked"] is True
    assert decision["action_type"] == "system_wipe"


def test_step_executor_runtime_legality_review_step_requires_authority_first() -> None:
    executor = StepExecutor()

    result = executor.execute_step(
        step={"type": "apply_patch"},
        context={
            "governance_snapshot": _governance(),
            "constitution": _constitution(),
        },
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"
    assert result["authority_decision"]["decision"] == "denied"
    assert result["authority_decision"]["reason"] == "missing_authority_metadata"
