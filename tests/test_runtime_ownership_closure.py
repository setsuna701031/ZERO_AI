from __future__ import annotations

import pytest

from core.runtime.runtime_ownership_closure import (
    RuntimeOwnershipGraph,
    seal_runtime_ownership,
    validate_runtime_ownership_chain,
)


def _owners() -> dict[str, str]:
    return {
        "goal_owner": "goal_loop",
        "session_owner": "session_coordinator",
        "execution_owner": "runtime_dispatcher",
        "capability_owner": "runtime_execution_authority",
        "evidence_owner": "runtime_evidence_authority",
        "persistence_owner": "runtime_persistence_service",
    }


def _identity() -> dict[str, str]:
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
        "evidence_id": "evidence-1",
        "persistence_id": "persist-1",
    }


def _record(closure_id: str = "ownership-1") -> dict[str, object]:
    return {
        "ownership_closure_id": closure_id,
        "payload": {"state": "sealed"},
    }


def test_ownership_closure_seals_canonical_owner_graph() -> None:
    graph = RuntimeOwnershipGraph.from_mapping(_owners())

    sealed = seal_runtime_ownership(_record(), ownership_graph=graph, identity_binding=_identity())

    assert sealed.closure_id == "ownership-1"
    assert sealed.ownership_graph.to_dict() == _owners()
    assert sealed.identity_binding == _identity()
    assert sealed.to_dict()["payload"]["ownership_graph"] == _owners()


def test_no_ownership_drift() -> None:
    payload = _record()
    payload["execution_owner"] = "task_runner"

    with pytest.raises(ValueError, match="runtime_ownership_graph_drift:execution_owner"):
        seal_runtime_ownership(payload, ownership_graph=_owners(), identity_binding=_identity())


def test_no_ownership_override_by_resume() -> None:
    resume = _record("resume-owner")
    resume["resume_graph"] = {"persistence_owner": "resume_runtime"}

    with pytest.raises(ValueError, match="runtime_ownership_graph_drift:persistence_owner"):
        validate_runtime_ownership_chain(
            _owners(),
            identity_binding=_identity(),
            resume_record=resume,
        )


def test_no_ownership_reassignment_by_continuation() -> None:
    continuation = _record("continuation-owner")
    continuation["continuation_graph"] = {"goal_owner": "continuation_runtime"}

    with pytest.raises(ValueError, match="runtime_ownership_graph_drift:goal_owner"):
        validate_runtime_ownership_chain(
            _owners(),
            identity_binding=_identity(),
            continuation_record=continuation,
        )


def test_no_replan_ownership_mutation() -> None:
    replan = _record("replan-owner")
    replan["replan_graph"] = {"execution_owner": "replan_runtime"}

    with pytest.raises(ValueError, match="runtime_ownership_graph_drift:execution_owner"):
        validate_runtime_ownership_chain(
            _owners(),
            identity_binding=_identity(),
            replan_record=replan,
        )


def test_no_parallel_ownership_source_from_fingerprint_drift() -> None:
    graph = RuntimeOwnershipGraph.from_mapping(_owners())
    execution = _record("execution-owner")
    execution["owner_fingerprint"] = "different-owner-fingerprint"

    with pytest.raises(ValueError, match="runtime_ownership_fingerprint_drift:execution"):
        validate_runtime_ownership_chain(
            graph,
            identity_binding=_identity(),
            execution_record=execution,
        )


def test_no_identity_mixing_under_ownership() -> None:
    evidence = _record("evidence-owner")
    evidence["execution_id"] = "execution-drift"

    with pytest.raises(ValueError, match="runtime_ownership_identity_drift:evidence:execution_id"):
        validate_runtime_ownership_chain(
            _owners(),
            identity_binding=_identity(),
            evidence_record=evidence,
        )


def test_no_fallback_owner_source() -> None:
    owners = _owners()
    owners["capability_owner"] = "legacy"

    with pytest.raises(ValueError, match="runtime_ownership_forbidden_owner:capability_owner"):
        RuntimeOwnershipGraph.from_mapping(owners)


def test_full_chain_preserves_single_owner_graph() -> None:
    graph = RuntimeOwnershipGraph.from_mapping(_owners())
    result = validate_runtime_ownership_chain(
        graph,
        identity_binding=_identity(),
        goal_record=_record("goal-owner"),
        session_record=_record("session-owner"),
        execution_record=_record("execution-owner"),
        capability_record=_record("capability-owner"),
        evidence_record=_record("evidence-owner"),
        persistence_record=_record("persistence-owner"),
        resume_record=_record("resume-owner"),
        continuation_record=_record("continuation-owner"),
        replan_record=_record("replan-owner"),
    )

    assert result["valid"] is True
    assert result["ownership_graph"] == _owners()
    assert result["identity_binding"] == _identity()
    assert set(result["checked_records"]) == {
        "goal",
        "session",
        "execution",
        "capability",
        "evidence",
        "persistence",
        "resume",
        "continuation",
        "replan",
    }
