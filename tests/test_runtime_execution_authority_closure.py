from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from core.runtime.runtime_evidence_surface import list_evidence
from core.runtime.runtime_execution_authority_evidence import (

    RUNTIME_EXECUTION_AUTHORITY_EVIDENCE_SCHEMA,
)
from core.runtime.runtime_execution_authority_gate import (
    RuntimeExecutionAuthorityDenied,
    RuntimeExecutionAuthorityGate,
)
pytestmark = [pytest.mark.contract, pytest.mark.integration]



def test_scheduler_direct_execution_is_blocked_with_evidence(tmp_path: Path) -> None:
    gate = RuntimeExecutionAuthorityGate()

    with pytest.raises(RuntimeExecutionAuthorityDenied) as context:
        gate.enforce(
            source="scheduler",
            action_type="command",
            metadata={"side_effect": True, "task_id": "task-scheduler"},
            repo_root=tmp_path,
            task_id="task-scheduler",
        )

    evidence = context.value.evidence
    indexed = list_evidence("task-scheduler", repo_root=tmp_path)

    assert context.value.decision.blocked is True
    assert context.value.decision.reason == "orchestration_surface_cannot_execute_side_effect"
    assert evidence["schema"] == RUNTIME_EXECUTION_AUTHORITY_EVIDENCE_SCHEMA
    assert evidence["blocked"] is True
    assert evidence["no_execution_performed"] is True
    assert indexed[0]["evidence_type"] == "runtime_execution_authority"
    assert Path(indexed[0]["path"]).exists()


def test_agent_loop_direct_execution_is_blocked() -> None:
    gate = RuntimeExecutionAuthorityGate()

    with pytest.raises(RuntimeExecutionAuthorityDenied) as context:
        gate.enforce(
            source="agent_loop",
            action_type="write_file",
            metadata={"side_effect": True},
        )

    assert context.value.decision.blocked is True
    assert context.value.decision.reason == "orchestration_surface_cannot_execute_side_effect"
    assert context.value.evidence["blocked"] is True


def test_helper_bridge_direct_execution_is_blocked() -> None:
    gate = RuntimeExecutionAuthorityGate()

    with pytest.raises(RuntimeExecutionAuthorityDenied) as context:
        gate.enforce(
            source="core.tasks.scheduler_core.command_step_helpers",
            action_type="command_execution",
            metadata={"effect_type": "command_execution"},
        )

    assert context.value.decision.blocked is True
    assert context.value.decision.reason == "helper_bridge_cannot_execute_side_effect"


def test_runtime_execution_gateway_is_allowed() -> None:
    decision = RuntimeExecutionAuthorityGate().enforce(
        source="runtime.execution_gateway",
        action_type="command",
        metadata={"side_effect": True},
    )

    assert decision.allowed is True
    assert decision.blocked is False
    assert decision.reason == "canonical_execution_authority"


def test_runtime_executor_is_allowed() -> None:
    decision = RuntimeExecutionAuthorityGate().enforce(
        source="runtime.executor",
        action_type="file_mutation",
        metadata={"side_effect": True},
    )

    assert decision.allowed is True
    assert decision.blocked is False
    assert decision.reason == "canonical_execution_authority"


def test_non_side_effect_action_is_allowed_for_orchestration() -> None:
    decision = RuntimeExecutionAuthorityGate().enforce(
        source="scheduler",
        action_type="read",
        metadata={"side_effect": False},
    )

    assert decision.allowed is True
    assert decision.reason == "non_side_effect_action"


def test_blocked_authority_evidence_payload_matches_disk(tmp_path: Path) -> None:
    gate = RuntimeExecutionAuthorityGate()

    with pytest.raises(RuntimeExecutionAuthorityDenied) as context:
        gate.enforce(
            source="core.agent.agent_loop",
            action_type="apply_patch",
            metadata={"task_id": "task-auth", "side_effect": True},
            repo_root=tmp_path,
            task_id="task-auth",
        )

    indexed = list_evidence("task-auth", repo_root=tmp_path)
    payload = json.loads(Path(indexed[0]["path"]).read_text(encoding="utf-8"))

    assert payload == context.value.evidence
    assert payload["reason"] == "orchestration_surface_cannot_execute_side_effect"
    assert payload["decision"]["source"] == "core.agent.agent_loop"
    assert indexed[0]["metadata"]["blocked"] is True


def test_execution_authority_closure_adds_no_scheduler_or_agent_loop_patch() -> None:
    import core.runtime.runtime_execution_authority_evidence as evidence
    import core.runtime.runtime_execution_authority_gate as gate
    import core.runtime.runtime_execution_authority_policy as policy

    source = "\n".join(
        [
            inspect.getsource(policy),
            inspect.getsource(gate),
            inspect.getsource(evidence),
        ]
    )

    assert "from core.agent import agent_loop" not in source
    assert "from core.tasks import scheduler" not in source
    assert "from core.runtime.step_executor import StepExecutor" not in source
    assert "subprocess." not in source
    assert "os.system" not in source
    assert "run_mutation_runtime_pipeline(" not in source
    assert "run_governed_mutation_runtime(" not in source
    assert "run_recovery(" not in source
    assert "execute_recovery(" not in source
