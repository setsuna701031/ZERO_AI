from __future__ import annotations

from core.agent.runtime_goal_operations import GoalOperationsConfig
from core.agent.runtime_goal_operations_health import build_health


def test_runtime_invariant_cross_goal_mission_and_session_ownership_is_rejected(tmp_path):
    goals = [{"goal_id": identity, "goal_status": "ready", "progress": {}, "replan_count": 0, "max_replans": 3} for identity in ("goal-a", "goal-b")]
    shared = {"entry_status": "running", "entry_id": "entry-shared", "mission_id": "mission-shared", "session_id": "session-shared"}
    references = {goal["goal_id"]: {"chains": [{**shared}], "issues": [], "duplicates": []} for goal in goals}
    sources = {"config": GoalOperationsConfig(str(tmp_path)), "goals": goals, "entries": {}, "errors": [], "daemon": None, "agent": None, "inbox": None}
    health = build_health(sources, references)
    duplicate_types = {item["type"] for item in health["duplicate_references"]}
    assert health["critical"] is True
    assert duplicate_types == {"duplicate_mission_ownership", "duplicate_session_ownership"}
