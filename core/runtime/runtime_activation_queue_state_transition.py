"""Disabled queue state transition boundary for runtime activation.

This module prepares future queue state transition metadata after the mutation
result envelope. It does not write queue state, persist updates, commit
transactions, call scheduler or executor code, run tools, start workers, or
mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_state_transition"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_state_transition(
    queue_mutation_result_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue state transition preview."""

    is_mapping = isinstance(queue_mutation_result_preview, Mapping)
    source = queue_mutation_result_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    executor_snapshot = _snapshot_mapping(source.get("executor_snapshot"))
    mutation_result_preview = _snapshot_mapping(
        source.get("mutation_result_preview")
    )
    mutation_result_snapshot = {
        "result_status": source.get("result_status"),
        "result_reason": source.get("result_reason"),
        "result_boundary_ready": source.get("result_boundary_ready", False),
        "mutation_result_created": source.get("mutation_result_created", False),
        "mutation_success_recorded": source.get(
            "mutation_success_recorded", False
        ),
        "queue_state_update_allowed": source.get(
            "queue_state_update_allowed", False
        ),
        "executor_snapshot": executor_snapshot,
        "mutation_result_preview": mutation_result_preview,
    }

    return {
        "enabled": False,
        "mode": "queue_state_transition_preview",
        "preview_only": True,
        "input_present": queue_mutation_result_preview is not None,
        "input_type": type(queue_mutation_result_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "transition_boundary_ready": True,
        "state_transition_prepared": True,
        "queue_state_update_allowed": False,
        "state_persistence_allowed": False,
        "runtime_mutation_allowed": False,
        "transition_status": "disabled",
        "transition_reason": "queue_state_transition_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "mutation_result_snapshot": mutation_result_snapshot,
        "future_state_preview": {
            "state_transition_type": "runtime_queue_mutation_result",
            "transition_prepared": True,
            "queue_state_update_enabled": False,
            "state_persistence_enabled": False,
            "runtime_update_enabled": False,
            "commit_enabled": False,
        },
        "queue_state_write_allowed": False,
        "persistence_write_allowed": False,
        "transaction_commit_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_state_transition_disabled",
    }
