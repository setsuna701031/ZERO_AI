from __future__ import annotations

import pytest

from core.runtime.runtime_evidence_closure import (
    RuntimeEvidenceIdentityGraph,
    seal_runtime_evidence,
    validate_runtime_evidence_chain,
)


def _identity() -> dict[str, str]:
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
        "capability_id": "capability-1",
    }


def _evidence(evidence_id: str = "evidence-1") -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "artifact_type": "runtime_evidence",
        "runtime_evidence": {
            "stdout": "",
            "stderr": "",
        },
    }


def test_evidence_source_closure_seals_existing_identity_graph() -> None:
    graph = RuntimeEvidenceIdentityGraph.from_mapping(_identity())

    sealed = seal_runtime_evidence(_evidence(), identity_graph=graph)

    assert sealed.evidence_id == "evidence-1"
    assert sealed.identity_graph.to_dict() == _identity()
    assert sealed.to_dict()["identity_fingerprint"] == graph.fingerprint
    assert sealed.to_dict()["payload"]["identity_graph"] == _identity()


def test_evidence_identity_closure_rejects_drift() -> None:
    payload = _evidence()
    payload["execution_id"] = "execution-drift"

    with pytest.raises(ValueError, match="runtime_evidence_identity_drift:execution_id"):
        seal_runtime_evidence(payload, identity_graph=_identity())


def test_evidence_persistence_closure_validates_same_fingerprint() -> None:
    graph = RuntimeEvidenceIdentityGraph.from_mapping(_identity())
    persistence = {
        "identity_graph": _identity(),
        "identity_fingerprint": graph.fingerprint,
        "evidence_ids": ["evidence-1", "evidence-2"],
    }

    result = validate_runtime_evidence_chain(
        graph,
        [_evidence("evidence-1"), _evidence("evidence-2")],
        persistence_record=persistence,
    )

    assert result["valid"] is True
    assert result["identity_fingerprint"] == graph.fingerprint
    assert result["evidence_ids"] == ["evidence-1", "evidence-2"]


def test_evidence_resume_closure_rejects_fingerprint_drift() -> None:
    resume = {
        "identity_graph": _identity(),
        "identity_fingerprint": "not-the-original-fingerprint",
        "evidence_ids": ["evidence-1"],
    }

    with pytest.raises(ValueError, match="runtime_evidence_resume_fingerprint_drift"):
        validate_runtime_evidence_chain(
            _identity(),
            [_evidence("evidence-1")],
            resume_record=resume,
        )


def test_decision_evidence_closure_allows_nested_identity_graph_only_when_matching() -> None:
    payload = _evidence("decision-evidence-1")
    payload["metadata"] = {"identity_graph": _identity()}

    sealed = seal_runtime_evidence(payload, identity_graph=_identity())

    assert sealed.evidence_id == "decision-evidence-1"
    assert sealed.identity_graph.execution_id == "execution-1"


def test_no_evidence_reissue_inside_chain() -> None:
    with pytest.raises(ValueError, match="runtime_evidence_id_reissue"):
        validate_runtime_evidence_chain(
            _identity(),
            [_evidence("same-evidence"), _evidence("same-evidence")],
        )


def test_no_fallback_identity_source() -> None:
    identity = _identity()
    identity["runtime_session_id"] = "legacy"

    with pytest.raises(ValueError, match="runtime_evidence_forbidden_identity:runtime_session_id"):
        RuntimeEvidenceIdentityGraph.from_mapping(identity)


def test_no_parallel_evidence_system_can_override_capability_identity() -> None:
    payload = _evidence("evidence-override")
    payload["runtime_capability_graph"] = {"capability_id": "parallel-capability"}

    with pytest.raises(ValueError, match="runtime_evidence_identity_drift:capability_id"):
        seal_runtime_evidence(payload, identity_graph=_identity())
