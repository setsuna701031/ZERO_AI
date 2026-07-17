from __future__ import annotations

from core.runtime.runtime_agent_planning_feedback import build_agent_planning_feedback
from core.runtime.runtime_memory_guided_goal_planner import apply_planning_feedback_to_goal_plan
from core.runtime.runtime_operator_session import fingerprint


def test_create_then_verify_adds_dependent_read_only_goal_without_scope_change():
    context = {"contract": "zero.runtime.agent_memory_context.v1", "query_text": "create second.txt", "experience_references": [{"experience_id": "exp-1", "similarity_score": .9, "outcome": "completed"}], "successful_patterns": ["create_then_verify"], "failure_patterns": [], "recommended_validations": ["verify_content_hash"], "risk_notes": [], "matched_tokens": ["create"]}; context["context_fingerprint"] = fingerprint(context)
    feedback = build_agent_planning_feedback("create second.txt", structured_intents=[{"operation": "create_file", "path": "second.txt"}], memory_context=context, now="2026-07-13T00:00:00Z")
    baseline = [{"goal_id": "create", "goal_title": "Create", "goal_description": "Create current target", "goal_type": "modify", "goal_status": "pending", "priority": 0, "depends_on": [], "required_capabilities": ["modify"], "target_scope": ["second.txt"], "acceptance_criteria": ["created"], "validation_requirements": [], "operator_confirmation_required": True, "natural_operation": "create_file", "natural_operation_inputs": {"path": "second.txt"}, "max_attempts": 3}]
    result = apply_planning_feedback_to_goal_plan(baseline, feedback)
    assert [goal["natural_operation"] for goal in result["goal_plan"]] == ["create_file", "check_exists"]
    assert result["goal_plan"][1]["depends_on"] == [result["goal_plan"][0]["goal_id"]]
    assert result["goal_plan"][1]["target_scope"] == ["second.txt"]
    assert result["goal_plan"][0]["operator_confirmation_required"] is True
