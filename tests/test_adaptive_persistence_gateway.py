from __future__ import annotations

from core.tasks.adaptive_persistence_gateway import AdaptivePersistenceGateway


class FakeRepository:
    def __init__(self) -> None:
        self.goals = {"goal_1": {"goal_id": "goal_1", "metadata": {}}}
        self.updates = []

    def update_goal(self, goal_id, patch):
        self.updates.append((goal_id, patch))
        record = self.goals.setdefault(goal_id, {"goal_id": goal_id, "metadata": {}})
        metadata = record.setdefault("metadata", {})
        metadata.update(patch.get("metadata", {}))
        return record

    def load_goal(self, goal_id):
        return self.goals.get(goal_id)


class FakeEvidenceAuthority:
    def __init__(self) -> None:
        self.records = []

    def register_decision_evidence(self, record):
        self.records.append(dict(record))
        result = dict(record)
        result["evidence_id"] = record["decision_id"]
        return result

    def get_goal_chain(self, goal_id):
        class Chain:
            def to_dict(self):
                return {"goal_id": goal_id, "evidence_ids": ["decision_x"], "validated_count": 1}
        return Chain()


def _cycle():
    return {
        "goal_id": "goal_1",
        "cycle_index": 0,
        "runtime_state": "complete",
        "adaptive_decision": "complete",
        "adaptive_decision_record": {
            "decision": "complete",
            "reason": "goal_completed",
            "outcome_class": "success",
            "next_action": "stop",
            "evidence_chain": [],
        },
        "runner_result": {"runtime_result": {"state": "complete", "iterations": []}},
        "continuation_work_item": {},
        "replan_record": {},
        "adaptive_planning_record": {},
        "adaptive_replan_contract": {"loop_action": "complete"},
    }


def test_gateway_persists_adaptive_record_and_decision_evidence(tmp_path):
    repo = FakeRepository()
    authority = FakeEvidenceAuthority()
    gateway = AdaptivePersistenceGateway(repo_root=tmp_path, repository=repo, evidence_authority=authority)
    cycle = _cycle()

    gateway.persist_cycle(cycle, replan_count=0, continuation_count=0, max_replans=1, max_continuations=3)

    assert cycle["adaptive_planning_record"]["persistence_gateway_schema"] == "zero.adaptive_persistence_gateway.v1"
    assert authority.records
    assert cycle["decision_evidence"]["decision_id"]
    assert cycle["evidence_chain"]["goal_id"] == "goal_1"
    assert any(update[0] == "goal_1" for update in repo.updates)


def test_gateway_links_continuation_decision_evidence(tmp_path):
    repo = FakeRepository()
    repo.goals["goal_1__continuation_1"] = {"goal_id": "goal_1__continuation_1", "metadata": {}}
    authority = FakeEvidenceAuthority()
    gateway = AdaptivePersistenceGateway(repo_root=tmp_path, repository=repo, evidence_authority=authority)
    cycle = _cycle()
    cycle["continuation_work_item"] = {"goal_id": "goal_1__continuation_1"}

    gateway.persist_cycle(cycle, replan_count=0, continuation_count=1, max_replans=1, max_continuations=3)

    assert cycle["continuation_work_item"]["decision_evidence_id"] == cycle["decision_evidence"]["decision_id"]
    assert repo.goals["goal_1__continuation_1"]["metadata"]["decision_evidence_id"] == cycle["decision_evidence"]["decision_id"]
