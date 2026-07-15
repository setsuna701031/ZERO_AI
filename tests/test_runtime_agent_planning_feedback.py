from __future__ import annotations

from copy import deepcopy

from core.runtime.runtime_agent_planning_feedback import build_agent_planning_feedback, validate_planning_feedback
from core.runtime.runtime_operator_session import fingerprint


NOW = "2026-07-13T00:00:00Z"


def context(**updates):
    value = {"contract": "zero.runtime.agent_memory_context.v1", "query_text": "create second.txt", "experience_references": [{"experience_id": "experience-1", "similarity_score": 0.8, "outcome": "completed"}], "successful_patterns": ["create_then_verify"], "failure_patterns": [], "recommended_validations": ["verify_content_hash"], "risk_notes": [], "matched_tokens": ["create"]}
    value.update(updates); value["context_fingerprint"] = fingerprint(value); return value


def test_feedback_is_deterministic_sealed_and_bounded():
    kwargs = {"structured_intents": [{"operation": "create_file", "path": "second.txt", "content": "hello"}], "memory_context": context(), "workspace_root": "w", "target_root": "t", "now": NOW}
    first = build_agent_planning_feedback("create second.txt", **kwargs)
    second = build_agent_planning_feedback("create second.txt", **kwargs)
    assert first == second
    assert first["recommended_goal_patterns"] == ["create_then_verify"]
    assert "verify_content_hash" in first["recommended_validations"]
    tampered = deepcopy(first); tampered["confidence"] = 0
    assert "planning_feedback_fingerprint_mismatch" in validate_planning_feedback(tampered)


def test_invalid_context_fails_safe_to_baseline_feedback_and_does_not_leak_secret():
    invalid = context(secret_token="do-not-copy"); invalid["matched_tokens"].append("api_key=do-not-copy")
    value = build_agent_planning_feedback("create second.txt", structured_intents=[{"operation": "create_file", "path": "second.txt"}], memory_context=invalid, now=NOW)
    assert value["applied_recommendations"] == []
    assert "memory_feedback_invalid" in value["risk_notes"]
    assert "do-not-copy" not in str(value)
