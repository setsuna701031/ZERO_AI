from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.runtime.runtime_authority_seal import _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN
from core.runtime.runtime_capability_tokens import CAP_MUTATION, ZONE_MUTATION, RuntimeCapabilityTokenManager
from core.runtime.runtime_evidence_authority import RuntimeEvidenceAuthority
from core.runtime.runtime_execution_authority import (
    CAPABILITY_PROPAGATION_STAGES,
    RuntimeCapabilityPropagationError,
    assert_runtime_capability_consistency,
    capability_from_authority_decision,
    propagate_runtime_capability,
)
from core.runtime.runtime_execution_authority_policy import evaluate_execution_authority
from core.runtime.runtime_persistence_service import RuntimePersistenceService


ROOT = Path(__file__).resolve().parents[1]


class _FileService:
    def write_text(self, **kwargs):
        return {"ok": True, "metadata": kwargs.get("metadata", {})}


def _capability():
    decision = evaluate_execution_authority(
        source="runtime_dispatcher",
        action_type="issue_capability",
        metadata={"side_effect": False, "task_id": "task:1"},
    )
    return decision, capability_from_authority_decision(
        decision,
        issuer="RuntimeExecutionAuthorityPolicy",
        resource="runtime_task",
        action="execute",
        scope={"task_id": "task:1", "package_id": "package:1", "execution_id": "execution:1"},
        lineage={"task_id": "task:1", "session_id": "session:1", "execution_id": "execution:1"},
    )


def test_single_capability_source_propagates_one_identity_through_all_stages() -> None:
    _, capability = _capability()
    payload = {}
    seen = set()
    for stage in CAPABILITY_PROPAGATION_STAGES:
        payload = propagate_runtime_capability(payload, capability, stage=stage)
        seen.add(payload["runtime_capability_id"])
        assert payload["runtime_capability_provenance"] is capability
    assert seen == {capability.capability_id}


def test_no_capability_override_or_upgrade() -> None:
    decision, capability = _capability()
    with pytest.raises(RuntimeCapabilityPropagationError, match="override_forbidden"):
        propagate_runtime_capability(
            {"runtime_capability_id": "runtime-capability:other"},
            capability,
            stage="runtime",
        )
    with pytest.raises(RuntimeCapabilityPropagationError, match="wildcard"):
        capability_from_authority_decision(
            decision,
            issuer="RuntimeExecutionAuthorityPolicy",
            resource="runtime_task",
            action="execute",
            scope={"task_id": "*"},
            lineage={"task_id": "task:1"},
        )


def test_no_capability_reissue_for_one_authority_decision() -> None:
    decision, _ = _capability()
    manager = RuntimeCapabilityTokenManager()
    token = manager.issue_from_authority_decision(
        decision,
        capability=CAP_MUTATION,
        zone=ZONE_MUTATION,
        scope={"path": "workspace/a.py", "execution_id": "execution:1"},
        lineage={"task_id": "task:1", "execution_id": "execution:1"},
    )
    assert token.authority_decision_id == decision.decision_id
    with pytest.raises(PermissionError, match="reissue_forbidden"):
        manager.issue_from_authority_decision(
            decision,
            capability=CAP_MUTATION,
            zone=ZONE_MUTATION,
            scope={"path": "workspace/a.py", "execution_id": "execution:1"},
            lineage={"task_id": "task:1", "execution_id": "execution:1"},
        )


def test_capability_evidence_and_persistence_consistency(tmp_path: Path) -> None:
    _, capability = _capability()
    authority = RuntimeEvidenceAuthority(
        evidence_id="evidence:1",
        issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
        capability_provenance=capability,
    )
    with pytest.raises(PermissionError, match="override_forbidden"):
        authority.update(
            issuer_token=_GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
            runtime_capability_id="runtime-capability:other",
        )
    evidence = authority.to_dict()
    persistence = RuntimePersistenceService(
        workspace_root=tmp_path,
        source="test",
        file_service=_FileService(),
    )
    persisted = persistence.write_json(
        tmp_path / "evidence.json",
        evidence,
        metadata=propagate_runtime_capability({}, capability, stage="mutation"),
    )
    assert assert_runtime_capability_consistency(evidence, persisted) == capability.capability_id
    assert persisted["runtime_capability_stage"] == "persistence"


def test_mutation_gateway_does_not_issue_or_override_capability() -> None:
    path = ROOT / "core/runtime/runtime_mutation_gateway.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    calls = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert "issue_runtime_mutation_capability" not in calls
    assert "propagate_runtime_capability" in calls


def test_required_non_mainline_findings_are_reported() -> None:
    doc = (ROOT / "docs/architecture/runtime_capability_propagation_closure.md").read_text(encoding="utf-8")
    for finding in (
        "second capability system",
        "wildcard capability",
        "capability fallback",
        "authority/capability mixed responsibility",
        "capability/evidence drift",
        "capability/persistence drift",
    ):
        assert finding in doc
    assert "Report, do not silently skip" in doc
