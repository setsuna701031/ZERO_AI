from __future__ import annotations

from pathlib import Path

import pytest

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime
from core.goals.goal_lineage_contract import (
    RUNTIME_IDENTITY_GRAPH_FIELDS,
    assert_runtime_identity_graph_consistency,
    attach_runtime_identity_graph,
    bind_runtime_identity_graph,
    build_runtime_execution_id,
    canonical_runtime_identity_graph,
    create_goal_branch_lineage,
    create_root_goal_lineage,
)
from core.runtime.runtime_authority_seal import _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN
from core.runtime.runtime_evidence_authority import RuntimeEvidenceAuthority
from core.runtime.runtime_execution_authority import (
    capability_from_authority_decision,
    propagate_runtime_capability,
)
from core.runtime.runtime_execution_authority_policy import evaluate_execution_authority
from core.runtime.runtime_persistence_service import RuntimePersistenceService
from core.runtime.runtime_session_resume import RuntimeSessionResume


class _FileService:
    def write_text(self, **kwargs):
        return {"ok": True, "metadata": kwargs.get("metadata", {})}


def _identity():
    lineage = create_root_goal_lineage(
        goal_id="goal:root",
        session_id="session:1",
        runtime_session_id="runtime-session:1",
    )
    execution_id = build_runtime_execution_id(lineage, task_id="task:1")
    graph = bind_runtime_identity_graph(lineage, execution_id=execution_id)
    decision = evaluate_execution_authority(
        source="runtime_dispatcher",
        action_type="issue_capability",
        metadata={"side_effect": False, "execution_id": execution_id},
    )
    capability = capability_from_authority_decision(
        decision,
        issuer="RuntimeExecutionAuthorityPolicy",
        resource="runtime_task",
        action="execute",
        scope={"task_id": "task:1", "execution_id": execution_id},
        lineage={"goal_lineage_id": lineage["goal_lineage_id"], "execution_id": execution_id},
    )
    graph = bind_runtime_identity_graph(graph, capability_id=capability.capability_id)
    return lineage, graph, capability


def test_goal_identity_closure() -> None:
    lineage, graph, _ = _identity()
    assert graph["root_goal_id"] == graph["source_goal_id"] == graph["goal_id"]
    assert graph["goal_lineage_id"] == lineage["goal_lineage_id"]
    assert graph["branch_type"] == "root"


def test_session_identity_closure() -> None:
    _, graph, capability = _identity()
    assert graph["session_id"] == "session:1"
    assert graph["runtime_session_id"] == "runtime-session:1"


def test_execution_identity_closure() -> None:
    _, graph, capability = _identity()
    assert graph["execution_id"] == capability.execution_id


def test_capability_identity_closure() -> None:
    _, graph, capability = _identity()
    assert graph["capability_id"] == capability.capability_id
    with pytest.raises(ValueError, match="runtime_identity_drift:capability_id"):
        bind_runtime_identity_graph(graph, capability_id="runtime-capability:other")


def test_evidence_identity_closure() -> None:
    _, graph, capability = _identity()
    authority = RuntimeEvidenceAuthority(
        evidence_id="evidence:1",
        issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
        capability_provenance=capability,
        identity_graph=graph,
    )
    evidence = authority.to_dict()
    assert evidence["evidence_id"] == "evidence:1"
    assert evidence["runtime_identity_graph"]["evidence_id"] == "evidence:1"
    assert_runtime_identity_graph_consistency(evidence, evidence["runtime_identity_graph"], require_complete=True)


def test_persistence_identity_closure(tmp_path: Path) -> None:
    _, graph, capability = _identity()
    evidence = RuntimeEvidenceAuthority(
        evidence_id="evidence:1",
        issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
        capability_provenance=capability,
        identity_graph=graph,
    ).to_dict()
    persistence = RuntimePersistenceService(workspace_root=tmp_path, source="test", file_service=_FileService())
    result = persistence.write_json(
        tmp_path / "evidence.json",
        evidence,
        metadata={
            **propagate_runtime_capability({}, capability, stage="mutation"),
            "runtime_identity_graph": evidence["runtime_identity_graph"],
        },
    )
    assert_runtime_identity_graph_consistency(evidence, result, require_complete=True)


def test_resume_identity_closure_recovers_original_graph(tmp_path: Path) -> None:
    _, graph, capability = _identity()
    evidence_graph = bind_runtime_identity_graph(graph, evidence_id="evidence:1")
    task = attach_runtime_identity_graph(
        {
            "task_id": "task:1",
            "status": "running",
            "runtime_identity": {
                "session_id": graph["session_id"],
                "runtime_session_id": graph["runtime_session_id"],
            },
            **propagate_runtime_capability({}, capability, stage="persistence"),
        },
        evidence_graph,
    )
    storage = tmp_path / "resume.json"
    RuntimeSessionResume(workspace_root=tmp_path, storage_path=storage).create_session_record(
        session_id=graph["session_id"], tasks=[task]
    )
    restored = RuntimeSessionResume(workspace_root=tmp_path, storage_path=storage).get_record(graph["session_id"])
    restored_graph = canonical_runtime_identity_graph(restored.snapshots[0].task["runtime_identity_graph"], require_complete=True)
    assert restored_graph == canonical_runtime_identity_graph(evidence_graph, require_complete=True)


def test_continuation_identity_closure() -> None:
    lineage, _, _ = _identity()
    branch = create_goal_branch_lineage(
        lineage,
        goal_id="goal:continuation:1",
        branch_type="continuation",
        branch_id="continuation:1",
    )
    runtime = ContinuationRuntime.start("goal:root", goal_lineage=lineage).record_work_item(branch)
    assert runtime.root_goal_id == lineage["root_goal_id"]
    assert runtime.source_goal_id == lineage["source_goal_id"]
    assert runtime.branch_type == "continuation"


def test_replan_identity_closure() -> None:
    lineage, _, _ = _identity()
    runtime = ReplanRuntime.start(goal_lineage=lineage).record_replan({"request_id": "replan:1"})
    assert runtime.root_goal_id == lineage["root_goal_id"]
    assert runtime.source_goal_id == lineage["source_goal_id"]
    assert runtime.branch_type == "replan"
    assert runtime.branch_id == "replan:1"


def test_no_fallback_identity_source() -> None:
    for field in ("goal_id", "session_id", "runtime_session_id"):
        kwargs = {
            "goal_id": "goal:root",
            "session_id": "session:1",
            "runtime_session_id": "runtime-session:1",
        }
        kwargs[field] = "unknown"
        with pytest.raises(ValueError, match="invalid_runtime_identity"):
            create_root_goal_lineage(**kwargs)


def test_no_hidden_parallel_identity_source() -> None:
    root = Path(__file__).resolve().parents[1]
    resume_source = (root / "core/runtime/runtime_session_resume.py").read_text(encoding="utf-8-sig")
    continuation_source = (root / "core/adaptive/continuation_runtime.py").read_text(encoding="utf-8-sig")
    replan_source = (root / "core/adaptive/replan_runtime.py").read_text(encoding="utf-8-sig")
    assert "def _new_session_id" not in resume_source
    assert 'f"goal-session-' not in continuation_source
    assert 'f"goal-runtime-' not in continuation_source
    assert 'f"goal-session-' not in replan_source
    assert set(RUNTIME_IDENTITY_GRAPH_FIELDS) >= {"execution_id", "capability_id", "evidence_id"}


def test_non_mainline_findings_are_complete() -> None:
    doc = (Path(__file__).resolve().parents[1] / "docs/architecture/runtime_identity_closure.md").read_text(encoding="utf-8")
    for finding in (
        "parallel identity systems", "legacy lineage systems", "hidden lineage source",
        "resume identity drift", "continuation lineage drift", "replan lineage drift",
        "ownership/identity mixing", "evidence/identity drift", "capability/identity drift",
        "persistence/identity drift",
    ):
        assert finding in doc
