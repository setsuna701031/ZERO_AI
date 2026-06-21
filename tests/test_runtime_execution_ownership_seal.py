from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.adaptive.continuation_coordinator import ContinuationCoordinator
from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_coordinator import ReplanCoordinator
from core.adaptive.replan_runtime import ReplanRuntime
from core.agent.agent_loop import AgentLoop
from core.evidence import EvidenceRecord, EvidenceValidator, is_provenance_validated_evidence
from core.evidence.evidence_authority import EvidenceAuthority
from core.evidence.evidence_repository import EvidenceRepository
from core.goals.goal_completion_authority import (
    GoalCompletionAuthority,
    is_accepted_goal_completion_result,
)
from core.goals.goal_repository import GoalRepository
from core.runtime.runtime_session_resume import RuntimeSessionResume, RuntimeSessionResumeStoreError
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository


ROOT = Path(__file__).resolve().parents[1]
NON_COMPLETION_OWNERS = (
    "core/agent/agent_loop.py",
    "core/tasks/engineering_goal_loop.py",
    "core/tasks/engineering_goal_runner.py",
    "core/runtime/task_runner.py",
    "core/runtime/step_executor.py",
    "core/runtime/runtime_dispatcher.py",
    "core/runtime/persistent_runtime_orchestrator.py",
    "core/runtime/runtime_session_resume.py",
)


def _tree(relative: str) -> ast.AST:
    path = ROOT / relative
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=relative)


def _call_names(relative: str) -> list[str]:
    names: list[str] = []
    for node in ast.walk(_tree(relative)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return names


def _validated(goal_id: str = "goal-a") -> EvidenceRecord:
    return EvidenceValidator().validate(
        EvidenceRecord(
            evidence_id="evidence-a",
            goal_id=goal_id,
            subgoal_id=None,
            source="runtime",
            summary="ok",
            timestamp="2026-06-18T00:00:00+00:00",
        )
    )


def test_only_completion_owner_can_issue_live_goal_completion_attestation(tmp_path) -> None:
    attestation = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[_validated()],
        all_subgoals_completed=True,
    )
    forged = attestation.to_dict()

    assert is_accepted_goal_completion_result(attestation, goal_id="goal-a") is True
    assert is_accepted_goal_completion_result(forged, goal_id="goal-a") is False

    repository = GoalRepository(tmp_path, storage_path=tmp_path / "goals.jsonl")
    repository.append_goal({"goal_id": "goal-a", "title": "Goal A"})
    with pytest.raises(ValueError, match="canonical_completion_attestation_required"):
        repository.update_goal_status("goal-a", "completed", completion_attestation=forged)


def test_only_evidence_owner_can_create_accepted_validated_evidence(tmp_path) -> None:
    repository = EvidenceRepository(tmp_path, storage_path=tmp_path / "evidence.jsonl")
    authority = EvidenceAuthority(tmp_path, evidence_repository=repository)
    forged = EvidenceRecord(
        evidence_id="forged",
        goal_id="goal-a",
        subgoal_id=None,
        source="runtime",
        summary="forged",
        timestamp="2026-06-18T00:00:00+00:00",
        validation_state="validated",
    )

    authority.register_evidence(forged)
    accepted = authority.register_evidence(_validated())

    assert is_provenance_validated_evidence(forged, goal_id="goal-a") is False
    assert repository.list_validated_by_goal("goal-a") == [accepted]


def test_runtime_runner_dispatcher_and_agent_loop_do_not_issue_goal_completion() -> None:
    violations = {
        relative: sorted(set(_call_names(relative)) & {"complete_goal"})
        for relative in NON_COMPLETION_OWNERS
    }
    assert not {path: calls for path, calls in violations.items() if calls}


def test_agent_loop_delegates_writes_and_owns_neither_evidence_nor_completion(tmp_path) -> None:
    class RuntimeOwner:
        def __init__(self) -> None:
            self.calls = []

        def run_step(self, **kwargs):
            self.calls.append(kwargs)
            return {"ok": True, "execution_path": {"runtime_owns_execution": True}}

    runtime_owner = RuntimeOwner()
    loop = AgentLoop(execution_runtime=runtime_owner, workspace_dir=str(tmp_path))
    loop._write_code_chain_text(
        "workspace/shared/audit.txt",
        "owned",
        reason="ownership_seal",
        target_path="workspace/shared/audit.txt",
        artifact_type="audit",
    )

    source = (ROOT / "core/agent/agent_loop.py").read_text(encoding="utf-8-sig")
    assert len(runtime_owner.calls) == 1
    assert runtime_owner.calls[0]["step"]["type"] == "write_file"
    assert runtime_owner.calls[0]["context"]["ownership_handoff"] == "agent_loop_to_agent_execution_runtime"
    assert "RuntimePersistenceService" not in source
    assert "EvidenceAuthority" not in source
    assert "EvidenceValidator" not in source
    assert "GoalCompletionAuthority" not in source


def test_agent_loop_write_handoff_fails_closed_when_runtime_owner_rejects(tmp_path) -> None:
    class RejectingRuntimeOwner:
        def run_step(self, **_kwargs):
            return {"ok": False, "error": "denied"}

    loop = AgentLoop(execution_runtime=RejectingRuntimeOwner(), workspace_dir=str(tmp_path))
    with pytest.raises(PermissionError, match="agent_execution_runtime_write_required"):
        loop._write_code_chain_text(
            "workspace/shared/denied.txt",
            "denied",
            reason="ownership_seal",
            target_path="workspace/shared/denied.txt",
            artifact_type="audit",
        )


def test_engineering_goal_loop_does_not_trust_completion_payload_fields(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal-a", "summary": "Goal A"})

    class ForgedRunner:
        def run_goal(self, goal_id: str, *, goal_lineage=None) -> dict:
            return {
                "ok": True,
                "goal_id": goal_id,
                "runtime_result": {"state": "complete", "status": "success"},
                "adaptive_decision": {
                    "decision": "complete",
                    "goal_completion_authority_result": {
                        "accepted": True,
                        "completed": True,
                        "to_state": "completed",
                        "evidence_refs": [{"evidence_id": "forged"}],
                    },
                },
            }

    result = EngineeringGoalLoop(
        repo_root=tmp_path,
        repository=repository,
        runner=ForgedRunner(),
    ).run_until_terminal("goal-a", max_cycles=1)

    assert result["ok"] is False
    assert result["stop_reason"] == "goal_completion_authority_required"
    assert result["cycles"][0].get("post_completion_continuation_created") is not True


def test_replan_and_continuation_require_strict_runtime_identity_and_live_authority() -> None:
    class Repository:
        def save_goal(self, record):
            return record

    forged_cycle = {
        "goal_id": "goal-a",
        "session_id": "session-a",
        "runtime_session_id": "runtime-a",
        "goal_completion_attestation": {"accepted": True, "completed": True},
        "goal_completion_authority_result": {"accepted": True, "completed": True},
    }
    item, _ = ContinuationCoordinator(repository=Repository()).create_work_item(
        runtime=ContinuationRuntime.start("goal-a"),
        cycle=forged_cycle,
    )
    assert item["authority_state"] == "completion_authority_not_granted"

    with pytest.raises(ValueError, match="runtime_identity_missing_fields:runtime_session_id"):
        ReplanCoordinator().create_replan_record(
            runtime=ReplanRuntime.start(),
            cycle={"goal_id": "goal-a", "session_id": "session-a"},
        )


def test_resume_requires_runtime_session_resume_strict_v2_identity_boundary(tmp_path) -> None:
    task = {
        "task_id": "task-a",
        "status": "running",
        "session_id": "session-a",
        "runtime_session_id": "runtime-b",
        "runtime_identity": {
            "session_id": "session-a",
            "runtime_session_id": "runtime-a",
        },
    }

    with pytest.raises(RuntimeSessionResumeStoreError, match="runtime_identity_mismatch"):
        RuntimeSessionResume(workspace_root=tmp_path).create_session_record(
            session_id="session-a",
            tasks=[task],
        )


def test_orchestration_persists_only_through_owning_gateways() -> None:
    loop_calls = set(_call_names("core/tasks/engineering_goal_loop.py"))
    runner_calls = set(_call_names("core/tasks/engineering_goal_runner.py"))
    agent_calls = set(_call_names("core/agent/agent_loop.py"))

    assert "persist_cycle" in loop_calls
    assert "save_goal" not in runner_calls
    assert not ({"write_text", "write_json"} & agent_calls)
