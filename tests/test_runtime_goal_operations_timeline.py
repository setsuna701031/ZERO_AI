from tests.goal_operations_test_support import make_goal, make_waiting_goal

def test_timeline_uses_persisted_evidence_and_is_stably_ordered(tmp_path):
    _, goal, service = make_waiting_goal(tmp_path); first = service.timeline(goal["goal_id"]).to_dict(); second = service.timeline(goal["goal_id"]).to_dict()
    assert first == second
    assert [item["persisted_timestamp"] for item in first["events"]] == sorted(item["persisted_timestamp"] for item in first["events"])
    categories = {item["event_category"] for item in first["events"]}
    assert {"goal_created", "goal_started", "milestone_waiting_approval", "mission_entry_created", "mission_session_created"} <= categories
    assert "milestone_approved" not in categories and "goal_completed" not in categories

def test_timeline_unknown_goal_fails_closed(tmp_path):
    import pytest
    _, _, service = make_goal(tmp_path)
    with pytest.raises(ValueError, match="goal_not_found"): service.timeline("missing")

def test_timeline_duplicate_event_identities_are_suppressed(tmp_path):
    _, goal, service = make_waiting_goal(tmp_path); events = service.timeline(goal["goal_id"]).to_dict()["events"]
    identities = [item["event_identity"] for item in events]
    assert len(identities) == len(set(identities))
