from __future__ import annotations

import copy

from core.runtime.runtime_end_to_end_orchestrator import create_runtime_session, resume_runtime_session
from core.runtime.runtime_operator_session import INPUT_CONTRACT
from tests.test_runtime_apply_execution_plan_builder import NOW
from tests.test_runtime_execution_plan_review_gate import review

def envelope(session, kind, payload, number=1):
    return {"contract": INPUT_CONTRACT, "session_id": session["session_id"], "input_id": f"input-{number}",
        "input_type": kind, "operator_id": "operator", "submitted_at": NOW, "payload": copy.deepcopy(payload)}

def setup(tmp_path):
    target = tmp_path / "target"; target.mkdir(); workspace = tmp_path / "workspace"; workspace.mkdir()
    session = create_runtime_session({"text": "repair", "target_files": ["a.py"]}, target_root=target, workspace_root=workspace, now=NOW)
    return session, target, workspace

def test_create_pauses_without_automatic_approval(tmp_path):
    session, _, _ = setup(tmp_path)
    assert session["current_phase"] == "proposal_ready" and session["required_action"] == "operator_approval"
    assert session["artifacts"]["approval"] is None and session["artifacts"]["execution_plan"] is None

def test_approval_delegates_admission_plan_and_duplicate_is_idempotent(tmp_path):
    session, target, workspace = setup(tmp_path); payload = {"decision": "approve", "expires_at": "2026-07-12T01:00:00+00:00"}
    item = envelope(session, "proposal_approval", payload)
    result = resume_runtime_session(session, operator_input=item, target_root=target, workspace_root=workspace, now=NOW)
    assert result["required_action"] == "execution_plan_review"
    assert result["artifacts"]["admission"]["apply_admitted"] is True
    assert result["artifacts"]["execution_plan"]["plan_ready"] is True
    assert resume_runtime_session(result, operator_input=item, target_root=target, workspace_root=workspace, now=NOW) == result

def test_review_requires_controlled_request_and_no_dry_run(tmp_path):
    session, target, workspace = setup(tmp_path)
    session = resume_runtime_session(session, operator_input=envelope(session, "proposal_approval", {"decision": "approve", "expires_at": "2026-07-12T01:00:00+00:00"}), target_root=target, workspace_root=workspace, now=NOW)
    payload = review(session["artifacts"]["execution_plan"]); payload["reviewed_at"] = NOW; payload["expires_at"] = "2026-07-12T01:00:00+00:00"
    result = resume_runtime_session(session, operator_input=envelope(session, "execution_plan_review", payload, 2), target_root=target, workspace_root=workspace, now=NOW)
    assert result["required_action"] == "controlled_execution_request"
    assert result["artifacts"]["controlled_execution_result"] is None

