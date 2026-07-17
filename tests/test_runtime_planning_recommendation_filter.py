from core.runtime.runtime_planning_recommendation_filter import filter_planning_recommendations


def test_filter_records_supported_unsupported_scope_policy_confidence_and_duplicates():
    values = ["create_then_verify", "create_then_verify", "invent_new_planner", {"recommendation": "verify_content_hash", "target": "other.txt"}, {"recommendation": "verify_file_exists", "confidence": .01}, {"recommendation": "auto_approve"}]
    result = filter_planning_recommendations(values, current_operations=["create_file"], current_targets=["second.txt"], safety_constraints=["operator_approval"])
    assert [item["decision"] for item in result["applied"]] == ["applied"]
    decisions = {item["decision"] for item in result["ignored"]}
    assert {"ignored_duplicate", "ignored_unsupported", "ignored_scope_expansion", "ignored_low_confidence", "ignored_unsafe"} <= decisions
