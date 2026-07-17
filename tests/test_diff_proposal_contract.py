from __future__ import annotations

from pathlib import Path

from core.engineering.diff_proposal import (

    build_diff_proposal,
    validate_diff_proposal_contract,
)
from core.engineering.repo_scan import build_impacted_file_plan
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def test_diff_proposal_is_read_only_and_requires_approval(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "core" / "runtime" / "alpha_engine.py", "print('alpha')\n")
    _write(tmp_path / "tests" / "test_alpha_engine.py", "def test_alpha(): pass\n")

    plan = build_impacted_file_plan(
        "Update alpha engine tests",
        repo_root=tmp_path,
    )

    proposal = build_diff_proposal(plan)
    payload = proposal.to_dict()

    assert proposal.proposal_id.startswith("diff-proposal-")
    assert payload["plan_id"] == plan.plan_id
    assert payload["metadata"]["read_only"] is True
    assert payload["metadata"]["mutation_allowed"] is False
    assert payload["metadata"]["execution_allowed"] is False
    assert payload["metadata"]["approval_required"] is True
    assert payload["metadata"]["governed_runtime_required"] is True


def test_diff_proposal_contains_classified_files_and_operations(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "docs" / "guide.md", "# Guide\n")
    _write(tmp_path / "core" / "runtime" / "planner.py", "class Planner: pass\n")

    plan = build_impacted_file_plan(
        "Update planner docs",
        repo_root=tmp_path,
    )

    proposal = build_diff_proposal(plan)
    payload = proposal.to_dict()

    assert payload["files"]

    for item in payload["files"]:
        assert item["classification"] in {
            "source",
            "test",
            "docs",
            "config",
            "other",
        }
        assert item["proposed_operation"]
        assert item["proposal_reason"]


def test_diff_proposal_contract_rejects_governed_looking_success_shape(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "core" / "runtime" / "executor.py", "print('x')\n")

    plan = build_impacted_file_plan(
        "Inspect executor planning",
        repo_root=tmp_path,
    )

    proposal = build_diff_proposal(plan).to_dict()

    assert validate_diff_proposal_contract(proposal) is True

    proposal["runtime_evidence_id"] = "runtime-evidence-123"

    assert validate_diff_proposal_contract(proposal) is False


def test_diff_proposal_is_not_execution_success(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "docs" / "loop.md", "# Loop\n")

    plan = build_impacted_file_plan(
        "Review loop docs",
        repo_root=tmp_path,
    )

    proposal = build_diff_proposal(plan).to_dict()

    assert "verification_result" not in proposal
    assert "execution_summary" not in proposal
    assert proposal["metadata"]["patch_apply_allowed"] is False
    assert proposal["metadata"]["execution_allowed"] is False


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
