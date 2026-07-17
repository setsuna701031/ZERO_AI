from __future__ import annotations

import pytest

from core.runtime.runtime_mutation_closure import (
    RuntimeMutationGraph,
    seal_runtime_mutation,
    validate_runtime_mutation_chain,
)


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


def _owners() -> dict[str, str]:
    return {
        "goal_owner": "goal_loop",
        "session_owner": "session_coordinator",
        "execution_owner": "runtime_dispatcher",
        "capability_owner": "runtime_execution_authority",
        "evidence_owner": "runtime_evidence_authority",
        "persistence_owner": "runtime_persistence_service",
    }


def _fingerprints() -> tuple[str, str]:
    import hashlib
    import json

    def fp(value: dict[str, str]) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    return fp(_identity()), fp(_owners())


def _mutation_graph() -> dict[str, str]:
    identity_fp, owner_fp = _fingerprints()
    return {
        "mutation_request_id": "mutation-request-1",
        "mutation_id": "mutation-1",
        "authority_decision_id": "authority-decision-1",
        "capability_id": "capability-1",
        "execution_id": "execution-1",
        "identity_fingerprint": identity_fp,
        "ownership_fingerprint": owner_fp,
        "evidence_id": "evidence-1",
        "persistence_id": "persist-1",
    }


def _record(closure_id: str = "mutation-closure-1") -> dict[str, object]:
    return {"mutation_closure_id": closure_id, "payload": {"state": "sealed"}}


def test_mutation_closure_seals_canonical_mutation_graph() -> None:
    graph = RuntimeMutationGraph.from_mapping(_mutation_graph())

    sealed = seal_runtime_mutation(
        _record(),
        mutation_graph=graph,
        identity_binding=_identity(),
        ownership_graph=_owners(),
    )

    assert sealed.closure_id == "mutation-closure-1"
    assert sealed.mutation_graph.to_dict() == _mutation_graph()
    assert sealed.identity_binding == _identity()
    assert sealed.ownership_graph == _owners()
    assert sealed.to_dict()["payload"]["mutation_graph"] == _mutation_graph()


def test_no_mutation_without_authority() -> None:
    graph = _mutation_graph()
    graph["authority_decision_id"] = ""

    with pytest.raises(ValueError, match="runtime_mutation_graph_missing:authority_decision_id"):
        RuntimeMutationGraph.from_mapping(graph)


def test_no_mutation_without_capability() -> None:
    graph = _mutation_graph()
    graph["capability_id"] = "fallback"

    with pytest.raises(ValueError, match="runtime_mutation_forbidden_value:capability_id"):
        RuntimeMutationGraph.from_mapping(graph)


def test_no_mutation_without_identity() -> None:
    graph = _mutation_graph()
    graph["identity_fingerprint"] = ""

    with pytest.raises(ValueError, match="runtime_mutation_graph_missing:identity_fingerprint"):
        RuntimeMutationGraph.from_mapping(graph)


def test_no_mutation_without_ownership() -> None:
    graph = _mutation_graph()
    graph["ownership_fingerprint"] = "unknown"

    with pytest.raises(ValueError, match="runtime_mutation_forbidden_value:ownership_fingerprint"):
        RuntimeMutationGraph.from_mapping(graph)


def test_no_mutation_graph_drift() -> None:
    payload = _record()
    payload["mutation_id"] = "mutation-drift"

    with pytest.raises(ValueError, match="runtime_mutation_graph_drift:mutation_id"):
        seal_runtime_mutation(
            payload,
            mutation_graph=_mutation_graph(),
            identity_binding=_identity(),
            ownership_graph=_owners(),
        )


def test_no_mutation_evidence_drift() -> None:
    evidence = _record("evidence-mutation")
    evidence["evidence_id"] = "evidence-drift"

    with pytest.raises(ValueError, match="runtime_mutation_graph_drift:evidence_id"):
        validate_runtime_mutation_chain(
            _mutation_graph(),
            identity_binding=_identity(),
            ownership_graph=_owners(),
            evidence_record=evidence,
        )


def test_no_mutation_persistence_drift() -> None:
    persistence = _record("persistence-mutation")
    persistence["persistence_id"] = "persist-drift"

    with pytest.raises(ValueError, match="runtime_mutation_graph_drift:persistence_id"):
        validate_runtime_mutation_chain(
            _mutation_graph(),
            identity_binding=_identity(),
            ownership_graph=_owners(),
            persistence_record=persistence,
        )


def test_no_parallel_direct_mutation_path() -> None:
    mutation = _record("direct-mutation")
    mutation["mutation_graph"] = {"direct_mutation": True}

    with pytest.raises(ValueError, match="runtime_mutation_bypass_marker:mutation:direct_mutation"):
        validate_runtime_mutation_chain(
            _mutation_graph(),
            identity_binding=_identity(),
            ownership_graph=_owners(),
            mutation_record=mutation,
        )


def test_full_mutation_chain_preserves_single_canonical_graph() -> None:
    result = validate_runtime_mutation_chain(
        _mutation_graph(),
        identity_binding=_identity(),
        ownership_graph=_owners(),
        request_record=_record("request-mutation"),
        authority_record=_record("authority-mutation"),
        capability_record=_record("capability-mutation"),
        identity_record=_record("identity-mutation"),
        ownership_record=_record("ownership-mutation"),
        mutation_record=_record("runtime-mutation"),
        evidence_record=_record("evidence-mutation"),
        persistence_record=_record("persistence-mutation"),
        resume_record=_record("resume-mutation"),
    )

    assert result["valid"] is True
    assert result["mutation_graph"] == _mutation_graph()
    assert set(result["checked_records"]) == {
        "request",
        "authority",
        "capability",
        "identity",
        "ownership",
        "mutation",
        "evidence",
        "persistence",
        "resume",
    }
