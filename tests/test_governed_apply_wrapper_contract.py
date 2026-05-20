from __future__ import annotations

import pytest

from core.engineering.governed_apply_wrapper import (
    build_governed_apply_request,
    validate_governed_apply_request_contract,
)


def test_governed_apply_request_wraps_ready_mutation_without_applying() -> None:
    request = build_governed_apply_request(
        _readiness(),
        approved_by="user-review",
    )
    payload = request.to_dict()

    assert payload["apply_request_id"].startswith("governed-apply-request-")
    assert payload["readiness_id"] == "mutation-readiness-123"
    assert payload["repair_proposal_id"] == "governed-repair-proposal-123"
    assert payload["verification_route_id"] == "verification-route-123"
    assert payload["approved_by"] == "user-review"
    assert payload["dry_run_required"] is True
    assert payload["sandbox_required"] is True
    assert payload["rollback_checkpoint_required"] is True
    assert payload["verification_required"] is True
    assert payload["metadata"]["request_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["runtime_authority_granted"] is False
    assert payload["metadata"]["canonical_runtime_success"] is False
    assert payload["metadata"]["requires_governed_runtime_execution"] is True
    assert payload["metadata"]["requires_sandbox_apply"] is True
    assert validate_governed_apply_request_contract(payload) is True


def test_governed_apply_request_rejects_not_ready_readiness() -> None:
    readiness = _readiness()
    readiness["ready_for_governed_mutation"] = False
    readiness["blockers"] = ["approval_incomplete"]

    with pytest.raises(ValueError, match="readiness_not_ready_for_governed_mutation"):
        build_governed_apply_request(readiness, approved_by="user-review")


def test_governed_apply_request_requires_approver() -> None:
    with pytest.raises(ValueError, match="approved_by_required"):
        build_governed_apply_request(_readiness(), approved_by="")


def test_governed_apply_request_rejects_readiness_that_grants_authority() -> None:
    readiness = _readiness()
    readiness["metadata"]["execution_allowed"] = True

    with pytest.raises(ValueError, match="readiness_must_not_grant_execution_authority"):
        build_governed_apply_request(readiness, approved_by="user-review")


def test_governed_apply_request_contract_rejects_runtime_success_shape() -> None:
    payload = build_governed_apply_request(
        _readiness(),
        approved_by="user-review",
    ).to_dict()

    assert validate_governed_apply_request_contract(payload) is True

    payload["runtime_evidence_id"] = "runtime-evidence-123"

    assert validate_governed_apply_request_contract(payload) is False


def test_governed_apply_request_contract_rejects_written_files_claim() -> None:
    payload = build_governed_apply_request(
        _readiness(),
        approved_by="user-review",
    ).to_dict()

    payload["files_written"] = ["core/runtime/executor.py"]

    assert validate_governed_apply_request_contract(payload) is False


def _readiness() -> dict[str, object]:
    return {
        "readiness_id": "mutation-readiness-123",
        "repair_proposal_id": "governed-repair-proposal-123",
        "recommendation_id": "retry-repair-recommendation-123",
        "verification_route_id": "verification-route-123",
        "ready_for_governed_mutation": True,
        "approval_complete": True,
        "rollback_available": True,
        "verification_profile_available": True,
        "mutation_scope_locked": True,
        "blockers": [],
        "metadata": {
            "control_plane_only": True,
            "read_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "runtime_authority_granted": False,
            "canonical_runtime_success": False,
            "governed_mutation_pipeline_required": True,
            "requires_runtime_evidence_after_execution": True,
            "requires_audit_lineage_after_execution": True,
            "source_repair_proposal_metadata": {
                "allowed_mutation_targets": ["core/runtime/executor.py"],
            },
        },
    }
