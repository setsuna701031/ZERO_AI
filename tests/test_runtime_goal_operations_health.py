import json

from core.runtime.runtime_operator_session import fingerprint
from tests.goal_operations_test_support import make_goal

def test_health_reports_healthy_ready_state(tmp_path):
    _, _, service = make_goal(tmp_path); health = service.health().to_dict()
    assert health["critical"] is False and health["ready"] is True
    assert health["checks"]["runtime_budget_invariant"] is True

def test_health_corrupt_goal_index_is_critical_and_read_only(tmp_path):
    controller, _, service = make_goal(tmp_path); path = controller.goals_root / "goal-index.json"
    value = json.loads(path.read_text(encoding="utf-8")); value["goal_ids"].append("ghost"); path.write_text(json.dumps(value), encoding="utf-8")
    before = path.read_bytes(); health = service.health().to_dict()
    assert health["critical"] is True and health["checks"]["goal_store"] is False
    assert path.read_bytes() == before

def test_health_replan_limit_exceeded_is_critical(tmp_path):
    controller, goal, service = make_goal(tmp_path); path = controller._goal_path(goal["goal_id"])
    value = controller.show(goal["goal_id"]); value["replan_count"] = value["max_replans"] + 1; value.pop("goal_fingerprint"); value["goal_fingerprint"] = fingerprint(value); path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    health = service.health().to_dict()
    assert health["critical"] and "replan_limit_exceeded" in str(health["issues"])
