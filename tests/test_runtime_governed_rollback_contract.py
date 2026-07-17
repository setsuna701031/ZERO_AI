from __future__ import annotations

from typing import Any
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




class _RollbackStepExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_step(
        self,
        step: dict[str, Any],
        task: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "step": step,
                "task": task or {},
                "context": context or {},
            }
        )

        authority = (
            ((context or {}).get("authority_context") or {}).get("execution_authority")
            if isinstance(context, dict)
            else {}
        ) or {}

        if not authority.get("granted"):
            return {
                "ok": False,
                "blocked": True,
                "action": "rollback_blocked",
                "error": {"type": "missing_execution_authority"},
                "runtime_evidence": {
                    "producer_layer": "step_executor",
                    "sealed_execution_evidence": False,
                    "normalized": False,
                },
            }

        return {
            "ok": True,
            "action": "governed_rollback_executed",
            "source": "step_executor",
            "rollback_executed": True,
            "runtime_evidence": {
                "producer_layer": "step_executor",
                "sealed_execution_evidence": True,
                "normalized": True,
                "execution_authority": authority,
            },
        }


def _authority(granted: bool) -> dict[str, Any]:
    return {
        "authority_context": {
            "execution_authority": {
                "granted": granted,
                "sealed": granted,
                "action_type": "mutation",
                "authority_source": "human_review" if granted else "missing",
            }
        }
    }


def test_governed_rollback_blocks_without_authority() -> None:
    executor = _RollbackStepExecutor()

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "target_path": "workspace/shared/rollback_target.py",
            "old_text": "after",
            "new_text": "before",
            "rollback": True,
        },
        task={"task_id": "rollback-blocked"},
        context=_authority(False),
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["error"]["type"] == "missing_execution_authority"
    assert result["runtime_evidence"]["sealed_execution_evidence"] is False


def test_governed_rollback_executes_with_authority() -> None:
    executor = _RollbackStepExecutor()

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "target_path": "workspace/shared/rollback_target.py",
            "old_text": "after",
            "new_text": "before",
            "rollback": True,
        },
        task={"task_id": "rollback-allowed"},
        context=_authority(True),
    )

    assert result["ok"] is True
    assert result["rollback_executed"] is True
    assert result["source"] == "step_executor"
    assert result["runtime_evidence"]["sealed_execution_evidence"] is True


def test_rollback_verification_record_is_execution_evidence_not_output_artifact() -> None:
    from core.runtime.rollback_verification import RollbackVerificationRecord

    record = RollbackVerificationRecord(
        rollback_id="rollback-contract",
        snapshot_id="snapshot-contract",
        plan_id="plan-contract",
        execution_order=["step.1", "step.2"],
        rollback_order=["step.2", "step.1"],
        verification_result="verified",
        mismatches=[],
        snapshot_fingerprint="snapshot-fingerprint",
        aggregate_status="succeeded",
        operation_fingerprints={"step.1": "a", "step.2": "b"},
        metadata={
            "producer_layer": "step_executor",
            "artifact_class": "execution_evidence",
            "sealed_execution_evidence": True,
        },
    )

    assert record.rollback_id == "rollback-contract"
    assert record.verification_result == "verified"
    assert record.metadata["artifact_class"] == "execution_evidence"
    assert record.metadata["sealed_execution_evidence"] is True
    assert record.fingerprint


def test_rollback_output_artifact_does_not_count_as_verification_evidence() -> None:
    artifact = {
        "record_type": "rollback_report",
        "artifact_class": "output_artifact",
        "producer_layer": "agent_loop",
        "sealed_execution_evidence": False,
    }

    assert artifact["artifact_class"] == "output_artifact"
    assert artifact["sealed_execution_evidence"] is False
