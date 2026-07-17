from __future__ import annotations

from core.runtime.runtime_prediction_engine import (
    assert_simulation_does_not_mutate,
    assert_simulation_preserves_lineage,
    compare_simulation_branches,
    create_simulation_branch,
)
from core.runtime.runtime_simulation_engine import (
    assert_simulation_read_only,
    assert_simulation_result_stable,
    compare_runtime_simulations,
    simulate_repair_strategy,
    simulate_runtime_step,
    simulate_transaction_lifecycle,
)
from core.runtime.runtime_transaction_registry import list_transactions


def test_simulation_branch_creation_stable() -> None:
    first = create_simulation_branch(_context(), simulated_steps=[{"step_id": "step-sim"}])
    second = create_simulation_branch(_context(), simulated_steps=[{"step_id": "step-sim"}])

    assert first.branch_id == second.branch_id
    assert first.normalized_digest == second.normalized_digest


def test_simulation_branch_cannot_commit() -> None:
    try:
        assert_simulation_does_not_mutate({"branch_id": "b", "parent_trace_id": "t", "committed": True})
    except AssertionError as exc:
        assert "commit" in str(exc)
    else:
        raise AssertionError("simulation commit should fail")


def test_simulation_branch_cannot_mutate() -> None:
    try:
        assert_simulation_does_not_mutate({"branch_id": "b", "parent_trace_id": "t", "mutation_allowed": True})
    except AssertionError as exc:
        assert "mutate" in str(exc)
    else:
        raise AssertionError("simulation mutation should fail")


def test_simulation_context_is_not_authority() -> None:
    branch = create_simulation_branch(_context(), simulated_steps=[{"step_id": "step-sim"}])

    assert branch.authority_granted is False
    assert branch.mutation_allowed is False


def test_simulated_transaction_lifecycle_does_not_create_real_transaction() -> None:
    before = tuple(tx.transaction_id for tx in list_transactions())
    result = simulate_transaction_lifecycle(_context())
    after = tuple(tx.transaction_id for tx in list_transactions())

    assert before == after
    assert assert_simulation_read_only(result) is True


def test_simulated_repair_path_does_not_invoke_step_executor_side_effect() -> None:
    result = simulate_repair_strategy(_context(strategy_id="strategy-sim"))

    assert result.predicted_repair_paths[0]["step_executor_invoked"] is False
    assert result.predicted_repair_paths[0]["side_effects_invoked"] is False


def test_compare_simulation_branches_deterministic() -> None:
    first = create_simulation_branch(_context(), simulated_steps=[{"step_id": "a"}])
    second = create_simulation_branch(_context(), simulated_steps=[{"step_id": "b"}])

    assert compare_simulation_branches(first, second).normalized_digest == compare_simulation_branches(second, first).normalized_digest
    assert compare_runtime_simulations(simulate_runtime_step(_context()), simulate_repair_strategy(_context()))["deterministic"] is True


def test_simulation_preserves_memory_evidence_lineage() -> None:
    branch = create_simulation_branch(_context(memory_refs=["runtime_memory:sim"], evidence_refs=["runtime_evidence:sim"]))

    assert "runtime_memory:sim" in branch.memory_refs
    assert "runtime_evidence:sim" in branch.predicted_evidence_refs
    assert assert_simulation_preserves_lineage(branch) is True


def test_simulation_digest_stable() -> None:
    first = simulate_runtime_step(_context())
    second = simulate_runtime_step(_context())

    assert assert_simulation_result_stable(first, second) is True
    assert first.normalized_digest == second.normalized_digest


def test_simulation_read_only_invariant_holds() -> None:
    assert assert_simulation_read_only(simulate_runtime_step(_context())) is True


def _context(**overrides):
    payload = {
        "task_id": "task-sim",
        "step_id": "step-sim",
        "trace_id": "trace-sim",
        "source_transaction_id": "runtime_tx:sim-source",
        "source_replay_run_id": "replay_run:sim",
        "source_recovery_attempt_id": "runtime_recovery:sim",
        "source_repair_loop_id": "repair_loop:sim",
        "affected_files": ["workspace/shared/sim.txt"],
    }
    payload.update(overrides)
    return payload
