from core.tasks.engineering_goal_loop import EngineeringGoalLoop


class FakeRepository:
    def __init__(self) -> None:
        self.records = {}
        self.updated = []

    def load_goal(self, goal_id):
        if goal_id not in self.records:
            self.records[goal_id] = {
                "goal_id": goal_id,
                "root_goal_id": goal_id,
                "source_goal_id": goal_id,
                "goal_lineage_id": f"{goal_id}:lineage",
                "branch_type": "root",
                "branch_id": "root",
                "session_id": f"goal-session:{goal_id}",
                "runtime_session_id": f"runtime-session:{goal_id}",
                "metadata": {},
            }
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

    def run_goal(self, goal_id, *, goal_lineage=None):
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


def test_goal_loop_declares_no_continuation_or_replan_authority(tmp_path) -> None:
    loop = EngineeringGoalLoop(
        repo_root=tmp_path,
        repository=FakeRepository(),
        runner=FakeRunner(["continue", "complete"]),
    )
    result = loop.run_until_terminal("goal_a", max_cycles=2, max_continuations=2)

    execution_path = result["execution_path"]
    assert execution_path["goal_loop_uses_goal_loop_dispatcher"] is True
    assert execution_path["goal_loop_uses_terminal_coordinator"] is True
    assert execution_path["goal_loop_owns_continuation_creation"] is False
    assert execution_path["goal_loop_owns_replan_creation"] is False
    assert result["cycles"][0]["goal_loop_dispatcher"]["execution_path"]["dispatcher_only"] is True
