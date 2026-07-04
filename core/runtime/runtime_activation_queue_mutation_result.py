"""Disabled result envelope for runtime queue mutation activation.

This module prepares future result metadata after the disabled executor shell.
It does not execute mutations, persist mutation results, write queue data,
update state, commit transactions, call scheduler or executor runtime code, run
tools, start workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_mutation_result"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_mutation_result(
    queue_mutation_executor_shell_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue mutation result preview."""

    is_mapping = isinstance(queue_mutation_executor_shell_preview, Mapping)
    source = queue_mutation_executor_shell_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    final_gate_snapshot = _snapshot_mapping(source.get("final_gate_snapshot"))
    executor_shell_preview = _snapshot_mapping(
        source.get("future_executor_shell_preview")
    )
    executor_snapshot = {
        "executor_shell_status": source.get("executor_shell_status"),
        "executor_shell_reason": source.get("executor_shell_reason"),
        "executor_shell_ready": source.get("executor_shell_ready", False),
        "mutation_executor_available": source.get(
            "mutation_executor_available", False
        ),
        "mutation_execution_started": source.get(
            "mutation_execution_started", False
        ),
        "mutation_execution_completed": source.get(
            "mutation_execution_completed", False
        ),
        "final_gate_snapshot": final_gate_snapshot,
        "future_executor_shell_preview": executor_shell_preview,
    }

    return {
        "enabled": False,
        "mode": "queue_mutation_result_preview",
        "preview_only": True,
        "input_present": queue_mutation_executor_shell_preview is not None,
        "input_type": type(queue_mutation_executor_shell_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "result_boundary_ready": True,
        "mutation_result_created": False,
        "mutation_success_recorded": False,
        "queue_state_update_allowed": False,
        "runtime_mutation_allowed": False,
        "result_status": "disabled",
        "result_reason": "queue_mutation_result_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "executor_snapshot": executor_snapshot,
        "mutation_result_preview": {
            "result_type": "runtime_queue_mutation",
            "result_created": False,
            "success_recorded": False,
            "queue_state_update_enabled": False,
            "runtime_update_enabled": False,
            "commit_enabled": False,
        },
        "queue_write_allowed": False,
        "state_update_allowed": False,
        "transaction_commit_allowed": False,
        "scheduler_call_allowed": False,
        "executor_runtime_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_mutation_result_disabled",
    }
