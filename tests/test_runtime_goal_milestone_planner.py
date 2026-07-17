from core.agent.runtime_goal_milestone_planner import plan_goal_milestones
from core.agent.runtime_long_horizon_goal import create_long_horizon_goal, stable_milestone_order
from core.runtime.runtime_operator_session import fingerprint

NOW = "2026-07-13T00:00:00Z"


def goal(tmp_path, text="完成一個簡單網站，包含首頁、樣式與驗證"):
    return create_long_horizon_goal(text, workspace_root=tmp_path, target_root=tmp_path, now=NOW)


def test_static_site_plan_is_deterministic_acyclic_and_approval_aware(tmp_path):
    first = plan_goal_milestones(goal(tmp_path), now=NOW); second = plan_goal_milestones(goal(tmp_path), now=NOW)
    assert first == second
    assert [first["milestones"][key]["milestone_key"] for key in first["milestone_order"]] == ["inspect_workspace", "create_project_structure", "create_index_html", "create_stylesheet", "verify_files", "final_review"]
    assert stable_milestone_order(first["milestones"]) == first["milestone_order"]
    assert all(first["milestones"][key]["approval_expected"] for key in first["milestone_order"][1:4])
    assert all("command" not in str(template) for item in first["milestones"].values() for template in item["mission_templates"])


def test_unsupported_is_blocked_and_memory_can_only_add_validation(tmp_path):
    unsupported = plan_goal_milestones(goal(tmp_path, "想辦法改善所有事情"), now=NOW)
    assert unsupported["supported"] is False and unsupported["manual_review_required"]
    context = {"contract": "zero.runtime.agent_memory_context.v1", "query_text": "site", "experience_references": [], "successful_patterns": ["create_then_verify"], "failure_patterns": [], "recommended_validations": ["verify_content_hash"], "risk_notes": ["workspace_containment_required"], "matched_tokens": []}; context["context_fingerprint"] = fingerprint(context)
    planned = plan_goal_milestones(goal(tmp_path), memory_context=context, now=NOW)
    keys = [planned["milestones"][key]["milestone_key"] for key in planned["milestone_order"]]
    assert "validate_content" in keys
    assert {path for item in planned["milestones"].values() for template in item["mission_templates"] for path in ("index.html", "styles.css") if path in template["natural_language"]} <= {"index.html", "styles.css"}
    assert planned["milestones"][planned["milestone_order"][1]]["approval_expected"] is True


def test_memory_unavailable_uses_baseline(tmp_path):
    planned = plan_goal_milestones(goal(tmp_path), memory_context=None, now=NOW)
    assert planned["supported"] and planned["memory_feedback_unavailable"] and len(planned["milestone_order"]) == 6
