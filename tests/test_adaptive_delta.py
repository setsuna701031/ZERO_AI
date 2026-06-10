from core.adaptive.adaptive_delta import build_adaptive_delta


def _obs(**overrides):
    base = {
        "schema": "zero.adaptive_loop.observation.v2",
        "goal_id": "goal-1",
        "cycle_index": 0,
        "runtime_state": "running",
        "runtime_ok": True,
        "adaptive_decision": "continue",
        "evidence_count": 0,
        "validated_evidence_count": 0,
        "remaining_task_count": 2,
        "completed_task_count": 0,
        "failed_task_count": 0,
        "blocked_task_count": 0,
    }
    base.update(overrides)
    return base


def test_initial_delta_is_passive_and_non_terminal() -> None:
    delta = build_adaptive_delta(None, _obs())
    assert delta["reason"] == "initial_observation"
    assert delta["previous_cycle_index"] is None
    assert delta["execution_path"]["persists_records"] is False


def test_delta_detects_progress() -> None:
    delta = build_adaptive_delta(_obs(cycle_index=0), _obs(cycle_index=1, remaining_task_count=1, completed_task_count=1))
    assert delta["has_progress"] is True
    assert delta["regressed"] is False
    assert delta["remaining_task_delta"] == -1


def test_delta_detects_regression() -> None:
    delta = build_adaptive_delta(_obs(cycle_index=0), _obs(cycle_index=1, failed_task_count=1))
    assert delta["regressed"] is True
    assert delta["failed_task_delta"] == 1
