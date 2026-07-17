from core.tasks.engineering_lifecycle_transition import EngineeringLifecycleTransition


def test_engineering_lifecycle_transition_is_passive_contract():
    transition = EngineeringLifecycleTransition(
        "created",
        "running",
        "start",
        adaptive_loop_contract={"loop_state": "initial"},
    )
    record = transition.to_dict()
    assert record["from_state"] == "created"
    assert record["to_state"] == "running"
    assert record["execution_path"]["executes_tasks"] is False
    assert record["execution_path"]["mutates_memory"] is False
