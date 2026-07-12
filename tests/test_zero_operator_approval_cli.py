from __future__ import annotations

import copy
import json
from pathlib import Path

from cli.zero_operator_approval import run_operator_approval_cli
from core.runtime.runtime_operator_approval_gate import RuntimeOperatorApprovalGate


NOW = "2026-07-10T12:00:00+00:00"


def _proposal(path: Path) -> dict:
    payload = {
        "schema": "zero.runtime.change_proposal_engine.v1",
        "proposal_status": "proposal_created",
        "proposal_id": "proposal-one",
        "requires_operator_approval": True,
        "mutation_allowed": False,
        "autonomous_apply_allowed": False,
        "patch_generation_allowed": False,
        "proposal": {
            "target_files": ["workspace/a.txt"],
            "recommended_actions": ["review_target_file"],
            "validation_requirements": ["run_focused_validation"],
            "rollback_requirements": [],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _gate() -> RuntimeOperatorApprovalGate:
    return RuntimeOperatorApprovalGate(clock=lambda: NOW)


def test_approve_scope_and_result_file_without_source_mutation(tmp_path: Path) -> None:
    proposal_path = tmp_path / "proposal.json"
    source = _proposal(proposal_path)
    before = copy.deepcopy(source)
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(json.dumps({
        "target_files": ["workspace/a.txt"],
        "recommended_actions": [], "validation_requirements": [],
        "rollback_requirements": [],
    }), encoding="utf-8")
    result_path = tmp_path / "nested" / "approval.json"
    result, code = run_operator_approval_cli(
        "approve", proposal_path, operator_id="heero", reason="reviewed",
        scope_file=scope_path, result_path=result_path, gate=_gate(),
    )

    assert code == 0
    assert result["approval_status"] == "approved"
    assert result["execution_authority_granted"] is False
    assert json.loads(result_path.read_text(encoding="utf-8")) == result
    assert json.loads(proposal_path.read_text(encoding="utf-8")) == before


def test_reject_revoke_and_status_commands(tmp_path: Path) -> None:
    proposal_path = tmp_path / "proposal.json"
    _proposal(proposal_path)
    rejected, reject_code = run_operator_approval_cli(
        "reject", proposal_path, operator_id="heero", reason="unsafe",
        result_path=tmp_path / "rejected.json", gate=_gate(),
    )
    approved, _ = run_operator_approval_cli(
        "approve", proposal_path, operator_id="heero",
        result_path=tmp_path / "approved.json", gate=_gate(),
    )
    approval_path = tmp_path / "approval-source.json"
    approval_path.write_text(json.dumps(approved), encoding="utf-8")
    revoked, revoke_code = run_operator_approval_cli(
        "revoke", approval_path, operator_id="heero", reason="withdraw",
        result_path=tmp_path / "revoked.json", gate=_gate(),
    )
    status_path = tmp_path / "status-source.json"
    status_path.write_text(json.dumps(revoked), encoding="utf-8")
    status, status_code = run_operator_approval_cli(
        "status", status_path, result_path=tmp_path / "status.json", gate=_gate()
    )

    assert reject_code == revoke_code == status_code == 0
    assert rejected["approval_status"] == "rejected"
    assert revoked["approval_status"] == "revoked"
    assert status["approval_status"] == "revoked"


def test_input_errors_are_exit_two(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    proposal = tmp_path / "proposal.json"
    _proposal(proposal)
    for index, args in enumerate([
        ("approve", tmp_path / "missing.json", "heero", ""),
        ("approve", invalid, "heero", ""),
        ("approve", proposal, "", ""),
        ("reject", proposal, "heero", ""),
    ]):
        result, code = run_operator_approval_cli(
            args[0], args[1], operator_id=args[2], reason=args[3],
            result_path=tmp_path / f"error-{index}.json",
        )
        assert code == 2
        assert result["ok"] is False


def test_business_invalid_scope_is_exit_one(tmp_path: Path) -> None:
    proposal = tmp_path / "proposal.json"
    _proposal(proposal)
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps({"target_files": ["workspace/new.txt"]}), encoding="utf-8")
    result, code = run_operator_approval_cli(
        "approve", proposal, operator_id="heero", scope_file=scope,
        result_path=tmp_path / "result.json", gate=_gate(),
    )
    assert code == 1
    assert result["approval_status"] == "invalid_scope"
    assert result["mutation_allowed"] is False
