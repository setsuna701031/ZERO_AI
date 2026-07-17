"""Disabled executor shell for runtime queue mutation activation.

This module prepares future executor shell metadata after the final safety
gate. It does not perform queue mutations, write queue data, call storage, begin
or commit transactions, call scheduler or executor runtime code, run tools,
start workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_mutation_executor_shell"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_mutation_executor_shell(
    queue_mutation_final_gate_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue mutation executor shell preview."""

    is_mapping = isinstance(queue_mutation_final_gate_preview, Mapping)
    source = queue_mutation_final_gate_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    dry_run_snapshot = _snapshot_mapping(source.get("dry_run_snapshot"))
    readiness_preview = _snapshot_mapping(
        source.get("final_mutation_readiness_preview")
    )
    final_gate_snapshot = {
        "final_gate_status": source.get("final_gate_status"),
        "final_gate_reason": source.get("final_gate_reason"),
        "final_gate_ready": source.get("final_gate_ready", False),
        "safety_check_passed": source.get("safety_check_passed", False),
        "mutation_execution_authorized": source.get(
            "mutation_execution_authorized", False
        ),
        "dry_run_snapshot": dry_run_snapshot,
        "final_mutation_readiness_preview": readiness_preview,
    }

    return {
        "enabled": False,
        "mode": "queue_mutation_executor_shell_preview",
        "preview_only": True,
        "input_present": queue_mutation_final_gate_preview is not None,
        "input_type": type(queue_mutation_final_gate_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "executor_shell_ready": True,
        "mutation_executor_available": False,
        "mutation_execution_started": False,
        "mutation_execution_completed": False,
        "queue_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "executor_shell_status": "disabled",
        "executor_shell_reason": "queue_mutation_executor_shell_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "final_gate_snapshot": final_gate_snapshot,
        "future_executor_shell_preview": {
            "executor_layer": "runtime_queue_mutation",
            "executor_available": False,
            "execution_start_enabled": False,
            "execution_completion_enabled": False,
            "queue_write_enabled": False,
            "runtime_write_enabled": False,
        },
        "queue_write_allowed": False,
        "storage_call_allowed": False,
        "transaction_begin_allowed": False,
        "transaction_commit_allowed": False,
        "scheduler_call_allowed": False,
        "executor_runtime_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_mutation_executor_shell_disabled",
    }
