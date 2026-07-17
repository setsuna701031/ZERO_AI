from __future__ import annotations

import pytest

from core.runtime.runtime_governance_graph_closure import (
    RuntimeGovernanceGraph,
    seal_runtime_governance_graph,
    validate_runtime_governance_graph_chain,
)


def _graph() -> dict[str, str]:
    return {
        "goal_id": "goal-child",
        "root_goal_id": "goal-root",
        "source_goal_id": "goal-source",
        "goal_lineage_id": "lineage-root",
        "session_id": "session-1",
        "runtime_session_id": "runtime-session-1",
        "execution_id": "execution-1",
        "authority_decision_id": "authority-decision-1",
        "capability_id": "capability-1",
        "identity_fingerprint": "identity-fp-1",
        "goal_owner": "goal_loop",
        "session_owner": "session_coordinator",
        "execution_owner": "runtime_dispatcher",
        "capability_owner": "runtime_execution_authority",
        "evidence_owner": "runtime_evidence_authority",
        "persistence_owner": "runtime_persistence_service",
        "ownership_fingerprint": "ownership-fp-1",
        "mutation_request_id": "mutation-request-1",
        "mutation_id": "mutation-1",
        "mutation_fingerprint": "mutation-fp-1",
        "evidence_id": "evidence-1",
        "persistence_id": "persist-1",
    }


def _record(closure_id: str) -> dict[str, object]:
    return {"governance_closure_id": closure_id, "payload": {"state": "sealed"}}


def test_governance_graph_closure_seals_single_canonical_graph() -> None:
    graph = RuntimeGovernanceGraph.from_mapping(_graph())

    sealed = seal_runtime_governance_graph(_record("governance-1"), governance_graph=graph)

    assert sealed.closure_id == "governance-1"
    assert sealed.governance_graph.to_dict() == _graph()
    assert sealed.to_dict()["payload"]["governance_graph"] == _graph()
    assert sealed.to_dict()["governance_fingerprint"] == graph.fingerprint


def test_authority_to_capability_consistency() -> None:
    authority = _record("authority-graph")
    authority["capability_id"] = "capability-drift"

    with pytest.raises(ValueError, match="runtime_governance_graph_drift:authority:capability_id"):
        validate_runtime_governance_graph_chain(_graph(), authority_record=authority)


def test_capability_to_identity_consistency() -> None:
    capability = _record("capability-graph")
    capability["identity_graph"] = {"execution_id": "execution-drift"}

    with pytest.raises(ValueError, match="runtime_governance_graph_drift:capability:execution_id"):
        validate_runtime_governance_graph_chain(_graph(), capability_record=capability)


def test_identity_to_ownership_consistency() -> None:
    identity = _record("identity-graph")
    identity["ownership_graph"] = {"execution_owner": "task_runner"}

    with pytest.raises(ValueError, match="runtime_governance_graph_drift:identity:execution_owner"):
        validate_runtime_governance_graph_chain(_graph(), identity_record=identity)


def test_ownership_to_mutation_consistency() -> None:
    ownership = _record("ownership-graph")
    ownership["mutation_graph"] = {"mutation_id": "mutation-drift"}

    with pytest.raises(ValueError, match="runtime_governance_graph_drift:ownership:mutation_id"):
        validate_runtime_governance_graph_chain(_graph(), ownership_record=ownership)


def test_mutation_to_evidence_consistency() -> None:
    mutation = _record("mutation-graph")
    mutation["evidence_id"] = "evidence-drift"

    with pytest.raises(ValueError, match="runtime_governance_graph_drift:mutation:evidence_id"):
        validate_runtime_governance_graph_chain(_graph(), mutation_record=mutation)


def test_evidence_to_persistence_consistency() -> None:
    evidence = _record("evidence-graph")
    evidence["persistence_id"] = "persist-drift"

    with pytest.raises(ValueError, match="runtime_governance_graph_drift:evidence:persistence_id"):
        validate_runtime_governance_graph_chain(_graph(), evidence_record=evidence)


def test_persistence_to_resume_consistency() -> None:
    graph = RuntimeGovernanceGraph.from_mapping(_graph())
    resume = _record("resume-graph")
    resume["governance_fingerprint"] = "not-the-same-graph"

    with pytest.raises(ValueError, match="runtime_governance_fingerprint_drift:resume"):
        validate_runtime_governance_graph_chain(graph, resume_record=resume)


def test_continuation_cannot_create_second_graph() -> None:
    continuation = _record("continuation-graph")
    continuation["continuation_graph"] = {"source_goal_id": "goal-child"}

    with pytest.raises(ValueError, match="runtime_governance_graph_drift:continuation:source_goal_id"):
        validate_runtime_governance_graph_chain(_graph(), continuation_record=continuation)


def test_replan_cannot_create_second_graph() -> None:
    replan = _record("replan-graph")
    replan["replan_graph"] = {"goal_lineage_id": "lineage-replan-drift"}

    with pytest.raises(ValueError, match="runtime_governance_graph_drift:replan:goal_lineage_id"):
        validate_runtime_governance_graph_chain(_graph(), replan_record=replan)


def test_parallel_governance_source_is_rejected() -> None:
    parallel = _record("parallel-graph")
    parallel["metadata"] = {"parallel_governance_graph": True}

    with pytest.raises(ValueError, match="runtime_governance_bypass_marker:mutation:parallel_governance_graph"):
        validate_runtime_governance_graph_chain(_graph(), mutation_record=parallel)


def test_full_runtime_governance_graph_chain_is_closed() -> None:
    result = validate_runtime_governance_graph_chain(
        _graph(),
        authority_record=_record("authority-graph"),
        capability_record=_record("capability-graph"),
        identity_record=_record("identity-graph"),
        ownership_record=_record("ownership-graph"),
        mutation_record=_record("mutation-graph"),
        evidence_record=_record("evidence-graph"),
        persistence_record=_record("persistence-graph"),
        resume_record=_record("resume-graph"),
        continuation_record=_record("continuation-graph"),
        replan_record=_record("replan-graph"),
    )

    assert result["valid"] is True
    assert result["governance_graph"] == _graph()
    assert set(result["checked_records"]) == {
        "authority",
        "capability",
        "identity",
        "ownership",
        "mutation",
        "evidence",
        "persistence",
        "resume",
        "continuation",
        "replan",
    }
