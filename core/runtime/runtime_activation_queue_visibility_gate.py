"""Disabled queue visibility gate for runtime activation.

This module prepares future scheduler visibility metadata after the queue state
transition preview. It does not expose tasks to schedulers, read or write
queues, perform filesystem or database IO, call scheduler or executor code, run
tools, start workers, or mutate runtime state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_visibility_gate"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_visibility_gate(
    queue_state_transition_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue visibility gate preview."""

    is_mapping = isinstance(queue_state_transition_preview, Mapping)
    source = queue_state_transition_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    mutation_result_snapshot = _snapshot_mapping(
        source.get("mutation_result_snapshot")
    )
    future_state_preview = _snapshot_mapping(source.get("future_state_preview"))
    queue_state_snapshot = {
        "transition_status": source.get("transition_status"),
        "transition_reason": source.get("transition_reason"),
        "transition_boundary_ready": source.get(
            "transition_boundary_ready", False
        ),
        "state_transition_prepared": source.get(
            "state_transition_prepared", False
        ),
        "queue_state_update_allowed": source.get(
            "queue_state_update_allowed", False
        ),
        "state_persistence_allowed": source.get(
            "state_persistence_allowed", False
        ),
        "mutation_result_snapshot": mutation_result_snapshot,
        "future_state_preview": future_state_preview,
    }

    return {
        "enabled": False,
        "mode": "queue_visibility_gate_preview",
        "preview_only": True,
        "input_present": queue_state_transition_preview is not None,
        "input_type": type(queue_state_transition_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "visibility_gate_ready": True,
        "queue_visible": False,
        "scheduler_visibility_allowed": False,
        "task_discovery_allowed": False,
        "runtime_mutation_allowed": False,
        "visibility_status": "disabled",
        "visibility_reason": "queue_visibility_gate_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "queue_state_snapshot": queue_state_snapshot,
        "future_scheduler_visibility_preview": {
            "visibility_layer": "runtime_queue_scheduler_discovery",
            "queue_visible": False,
            "scheduler_visibility_enabled": False,
            "task_discovery_enabled": False,
            "queue_read_enabled": False,
        },
        "queue_read_allowed": False,
        "queue_write_allowed": False,
        "filesystem_io_allowed": False,
        "database_io_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_visibility_gate_disabled",
    }
