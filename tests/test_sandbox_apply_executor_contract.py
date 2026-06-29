from __future__ import annotations

import pytest

from core.engineering.sandbox_apply_executor import (

    build_sandbox_apply_dry_run,
    validate_sandbox_apply_dry_run_contract,
)
pytestmark = [pytest.mark.contract]



def test_sandbox_apply_dry_run_builds_without_real_mutation() -> None:
    result = build_sandbox_apply_dry_run(
        _apply_request(),
        planned_operations=["virtual_patch_preview"],
    )
    payload = result.to_dict()

    assert payload["dry_run_id"].startswith("sandbox-apply-dry-run-")
    assert payload["sandbox_status"] == "dry_run_ready"
    assert payload["blockers"] == []
    assert payload["target_files"] == ["core/runtime/executor.py"]
    assert payload["planned_operations"] == ["virtual_patch_preview"]
    assert payload["metadata"]["dry_run"] is True
    assert payload["metadata"]["sandbox_only"] is True
    assert payload["metadata"]["no_real_write"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["canonical_runtime_success"] is False
    assert payload["rollback_checkpoint_draft"]["real_checkpoint_created"] is False
    assert payload["verification_draft"]["real_verification_executed"] is False
    assert payload["evidence_draft"]["real_runtime_evidence_created"] is False
    assert validate_sandbox_apply_dry_run_contract(payload) is True


def test_sandbox_apply_dry_run_blocks_missing_operations() -> None:
    payload = build_sandbox_apply_dry_run(
        _apply_request(),
        planned_operations=[],
    ).to_dict()

    assert payload["sandbox_status"] == "blocked"
    assert "planned_operations_required" in payload["blockers"]
    assert validate_sandbox_apply_dry_run_contract(payload) is True


def test_sandbox_apply_dry_run_rejects_apply_request_without_sandbox_requirement() -> None:
    request = _apply_request()
    request["metadata"]["requires_sandbox_apply"] = False

    with pytest.raises(ValueError, match="apply_request_must_require_sandbox_apply"):
        build_sandbox_apply_dry_run(
            request,
            planned_operations=["virtual_patch_preview"],
        )


def test_sandbox_apply_dry_run_rejects_apply_request_granting_execution() -> None:
    request = _apply_request()
    request["metadata"]["execution_allowed"] = True

    with pytest.raises(ValueError, match="apply_request_must_not_grant_execution_authority"):
        build_sandbox_apply_dry_run(
            request,
            planned_operations=["virtual_patch_preview"],
        )


def test_sandbox_apply_contract_rejects_runtime_success_shape() -> None:
    payload = build_sandbox_apply_dry_run(
        _apply_request(),
        planned_operations=["virtual_patch_preview"],
    ).to_dict()

    assert validate_sandbox_apply_dry_run_contract(payload) is True

    payload["runtime_evidence_id"] = "runtime-evidence-123"

    assert validate_sandbox_apply_dry_run_contract(payload) is False


def test_sandbox_apply_contract_rejects_real_write_claim() -> None:
    payload = build_sandbox_apply_dry_run(
        _apply_request(),
        planned_operations=["virtual_patch_preview"],
    ).to_dict()

    payload["files_written"] = ["core/runtime/executor.py"]

    assert validate_sandbox_apply_dry_run_contract(payload) is False


def _apply_request() -> dict[str, object]:
    return {
        "apply_request_id": "governed-apply-request-123",
        "readiness_id": "mutation-readiness-123",
        "repair_proposal_id": "governed-repair-proposal-123",
        "verification_route_id": "verification-route-123",
        "approved_by": "user-review",
        "target_files": ["core/runtime/executor.py"],
        "dry_run_required": True,
        "sandbox_required": True,
        "rollback_checkpoint_required": True,
        "verification_required": True,
        "metadata": {
            "control_plane_only": True,
            "request_only": True,
            "mutation_allowed": False,
            "execution_allowed": False,
            "patch_apply_allowed": False,
            "runtime_authority_granted": False,
            "canonical_runtime_success": False,
            "requires_governed_runtime_execution": True,
            "requires_sandbox_apply": True,
            "requires_rollback_checkpoint": True,
            "requires_verification_after_apply": True,
            "requires_runtime_evidence_after_execution": True,
            "requires_audit_lineage_after_execution": True,
        },
    }
