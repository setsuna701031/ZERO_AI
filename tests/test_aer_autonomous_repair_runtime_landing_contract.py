from __future__ import annotations

from pathlib import Path
from typing import Any


class _RecordingStepExecutor:
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
                "kwargs": kwargs,
            }
        )

        authority_context = (
            (context or {}).get("authority_context")
            if isinstance(context, dict)
            else {}
        ) or {}
        execution_authority = authority_context.get("execution_authority") or {}

        if not execution_authority.get("granted"):
            return {
                "ok": False,
                "blocked": True,
                "action": "repair_mutation_blocked",
                "error": {
                    "type": "missing_execution_authority",
                    "message": "repair mutation blocked before execution",
                },
                "runtime_evidence": {
                    "producer_layer": "step_executor",
                    "evidence_type": "governed_runtime_evidence",
                    "sealed_execution_evidence": False,
                    "normalized": False,
                },
            }

        return {
            "ok": True,
            "action": "governed_repair_mutation_executed",
            "source": "step_executor",
            "mutation_executed": True,
            "runtime_evidence": {
                "producer_layer": "step_executor",
                "evidence_type": "governed_runtime_evidence",
                "sealed_execution_evidence": True,
                "normalized": True,
                "execution_authority": execution_authority,
            },
            "output_artifact": {
                "artifact_class": "output_artifact",
                "sealed_execution_evidence": False,
            },
        }


def _execution_authority(action_type: str = "mutation") -> dict[str, Any]:
    return {
        "granted": True,
        "sealed": True,
        "action_type": action_type,
        "authority_source": "human_review",
    }


def _authority_context(granted: bool = True) -> dict[str, Any]:
    return {
        "authority_phase": "taskrunner_propagation",
        "authority_layer": "task_runner",
        "authority_role": "propagation",
        "execution_authority_granted": False,
        "can_execute_privileged_step": False,
        "execution_authority": (
            _execution_authority()
            if granted
            else {
                "granted": False,
                "sealed": False,
                "action_type": "mutation",
                "authority_source": "missing",
            }
        ),
    }


def _repair_plan(path: str = "workspace/shared/repaired.py") -> dict[str, Any]:
    return {
        "ok": True,
        "classification": "python_repair",
        "summary": "deterministic repair plan",
        "actions": [
            {
                "type": "write_file",
                "path": path,
                "content": "def repaired():\n    return True\n",
                "reason": "repair failed source",
            }
        ],
    }


def test_repair_injection_creates_governed_execution_intent_only(
    tmp_path: Path,
) -> None:
    from core.runtime.repair_step_injector import RepairStepInjector

    target = tmp_path / "workspace" / "shared" / "repaired.py"
    injector = RepairStepInjector()

    result = injector.build_injection(
        repair_plan=_repair_plan("workspace/shared/repaired.py"),
        task={
            "task_id": "repair-intent",
            "authority_context": _authority_context(),
        },
        failed_step={"type": "run_python"},
        failed_result={"ok": False, "error": {"type": "syntax_error"}},
    )

    payload = result.to_dict()
    steps = payload["steps"]

    assert payload["ok"] is True
    assert steps
    assert steps[0]["type"] == "governed_repair_mutation"
    assert steps[0]["repair_injected"] is True
    assert steps[0]["mutation"]["op_type"] == "write_file"
    assert not target.exists()


def test_readonly_runtime_blocks_repair_injection() -> None:
    from core.runtime.repair_step_injector import RepairStepInjector

    result = RepairStepInjector().build_injection(
        repair_plan=_repair_plan(),
        task={"task_id": "readonly-repair", "runtime_mode": "replay"},
        failed_step={"type": "run_python"},
        failed_result={"ok": False},
    )

    payload = result.to_dict()

    assert payload["ok"] is False
    assert "cannot inject repair steps" in payload["reason"]
    assert payload["diagnostics"]["guard_mode"] == "readonly_runtime_repair_injection_blocked"


def test_governed_repair_step_reaches_step_executor_with_authority() -> None:
    executor = _RecordingStepExecutor()
    step = {
        "type": "governed_repair_mutation",
        "mutation": {
            "op_type": "write_file",
            "target_path": "workspace/shared/repaired.py",
            "content": "def repaired():\n    return True\n",
        },
    }

    result = executor.execute_step(
        step,
        task={"task_id": "repair-chain"},
        context={"authority_context": _authority_context(granted=True)},
    )

    assert executor.calls
    assert executor.calls[0]["step"]["type"] == "governed_repair_mutation"
    assert result["ok"] is True
    assert result["source"] == "step_executor"
    assert result["runtime_evidence"]["sealed_execution_evidence"] is True


def test_autonomous_repair_mutation_blocks_without_authority() -> None:
    executor = _RecordingStepExecutor()

    result = executor.execute_step(
        {
            "type": "governed_repair_mutation",
            "mutation": {
                "op_type": "write_file",
                "target_path": "workspace/shared/blocked.py",
                "content": "blocked",
            },
        },
        task={"task_id": "blocked-repair"},
        context={"authority_context": _authority_context(granted=False)},
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["error"]["type"] == "missing_execution_authority"
    assert result["runtime_evidence"]["sealed_execution_evidence"] is False


def test_rollback_execution_requires_governed_authority() -> None:
    executor = _RecordingStepExecutor()
    rollback_step = {
        "type": "apply_patch",
        "target_path": "workspace/shared/rollback.py",
        "old_text": "after",
        "new_text": "before",
        "rollback": True,
    }

    denied = executor.execute_step(
        rollback_step,
        task={"task_id": "rollback-denied"},
        context={"authority_context": _authority_context(granted=False)},
    )
    allowed = executor.execute_step(
        rollback_step,
        task={"task_id": "rollback-allowed"},
        context={"authority_context": _authority_context(granted=True)},
    )

    assert denied["ok"] is False
    assert denied["blocked"] is True
    assert allowed["ok"] is True
    assert allowed["mutation_executed"] is True


def test_repair_output_artifact_is_not_execution_evidence() -> None:
    output_artifact = {
        "artifact_class": "output_artifact",
        "producer_layer": "agent_loop",
        "sealed_execution_evidence": False,
        "record_type": "generated_repair_report",
    }

    assert output_artifact["artifact_class"] == "output_artifact"
    assert output_artifact["sealed_execution_evidence"] is False


def test_replay_like_external_records_do_not_satisfy_runtime_evidence_consumer() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    records = {
        "snapshot": {
            "record_type": "execution_plan_snapshot",
            "producer_layer": "external",
            "normalized": False,
        },
        "replay": {
            "record_type": "execution_replay_record",
            "producer_layer": "external",
            "normalized": False,
        },
        "audit": {
            "record_type": "execution_audit_record",
            "producer_layer": "external",
            "normalized": False,
        },
        "rollback": {
            "record_type": "rollback_verification_record",
            "producer_layer": "external",
            "normalized": False,
        },
        "bundle": {
            "record_type": "runtime_evidence_bundle",
            "producer_layer": "external",
            "normalized": False,
        },
    }

    summary = RuntimeEvidenceConsumer().read_records(records)

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert summary["invalid_records"]
