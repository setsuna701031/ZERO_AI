from __future__ import annotations

from pathlib import Path

from core.engineering.approval_envelope import (

    build_approval_envelope,
    build_governed_apply_eligibility,
    build_verification_profile,
    validate_approval_envelope_contract,
    validate_verification_profile_contract,
)
from core.engineering.diff_proposal import build_diff_proposal
from core.engineering.repo_scan import build_impacted_file_plan
import pytest

pytestmark = [pytest.mark.contract]



def test_approval_envelope_is_read_only_and_not_execution_authority(
    tmp_path: Path,
) -> None:
    proposal = _proposal_for_task(tmp_path, "Update alpha runtime tests")

    profile = build_verification_profile(proposal)
    approval = build_approval_envelope(
        proposal,
        reviewer="human",
        review_state="pending",
        verification_profile=profile,
    )
    payload = approval.to_dict()

    assert payload["approval_id"].startswith("approval-envelope-")
    assert payload["proposal_id"] == proposal.proposal_id
    assert payload["verification_profile_id"] == profile.verification_profile_id
    assert payload["review_state"] == "pending"
    assert payload["metadata"]["read_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["patch_apply_allowed"] is False
    assert payload["metadata"]["governed_apply_required"] is True
    assert validate_approval_envelope_contract(payload) is True


def test_verification_profile_requires_commands_rollback_and_recovery(
    tmp_path: Path,
) -> None:
    proposal = _proposal_for_task(tmp_path, "Update alpha runtime tests")

    profile = build_verification_profile(proposal, retry_budget=2)
    payload = profile.to_dict()

    assert payload["verification_profile_id"].startswith("verification-profile-")
    assert payload["proposal_id"] == proposal.proposal_id
    assert payload["plan_id"] == proposal.plan_id
    assert payload["retry_budget"] == 2
    assert payload["rollback_required"] is True
    assert payload["recovery_required"] is True
    assert payload["commands"]
    assert payload["metadata"]["verification_execution_allowed"] is False
    assert payload["metadata"]["mutation_allowed"] is False
    assert validate_verification_profile_contract(payload) is True


def test_governed_apply_eligibility_blocks_pending_approval(
    tmp_path: Path,
) -> None:
    proposal = _proposal_for_task(tmp_path, "Update alpha runtime tests")
    profile = build_verification_profile(proposal)
    approval = build_approval_envelope(
        proposal,
        review_state="pending",
        verification_profile=profile,
    )

    eligibility = build_governed_apply_eligibility(
        proposal=proposal,
        approval=approval,
        verification_profile=profile,
    )
    payload = eligibility.to_dict()

    assert payload["status"] == "blocked"
    assert "approval is not approved" in payload["reasons"]
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["eligibility_only"] is True


def test_governed_apply_eligibility_is_not_patch_apply_execution(
    tmp_path: Path,
) -> None:
    proposal = _proposal_for_task(tmp_path, "Update alpha runtime tests")
    profile = build_verification_profile(proposal)
    approval = build_approval_envelope(
        proposal,
        review_state="approved",
        verification_profile=profile,
    )

    eligibility = build_governed_apply_eligibility(
        proposal=proposal,
        approval=approval,
        verification_profile=profile,
    )
    payload = eligibility.to_dict()

    assert payload["status"] == "eligible_for_governed_apply"
    assert payload["reasons"] == []
    assert payload["metadata"]["patch_apply_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["requires_governed_runtime"] is True
    assert "runtime_evidence_id" not in payload
    assert "governed_mutation_lineage" not in payload
    assert "verification_result" not in payload


def test_approval_and_verification_contracts_reject_success_like_shapes(
    tmp_path: Path,
) -> None:
    proposal = _proposal_for_task(tmp_path, "Update alpha runtime tests")
    profile = build_verification_profile(proposal)
    approval = build_approval_envelope(
        proposal,
        review_state="approved",
        verification_profile=profile,
    )

    approval_payload = approval.to_dict()
    approval_payload["runtime_evidence_id"] = "runtime-evidence-123"

    assert validate_approval_envelope_contract(approval_payload) is False

    profile_payload = profile.to_dict()
    profile_payload["rollback_required"] = False

    assert validate_verification_profile_contract(profile_payload) is False


def _proposal_for_task(tmp_path: Path, task: str):
    _write(tmp_path / "core" / "runtime" / "alpha_engine.py", "print('alpha')\n")
    _write(tmp_path / "tests" / "test_alpha_engine.py", "def test_alpha(): pass\n")
    plan = build_impacted_file_plan(task, repo_root=tmp_path)
    return build_diff_proposal(plan)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
