from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_agentloop_cannot_produce_sealed_execution_evidence_directly() -> None:
    from core.agent.agent_loop import AgentLoop
    from core.runtime.runtime_execution_result import build_runtime_execution_result

    result = AgentLoop(debug=False)._try_force_repo_edit_route(
        "replace bad with good in workspace/shared/evidence_boundary.py"
    )
    forged = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "execution_id": "agentloop-forged-evidence",
            "status": "succeeded",
            "evidence_seal_valid": True,
            "metadata": {
                "execution_source": "agent_loop",
                "producer_layer": "agent_loop",
            },
        }
    )

    assert result["mode"] == "forced_repo_edit_intent"
    assert result["execution_intent_only"] is True
    assert result["execution"]["mutation_executed"] is False
    assert "execution_evidence" not in result["execution"]
    assert forged["executed"] is False
    assert forged["execution_evidence"]["execution_legality"] == "denied"
    assert forged["execution_evidence"]["producer_layer"] == "agent_loop"


def test_scheduler_cannot_produce_sealed_execution_evidence_directly(tmp_path: Path) -> None:
    from core.runtime.runtime_execution_result import build_runtime_execution_result
    from core.tasks.scheduler import Scheduler

    scheduler = Scheduler(workspace_dir=str(tmp_path), allow_commands=True, debug=False)
    result = scheduler._try_force_repo_edit_at_create_task(
        "replace bad with good in workspace/shared/scheduler_evidence_boundary.py"
    )
    forged = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "execution_id": "scheduler-forged-evidence",
            "status": "succeeded",
            "metadata": {
                "execution_source": "scheduler",
                "producer_layer": "scheduler",
                "sealed_execution_evidence": True,
            },
        }
    )

    assert result["execution_intent_only"] is True
    assert result["mutation_executed"] is False
    assert result["status"] == scheduler.STATUS_QUEUED
    assert result["planner_result"]["steps"][0]["type"] == "code_chain_repair"
    assert forged["executed"] is False
    assert forged["execution_evidence"]["execution_legality"] == "denied"
    assert forged["execution_evidence"]["producer_layer"] == "scheduler"


def test_code_chain_visibility_artifacts_route_through_execution_owner() -> None:
    from core.agent.agent_loop import AgentLoop

    fake = _RecordingExecutionRuntime()
    loop = AgentLoop(debug=False, execution_runtime=fake)

    result = loop._write_code_chain_text(
        Path("workspace/audit/code_chain/diffs/probe.diff"),
        "--- before\n+++ after\n",
        reason="agent_loop_code_chain_diff_write",
        target_path="workspace/shared/probe.py",
        artifact_type="patch_diff",
    )

    call = fake.calls[0]
    assert result["ok"] is True
    assert call["step"]["type"] == "write_file"
    assert call["context"]["ownership_handoff"] == "agent_loop_to_agent_execution_runtime"
    assert call["context"]["lineage"]["artifact_class"] == "output_artifact"
    assert call["context"]["provenance"]["producer_layer"] == "agent_execution_runtime"
    assert call["context"]["metadata"]["sealed_execution_evidence"] is True


def test_unsealed_audit_and_output_artifacts_cannot_satisfy_evidence_seal() -> None:
    from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer
    from core.runtime.runtime_evidence_query import RuntimeEvidenceQuery

    external_output = SimpleNamespace(
        snapshot_id="external-snapshot",
        replay_id="external-replay",
        audit_id="external-audit",
        rollback_id="external-rollback",
        bundle_id="external-bundle",
        aggregate_status="succeeded",
        verification_result="verified",
        fingerprint="external-fingerprint",
    )
    records = {
        "snapshot": external_output,
        "replay": external_output,
        "audit": external_output,
        "rollback": external_output,
        "bundle": external_output,
    }

    summary = RuntimeEvidenceConsumer().read_records(records)
    sealed_state = RuntimeEvidenceQuery().sealed_state(summary)

    assert summary["ok"] is False
    assert summary["record_count"] == 0
    assert summary["present_records"] == []
    assert summary["missing_records"] == ["snapshot", "replay", "audit", "rollback", "bundle"]
    assert summary["invalid_records"] == ["snapshot", "replay", "audit", "rollback", "bundle"]
    assert sealed_state["sealed"] is False
    assert sealed_state["reason"] == "missing_evidence"


def test_governed_execution_remains_execution_evidence_source() -> None:
    from core.runtime.runtime_execution_result import build_runtime_execution_result

    step_result = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "execution_id": "step-exec-1",
            "status": "succeeded",
            "metadata": {"execution_source": "step_executor"},
        }
    )
    governed_result = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "execution_id": "gateway-exec-1",
            "status": "succeeded",
            "metadata": {"execution_source": "runtime_execution_gateway"},
        }
    )

    assert step_result["executed"] is True
    assert step_result["execution_evidence"]["execution_legality"] == "legal"
    assert step_result["execution_evidence"]["producer_layer"] == "step_executor"
    assert governed_result["executed"] is True
    assert governed_result["execution_evidence"]["execution_legality"] == "legal"
    assert governed_result["execution_evidence"]["producer_layer"] == "governed_execution"


def test_runtime_state_persistence_is_task_state_not_execution_proof(tmp_path: Path) -> None:
    from core.tasks.scheduler import Scheduler

    scheduler = Scheduler(workspace_dir=str(tmp_path), allow_commands=True, debug=False)
    task = scheduler._create_task_record(
        "replace bad with good in workspace/shared/runtime_state_boundary.py"
    )
    task_record = task["task"]

    assert task_record["runtime_state_file"].endswith("runtime_state.json")
    assert task["authority_context"]["authority_role"] == "orchestration"
    assert task["execution_intent_only"] is True
    assert task["mutation_executed"] is False
    assert "execution_evidence" not in task_record
    assert "evidence_seal_valid" not in task_record


class _RecordingExecutionRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_step(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ok": True, "execution_path": {"runtime_owns_execution": True}}
