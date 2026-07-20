from __future__ import annotations

import json
from pathlib import Path

from core.engineering.engineering_runtime_formal_persistence import resume_formal_persistence_session
from core.engineering.engineering_runtime_orchestrator import orchestrate_engineering_runtime
from core.engineering.engineering_runtime_session_store import read_session_artifact


TARGET = "examples/zero_first_governed_engineering_trial.json"


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "examples").mkdir(parents=True)
    (root / "examples" / ".keep").write_text("", encoding="utf-8")
    return root


def _payload(mode: str = "propose", *, operator_input: dict | None = None) -> dict:
    payload = {
        "request_id": "zero-first-engineering-runtime-trial-001",
        "requested_orchestration_mode": mode,
        "workspace_id": "ZERO_AI",
        "workspace_root_fingerprint": "root-fingerprint",
        "scope_constraints": [TARGET],
        "authority_constraints": ["bounded", "no_mutation"],
        "execution_requested": False,
    }
    if operator_input is not None:
        payload["operator_input"] = operator_input
    return payload


def _run(tmp_path: Path, mode: str = "propose", *, operator_input: dict | None = None) -> tuple[dict, Path]:
    session_root = tmp_path / "sessions"
    result = orchestrate_engineering_runtime(
        _payload(mode, operator_input=operator_input),
        workspace_root=str(_repo(tmp_path)),
        session_root=str(session_root),
    )
    return result, session_root


def _formal(result: dict) -> dict:
    return result["formal_persistence"]


def test_formal_analysis_and_proposal_persist_and_pause(tmp_path: Path) -> None:
    result, session_root = _run(tmp_path, "propose")
    formal = _formal(result)
    session_id = formal["session_id"]

    assert formal["status"] == "awaiting_operator_approval"
    assert formal["current_phase"] == "awaiting_operator_approval"
    assert formal["required_operator_input"] == {
        "decision_required": True,
        "operator_identity_required": True,
        "automated_decision_allowed": False,
    }
    assert formal["executor_invoked"] is False
    assert formal["workspace_mutation_performed"] is False
    assert formal["git_mutation_performed"] is False

    analysis = read_session_artifact(session_root, session_id, "formal-analysis.json")
    proposal = read_session_artifact(session_root, session_id, "formal-proposal.json")
    index = read_session_artifact(session_root, session_id, "artifact-index.json")

    assert analysis["status"] == "closed"
    assert proposal["schema"] == "zero.engineering.proposal_review_closure.v1"
    assert proposal["status"] == "closed"
    assert [entry["logical_key"] for entry in index["entries"]] == [
        "formal_analysis",
        "formal_planning",
        "formal_proposal",
    ]


def test_valid_human_approval_prepares_and_stops_before_mutation_authorization(tmp_path: Path) -> None:
    operator_input = {
        "decision": "approved",
        "operator_id": "setsuna701031",
        "automated_decision": False,
        "approval_scope": [TARGET],
    }
    result, session_root = _run(tmp_path, "prepare", operator_input=operator_input)
    formal = _formal(result)
    session_id = formal["session_id"]

    assert formal["status"] == "awaiting_mutation_authorization"
    assert formal["current_phase"] == "awaiting_mutation_authorization"
    assert formal["executor_invoked"] is False
    assert formal["workspace_mutation_performed"] is False
    assert formal["git_mutation_performed"] is False

    approval = read_session_artifact(session_root, session_id, "formal-approval.json")
    preparation = read_session_artifact(session_root, session_id, "formal-preparation.json")
    index = read_session_artifact(session_root, session_id, "artifact-index.json")

    assert approval["status"] == "closed_approved"
    assert approval["authorization_authority_declaration"] == "not_granted"
    assert approval["execution_authority_declaration"] == "not_granted"
    assert approval["mutation_authority_declaration"] == "not_granted"
    assert preparation["status"] == "closed_ready"
    assert preparation["next_boundary_declaration"]["state"] == "ready_for_governed_execution"
    assert index["entries"][-1]["logical_key"] == "formal_preparation"


def test_invalid_human_approval_inputs_fail_closed(tmp_path: Path) -> None:
    automated, _ = _run(
        tmp_path / "automated",
        "prepare",
        operator_input={
            "decision": "approved",
            "operator_id": "setsuna701031",
            "automated_decision": True,
            "approval_scope": [TARGET],
        },
    )
    missing_operator, _ = _run(
        tmp_path / "missing",
        "prepare",
        operator_input={
            "decision": "approved",
            "operator_id": "",
            "automated_decision": False,
            "approval_scope": [TARGET],
        },
    )
    expanded_scope, _ = _run(
        tmp_path / "expanded",
        "prepare",
        operator_input={
            "decision": "approved",
            "operator_id": "setsuna701031",
            "automated_decision": False,
            "approval_scope": [TARGET, "core/runtime/runtime.py"],
        },
    )

    assert _formal(automated)["status"] == "invalid"
    assert _formal(missing_operator)["status"] == "invalid"
    assert _formal(expanded_scope)["status"] == "invalid"
    assert "automated_approval_rejected" in _formal(automated)["reason_codes"][0]
    assert "operator_identity_required" in _formal(missing_operator)["reason_codes"][0]
    assert "approval_scope_expansion" in _formal(expanded_scope)["reason_codes"][0]


def test_resume_is_idempotent_and_does_not_auto_approve_or_execute(tmp_path: Path) -> None:
    proposed, session_root = _run(tmp_path, "propose")
    session_id = _formal(proposed)["session_id"]

    paused = resume_formal_persistence_session(session_root, session_id)
    assert paused["status"] == "awaiting_operator_approval"
    assert paused["required_operator_input"]["automated_decision_allowed"] is False
    assert paused["executor_invoked"] is False

    operator_input = {
        "decision": "approved",
        "operator_id": "setsuna701031",
        "automated_decision": False,
        "approval_scope": [TARGET],
    }
    prepared = orchestrate_engineering_runtime(
        _payload("prepare", operator_input=operator_input),
        workspace_root=str(tmp_path / "repo"),
        session_root=str(session_root),
    )
    resumed = resume_formal_persistence_session(session_root, _formal(prepared)["session_id"])
    assert resumed["status"] == "awaiting_mutation_authorization"
    assert resumed["executor_invoked"] is False
    assert resumed["workspace_mutation_performed"] is False
    assert resumed["git_mutation_performed"] is False


def test_conflicting_duplicate_and_tamper_fail_closed(tmp_path: Path) -> None:
    result, session_root = _run(tmp_path, "propose")
    session_id = _formal(result)["session_id"]

    proposal_path = session_root / session_id / "formal-proposal.json"
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["status"] = "tampered"
    proposal_path.write_text(json.dumps(proposal, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    resumed = resume_formal_persistence_session(session_root, session_id)
    assert resumed["status"] == "invalid"

    rerun = orchestrate_engineering_runtime(
        _payload("prepare", operator_input={
            "decision": "approved",
            "operator_id": "setsuna701031",
            "automated_decision": False,
            "approval_scope": [TARGET],
        }),
        workspace_root=str(tmp_path / "repo"),
        session_root=str(session_root),
    )
    assert _formal(rerun)["status"] == "invalid"


def _run_payload(tmp_path: Path, payload: dict) -> tuple[dict, Path]:
    session_root = tmp_path / "sessions"
    result = orchestrate_engineering_runtime(
        payload,
        workspace_root=str(_repo(tmp_path)),
        session_root=str(session_root),
    )
    return result, session_root


def test_scoped_analysis_records_missing_target_and_avoids_unrelated_paths(tmp_path: Path) -> None:
    result, session_root = _run(tmp_path, "propose")
    formal = _formal(result)
    analysis = read_session_artifact(session_root, formal["session_id"], "formal-analysis.json")
    summary = analysis["report"]["repository_summary"]

    assert formal["scoped_analysis_enabled"] is True
    assert formal["normalized_scope"] == [TARGET]
    assert summary["analysis_coverage"] == "bounded_scope_only"
    assert summary["proposed_missing_targets"] == [TARGET]
    assert summary["snapshot_truncated"] is False
    assert TARGET in summary["proposed_missing_targets"]
    assert "examples" in summary["analyzed_paths"]
    assert all(not path.startswith(("core/", "cli/", "tests/")) for path in summary["analyzed_paths"])
    assert not (tmp_path / "repo" / TARGET).exists()


def test_scope_normalization_fail_closed_cases(tmp_path: Path) -> None:
    cases = [
        ("absolute", "/tmp/outside.json", "scoped_analysis_absolute_path"),
        ("drive", "C:/outside.json", "scoped_analysis_absolute_path"),
        ("traversal", "../outside.json", "scoped_analysis_traversal"),
        ("missing_parent", "missing_dir/new.json", "scoped_analysis_missing_parent"),
        ("empty", "", "scoped_analysis_empty_scope"),
    ]
    for name, target, reason in cases:
        payload = _payload("propose")
        payload["scope_constraints"] = [] if name == "empty" else [target]
        payload["target_paths"] = [] if name == "empty" else [target]
        result, _ = _run_payload(tmp_path / name, payload)
        formal = _formal(result)
        assert formal["status"] == "invalid"
        assert reason in formal["reason_codes"][0]


def test_symlink_escape_scope_fails_closed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "examples" / "escape").symlink_to(outside, target_is_directory=True)
    session_root = tmp_path / "sessions"
    payload = _payload("propose")
    payload["scope_constraints"] = ["examples/escape"]
    payload["target_paths"] = ["examples/escape"]

    result = orchestrate_engineering_runtime(payload, workspace_root=str(root), session_root=str(session_root))

    assert _formal(result)["status"] == "invalid"
    assert "scoped_analysis_symlink_rejected" in _formal(result)["reason_codes"][0]


def test_conflicting_scope_on_same_session_fails_closed(tmp_path: Path) -> None:
    result, session_root = _run(tmp_path, "propose")
    payload = _payload("propose")
    payload["scope_constraints"] = ["examples/.keep"]
    payload["target_paths"] = ["examples/.keep"]

    rerun = orchestrate_engineering_runtime(payload, workspace_root=str(tmp_path / "repo"), session_root=str(session_root))

    assert _formal(result)["status"] == "awaiting_operator_approval"
    assert _formal(rerun)["status"] == "invalid"
    assert "formal_analysis_scope_conflict" in _formal(rerun)["reason_codes"][0]
