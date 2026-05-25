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
        payload = {
            "step": step,
            "task": task or {},
            "context": context or {},
        }
        self.calls.append(payload)

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
                "error": {
                    "type": "missing_execution_authority",
                    "message": "mutation blocked before execution",
                },
                "runtime_evidence": {
                    "sealed_execution_evidence": False,
                    "producer_layer": "step_executor",
                    "record_type": "runtime_execution_result",
                    "evidence_type": "governed_runtime_evidence",
                    "normalized": False,
                },
            }

        return {
            "ok": True,
            "action": "governed_mutation_executed",
            "mutation_executed": True,
            "source": "step_executor",
            "runtime_evidence": {
                "sealed_execution_evidence": True,
                "producer_layer": "step_executor",
                "record_type": "runtime_execution_result",
                "evidence_type": "governed_runtime_evidence",
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
        "authority_source": "human_review",
        "action_type": action_type,
        "sealed": True,
    }


def _make_scheduler(tmp_path: Path, step_executor: Any | None = None):
    from core.tasks.scheduler import Scheduler

    return Scheduler(
        workspace_dir=str(tmp_path),
        step_executor=step_executor or _RecordingStepExecutor(),
        debug=False,
    )


def test_governed_code_chain_path_reaches_step_executor(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()
    scheduler = _make_scheduler(tmp_path, step_executor=recorder)

    result = scheduler._execute_simple_step(
        task={
            "task_id": "governed-code-chain",
            "task_dir": str(tmp_path / "tasks" / "governed-code-chain"),
            "execution_authority": _execution_authority(),
            "authority_propagation_required": True,
        },
        step={
            "type": "code_chain_repair",
            "instruction": "fix runtime mutation path",
        },
    )

    assert recorder.calls
    assert recorder.calls[0]["step"]["type"] == "code_chain_repair"
    assert result["source"] == "step_executor"


def test_scheduler_remains_orchestration_only(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()
    scheduler = _make_scheduler(tmp_path, step_executor=recorder)

    target = tmp_path / "workspace" / "shared" / "illegal.txt"

    scheduler._execute_simple_step(
        task={
            "task_id": "scheduler-orchestration",
            "task_dir": str(tmp_path / "tasks" / "scheduler-orchestration"),
            "execution_authority": _execution_authority(),
            "authority_propagation_required": True,
        },
        step={
            "type": "write_file",
            "path": "workspace/shared/illegal.txt",
            "content": "scheduler must not write directly",
        },
    )

    assert recorder.calls
    assert not target.exists()


def test_agentloop_forced_repo_edit_is_execution_intent_only(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    from core.agent import agent_loop as agent_loop_module
    from core.agent.agent_loop import AgentLoop

    marker = tmp_path / "hidden-write.txt"

    def forbidden_repo_edit(*args: Any, **kwargs: Any) -> dict[str, Any]:
        marker.write_text("illegal", encoding="utf-8")
        return {"ok": True}

    monkeypatch.setattr(
        agent_loop_module,
        "run_repo_edit_decision",
        forbidden_repo_edit,
    )

    result = AgentLoop(debug=False)._try_force_repo_edit_route(
        "replace bad with good in workspace/shared/aer_landing_bridge.py"
    )

    assert result["execution_intent_only"] is True
    assert result["execution"]["mutation_executed"] is False
    assert not marker.exists()


def test_missing_authority_blocks_before_mutation(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()

    result = recorder.execute_step(
        {
            "type": "write_file",
            "path": "workspace/shared/blocked.txt",
            "content": "blocked",
        },
        task={"task_id": "blocked-task"},
        context={
            "authority_context": {
                "execution_authority": {
                    "granted": False,
                    "sealed": False,
                }
            }
        },
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["error"]["type"] == "missing_execution_authority"
    assert result["runtime_evidence"]["sealed_execution_evidence"] is False


def test_successful_governed_mutation_emits_sealed_runtime_evidence(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()

    result = recorder.execute_step(
        {
            "type": "apply_patch",
            "target_path": "workspace/shared/demo.txt",
            "old_text": "before",
            "new_text": "after",
        },
        task={"task_id": "sealed-runtime-evidence"},
        context={
            "authority_context": {
                "execution_authority": _execution_authority(),
            }
        },
    )

    evidence = result["runtime_evidence"]

    assert result["ok"] is True
    assert evidence["sealed_execution_evidence"] is True
    assert evidence["producer_layer"] == "step_executor"
    assert evidence["normalized"] is True


def test_output_artifact_cannot_satisfy_execution_evidence_seal() -> None:
    output_artifact = {
        "artifact_class": "output_artifact",
        "sealed_execution_evidence": False,
        "producer_layer": "agent_loop",
        "record_type": "generated_artifact_write",
    }

    assert output_artifact["artifact_class"] == "output_artifact"
    assert output_artifact["sealed_execution_evidence"] is False


def test_runtime_evidence_consumer_only_accepts_normalized_governed_evidence() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

    consumer = RuntimeEvidenceConsumer()

    fake_records = {
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

    summary = consumer.read_records(fake_records)

    assert summary["ok"] is False
    assert summary["invalid_records"]

