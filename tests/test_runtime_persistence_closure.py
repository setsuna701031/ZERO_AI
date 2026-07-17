from __future__ import annotations

import pytest

from core.runtime.runtime_persistence_closure import (
    RuntimePersistenceExecutionGraph,
    seal_runtime_persistence,
    validate_runtime_persistence_chain,
)


def _graph() -> dict[str, str]:
    return {
        "goal_id": "goal-child",
        "root_goal_id": "goal-root",
        "source_goal_id": "goal-source",
        "goal_lineage_id": "lineage-root",
        "branch_id": "branch-main",
        "branch_type": "mainline",
        "session_id": "session-1",
        "runtime_session_id": "runtime-session-1",
        "execution_id": "execution-1",
        "authority_decision_id": "authority-decision-1",
        "capability_id": "capability-1",
    }


def _persistence(persistence_id: str = "persist-1") -> dict[str, object]:
    return {
        "persistence_id": persistence_id,
        "payload": {"state": "saved"},
        "evidence_ids": ["evidence-1", "evidence-2"],
    }


def test_persistence_closure_seals_live_execution_graph() -> None:
    graph = RuntimePersistenceExecutionGraph.from_mapping(_graph())

    sealed = seal_runtime_persistence(_persistence(), execution_graph=graph)

    assert sealed.persistence_id == "persist-1"
    assert sealed.execution_graph.to_dict() == _graph()
    assert sealed.to_dict()["execution_fingerprint"] == graph.fingerprint
    assert sealed.to_dict()["payload"]["execution_graph"] == _graph()


def test_no_persistence_identity_drift() -> None:
    payload = _persistence()
    payload["execution_id"] = "execution-drift"

    with pytest.raises(ValueError, match="runtime_persistence_graph_drift:execution_id"):
        seal_runtime_persistence(payload, execution_graph=_graph())


def test_no_snapshot_drift() -> None:
    snapshot = _persistence("snapshot-1")
    snapshot["snapshot"] = {"capability_id": "capability-drift"}

    with pytest.raises(ValueError, match="runtime_persistence_graph_drift:capability_id"):
        validate_runtime_persistence_chain(
            _graph(),
            persistence_record=_persistence(),
            snapshot_record=snapshot,
        )


def test_resume_reuses_original_execution_fingerprint() -> None:
    graph = RuntimePersistenceExecutionGraph.from_mapping(_graph())
    resume = _persistence("resume-1")
    resume["execution_graph"] = _graph()
    resume["execution_fingerprint"] = graph.fingerprint

    result = validate_runtime_persistence_chain(
        graph,
        persistence_record=_persistence(),
        resume_record=resume,
    )

    assert result["valid"] is True
    assert result["checked_records"]["resume"] == "resume-1"
    assert result["execution_fingerprint"] == graph.fingerprint


def test_no_resume_remint_from_fingerprint_drift() -> None:
    resume = _persistence("resume-1")
    resume["execution_graph"] = _graph()
    resume["execution_fingerprint"] = "not-the-original-fingerprint"

    with pytest.raises(ValueError, match="runtime_persistence_resume_fingerprint_drift"):
        validate_runtime_persistence_chain(
            _graph(),
            persistence_record=_persistence(),
            resume_record=resume,
        )


def test_no_evidence_replacement_between_persistence_and_resume() -> None:
    resume = _persistence("resume-1")
    resume["evidence_ids"] = ["evidence-1", "evidence-replaced"]

    with pytest.raises(ValueError, match="runtime_persistence_evidence_ref_drift"):
        validate_runtime_persistence_chain(
            _graph(),
            persistence_record=_persistence(),
            resume_record=resume,
        )


def test_no_authority_or_capability_replacement() -> None:
    recovered = _persistence("recovered-1")
    recovered["recovered_graph"] = {
        "authority_decision_id": "authority-decision-2",
        "capability_id": "capability-1",
    }

    with pytest.raises(ValueError, match="runtime_persistence_graph_drift:authority_decision_id"):
        validate_runtime_persistence_chain(
            _graph(),
            persistence_record=_persistence(),
            recovered_record=recovered,
        )


def test_no_fallback_identity_source() -> None:
    graph = _graph()
    graph["runtime_session_id"] = "legacy"

    with pytest.raises(ValueError, match="runtime_persistence_forbidden_identity:runtime_session_id"):
        RuntimePersistenceExecutionGraph.from_mapping(graph)


def test_no_hidden_recovery_path_can_replace_identity() -> None:
    recovered = _persistence("recovered-1")
    recovered["recovery"] = {"goal_lineage_id": "lineage-drift"}

    with pytest.raises(ValueError, match="runtime_persistence_graph_drift:goal_lineage_id"):
        validate_runtime_persistence_chain(
            _graph(),
            persistence_record=_persistence(),
            recovered_record=recovered,
        )
