from __future__ import annotations

from copy import deepcopy

import pytest

from core.agent.runtime_mission_reflection import build_mission_reflection, validate_reflection


NOW = "2026-07-13T00:00:00Z"


def entry(status="completed", **updates):
    value = {"entry_id": "entry-1", "mission_id": "mission-1", "mission_session_id": "session-1", "status": status, "original_input": "create hello.txt", "normalized_input": "create hello.txt", "approval_required": False, "approval_status": "not_required", "attempt_count": 1, "last_result": {"execution_status": status}, "failure": None}
    value.update(updates); return value


def test_completed_reflection_is_deterministic_and_evidence_grounded():
    first = build_mission_reflection(entry(), agent_id="agent", mission={"mission_fingerprint": "mf", "mission_status": "completed"}, session={"session_status": "completed"}, artifact={"structured_intents": [{"operation": "create_file", "path": "hello.txt"}, {"operation": "check_exists", "path": "hello.txt"}]}, now=NOW)
    second = build_mission_reflection(entry(), agent_id="agent", mission={"mission_fingerprint": "mf", "mission_status": "completed"}, session={"session_status": "completed"}, artifact={"structured_intents": [{"operation": "create_file", "path": "hello.txt"}, {"operation": "check_exists", "path": "hello.txt"}]}, now=NOW)
    assert first == second and validate_reflection(first) == []
    assert first["outcome"] == "completed" and "create_then_verify" in first["reusable_patterns"]
    assert first["evidence_quality"] == "sufficient" and first["reflection_confidence"] == "high"


@pytest.mark.parametrize(("status", "approval", "outcome"), [("blocked", "pending", "blocked"), ("failed", "not_required", "failed"), ("blocked", "denied", "denied"), ("cancelled", "not_required", "cancelled")])
def test_terminal_outcomes_are_explicit(status, approval, outcome):
    reflected = build_mission_reflection(entry(status, approval_status=approval, failure={"reasons": ["unsafe path"]}), agent_id="agent", now=NOW)
    assert reflected["outcome"] == outcome
    if outcome in {"blocked", "denied"}: assert "path_traversal" in reflected["avoid_patterns"]


def test_insufficient_evidence_has_low_confidence():
    reflected = build_mission_reflection(entry("cancelled", last_result=None, failure=None, mission_id=None, mission_session_id=None), agent_id="agent", now=NOW)
    assert reflected["evidence_quality"] == "insufficient" and reflected["reflection_confidence"] == "low"


def test_secrets_are_redacted_from_reflection():
    reflected = build_mission_reflection(entry(original_input="create x password=hunter2", normalized_input="create x token=abc", failure={"reasons": ["authorization: Bearer xyz"]}), agent_id="agent", now=NOW)
    text = str(reflected)
    assert "hunter2" not in text and "Bearer xyz" not in text and "[REDACTED]" in text
    assert "secret_redacted" in reflected["risk_notes"]


def test_fingerprint_tampering_is_detected():
    reflected = build_mission_reflection(entry(), agent_id="agent", now=NOW); tampered = deepcopy(reflected); tampered["summary"] = "tampered"
    assert "reflection_fingerprint_mismatch" in validate_reflection(tampered)


def test_validation_failure_is_not_recorded_as_success_pattern():
    reflected = build_mission_reflection(entry("failed", failure={"reasons": ["validation_failed"]}), agent_id="agent", artifact={"structured_intents": [{"operation": "create_file", "path": "hello.txt"}, {"operation": "check_exists", "path": "hello.txt"}]}, now=NOW)
    assert "create_then_verify" not in reflected["reusable_patterns"]
    assert "commit_without_validation" in reflected["avoid_patterns"]
