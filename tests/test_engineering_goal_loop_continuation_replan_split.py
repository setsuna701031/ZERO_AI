from core.tasks.engineering_goal_loop import EngineeringGoalLoop


class FakeRepository:
    def __init__(self) -> None:
        self.records = {}
        self.updated = []

    def load_goal(self, goal_id):
        return self.records.get(goal_id)

    def save_goal(self, record):
        self.records[record["goal_id"]] = dict(record)
        return self.records[record["goal_id"]]

    def update_goal(self, goal_id, patch):
        self.updated.append((goal_id, patch))
        self.records.setdefault(goal_id, {"goal_id": goal_id, "metadata": {}})
        self.records[goal_id].setdefault("metadata", {}).update(patch.get("metadata", {}))
        return self.records[goal_id]


class FakeRunner:
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def run_goal(self, goal_id):
        decision = self.decisions.pop(0)
        return {
            "ok": decision == "complete",
            "action": "run_goal",
            "goal_id": goal_id,
            "runtime_request": {},
            "runtime_result": {"state": "completed" if decision == "complete" else "running", "ok": decision == "complete"},
            "runtime_stdout": "",
            "runtime_root_cause": {},
            "adaptive_decision": {
                "decision": decision,
                "reason": f"{decision}_reason",
                "confidence": 1.0,
                "continuation_plan": {
                    "next_runtime_request": {"payload": {"goal": "Continue"}},
                    "work_item_template": {"objective": "Continue", "acceptance": {}},
                    "evidence_chain": [],
                } if decision == "continue" else {},
                "replan_request": {
                    "reason": "recoverable_runtime_failure",
                    "evidence_chain": [],
                } if decision == "replan" else {},
                "adaptive_planning_record": {"outcome_class": decision, "next_action": decision},
            },
            "issue_summary": {},
        }


def test_goal_loop_delegates_continuation_to_coordinator(tmp_path) -> None:
    repo = FakeRepository()
    loop = EngineeringGoalLoop(repo_root=tmp_path, repository=repo, runner=FakeRunner(["continue", "complete"]))
    result = loop.run_until_terminal("goal_a", max_cycles=2, max_continuations=2)
    first = result["cycles"][0]
    assert first["continuation_work_item"]["continuation_coordinator"]["created_work_item"] is True
    assert result["continuation_runtime"]["continuation_count"] == 1
    assert result["execution_path"]["goal_loop_uses_continuation_coordinator"] is True
    assert result["execution_path"]["goal_loop_owns_continuation_creation"] is False


def test_goal_loop_delegates_replan_to_coordinator(tmp_path) -> None:
    repo = FakeRepository()
    loop = EngineeringGoalLoop(repo_root=tmp_path, repository=repo, runner=FakeRunner(["replan"]))
    result = loop.run_until_terminal("goal_a", max_cycles=1, max_replans=1)
    first = result["cycles"][0]
    assert first["replan_record"]["replan_coordinator"]["created_replan_record"] is True
    assert result["replan_runtime"]["replan_count"] == 1
    assert result["execution_path"]["goal_loop_uses_replan_coordinator"] is True
    assert result["execution_path"]["goal_loop_owns_replan_creation"] is False
