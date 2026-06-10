from core.adaptive.adaptive_observation import AdaptiveObservation, build_adaptive_observation_from_cycle


def test_observation_from_cycle_summarizes_runtime_and_progress() -> None:
    cycle = {
        "goal_id": "goal-1",
        "cycle_index": 2,
        "ok": True,
        "runtime_state": "completed",
        "engineering_runtime_contract": {
            "runtime_result": {"state": "completed"},
            "adaptive_decision": {
                "decision": "complete",
                "progress": {
                    "remaining_tasks": [],
                    "completed_tasks": ["a", "b"],
                    "failed_tasks": [],
                    "blocked_tasks": [],
                },
            },
        },
        "evidence_chain": {"validated_count": 3},
    }
    data = build_adaptive_observation_from_cycle(cycle)
    assert data["schema"] == "zero.adaptive_loop.observation.v2"
    assert data["goal_id"] == "goal-1"
    assert data["adaptive_decision"] == "complete"
    assert data["completed_task_count"] == 2
    assert data["validated_evidence_count"] == 3
    assert data["execution_path"]["executes_tasks"] is False


def test_observation_from_mapping_round_trips() -> None:
    observation = AdaptiveObservation.from_mapping({
        "goal_id": "goal-1",
        "cycle_index": 1,
        "runtime_state": "running",
        "runtime_ok": True,
        "adaptive_decision": "continue",
    })
    assert observation.to_dict()["runtime_state"] == "running"
