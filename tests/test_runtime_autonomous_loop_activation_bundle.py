from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_autonomous_loop_activation import (
    evaluate_runtime_loop_activation,
    evaluate_runtime_loop_stop_condition,
    evaluate_runtime_pause_resume,
    run_runtime_tick_cycle,
)


def closure_record():
    return {
        "loop_closure_authorized": True,
        "loop_closure_id": "closure-1",
    }


def test_loop_activation_authorizes_bounded_tick_cycle_request():
    record = evaluate_runtime_loop_activation(closure_record(), max_iterations=3)

    assert record["loop_activation_authorized"] is True
    assert record["source_loop_closure_id"] == "closure-1"
    assert record["tick_cycle_requested"] is True
    assert record["runtime_state_mutated"] is False


def test_loop_activation_denies_missing_closure_record():
    record = evaluate_runtime_loop_activation(None, max_iterations=1)

    assert record["loop_activation_authorized"] is False
    assert record["denial_reason"] == "missing_loop_closure_record"
    assert record["runtime_state_mutated"] is False


def test_loop_activation_denies_rejected_closure_record():
    record = evaluate_runtime_loop_activation({"loop_closure_authorized": False, "loop_closure_id": "bad"})

    assert record["loop_activation_authorized"] is False
    assert record["denial_reason"] == "loop_closure_not_authorized"


def test_loop_activation_denies_when_paused():
    record = evaluate_runtime_loop_activation(closure_record(), paused=True)

    assert record["loop_activation_authorized"] is False
    assert record["denial_reason"] == "runtime_paused"


def test_tick_cycle_without_handler_stays_data_only():
    activation = evaluate_runtime_loop_activation(closure_record(), max_iterations=1)
    cycle = run_runtime_tick_cycle(activation)

    assert cycle["tick_cycle_authorized"] is True
    assert cycle["tick_handler_called"] is False
    assert cycle["tick_handler_result_received"] is False
    assert cycle["runtime_state_mutated"] is False


def test_tick_cycle_with_handler_receives_tiny_payload_only():
    activation = evaluate_runtime_loop_activation(closure_record(), max_iterations=1)
    received = []

    def handler(payload):
        received.append(payload)
        return {"status": "accepted"}

    cycle = run_runtime_tick_cycle(activation, tick_handler=handler)

    assert cycle["tick_cycle_authorized"] is True
    assert cycle["tick_handler_called"] is True
    assert cycle["tick_handler_result_received"] is True
    assert cycle["tick_handler_result"] == {"status": "accepted"}
    assert received == [
        {
            "source_loop_activation_id": activation["loop_activation_id"],
            "iteration_index": 1,
        }
    ]


def test_tick_cycle_denies_rejected_activation():
    cycle = run_runtime_tick_cycle({"loop_activation_authorized": False, "loop_activation_id": "no"})

    assert cycle["tick_cycle_authorized"] is False
    assert cycle["denial_reason"] == "loop_activation_not_authorized"


def test_tick_cycle_handler_failure_is_deterministic_denial():
    activation = evaluate_runtime_loop_activation(closure_record(), max_iterations=1)

    def handler(_payload):
        raise RuntimeError("boom")

    cycle = run_runtime_tick_cycle(activation, tick_handler=handler)

    assert cycle["tick_cycle_authorized"] is False
    assert cycle["tick_handler_called"] is True
    assert cycle["tick_handler_result_received"] is False
    assert cycle["denial_reason"] == "tick_handler_failed:RuntimeError"
    assert cycle["runtime_state_mutated"] is False


def test_stop_condition_stops_at_max_iterations():
    activation = evaluate_runtime_loop_activation(closure_record(), max_iterations=1)
    cycle = run_runtime_tick_cycle(activation)
    stop = evaluate_runtime_loop_stop_condition(cycle, iteration_count=1, max_iterations=1)

    assert stop["loop_stop_required"] is True
    assert stop["loop_continue_authorized"] is False
    assert stop["stop_reason"] == "max_iterations_reached"
    assert stop["runtime_state_mutated"] is False


def test_stop_condition_allows_continue_within_bounds():
    activation = evaluate_runtime_loop_activation(closure_record(), max_iterations=3)
    cycle = run_runtime_tick_cycle(activation)
    stop = evaluate_runtime_loop_stop_condition(cycle, iteration_count=1, max_iterations=3)

    assert stop["loop_stop_required"] is False
    assert stop["loop_continue_authorized"] is True
    assert stop["stop_reason"] == "continue_within_bounds"


def test_pause_resume_records_do_not_mutate_state():
    paused = evaluate_runtime_pause_resume("pause")
    resumed = evaluate_runtime_pause_resume("resume", paused)

    assert paused["runtime_paused"] is True
    assert resumed["runtime_paused"] is False
    assert paused["runtime_state_mutated"] is False
    assert resumed["runtime_state_mutated"] is False


def test_source_boundary_has_no_forbidden_runtime_surface_imports_or_calls():
    source = Path("core/runtime/runtime_autonomous_loop_activation.py").read_text(encoding="utf-8").lower()
    forbidden = [
        "import scheduler",
        "from scheduler",
        "import executor",
        "from executor",
        "task_runner",
        "agent_loop",
        "work_package_operator",
        "progress_memory",
        "run_one_step",
        ".run(",
    ]

    for token in forbidden:
        assert token not in source
