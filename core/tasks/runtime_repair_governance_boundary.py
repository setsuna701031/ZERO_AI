from __future__ import annotations

from typing import Any, Dict, Mapping

from core.tasks.runtime_state_hygiene import (
    freeze_runtime_export,
)


RUNTIME_REPAIR_GOVERNANCE_BOUNDARY_TYPE = (
    "runtime_repair_governance_boundary"
)

RUNTIME_REPAIR_GOVERNANCE_BOUNDARY_VERSION = (
    "runtime_repair_governance_boundary.v1"
)


def build_runtime_repair_governance_boundary(
    *,
    replay_chain: Any,
    snapshot: Any,
    executor_contract: Any,
) -> Dict[str, Any]:
    safe_replay_chain = (
        replay_chain
        if isinstance(
            replay_chain,
            Mapping,
        )
        else {}
    )

    safe_snapshot = (
        snapshot
        if isinstance(
            snapshot,
            Mapping,
        )
        else {}
    )

    safe_executor_contract = (
        executor_contract
        if isinstance(
            executor_contract,
            Mapping,
        )
        else {}
    )

    scheduler_summary = (
        build_runtime_repair_scheduler_boundary_summary(
            safe_replay_chain,
            safe_snapshot,
            safe_executor_contract,
        )
    )

    agent_loop_summary = (
        build_runtime_repair_agent_loop_boundary_summary(
            safe_replay_chain,
            safe_snapshot,
            safe_executor_contract,
        )
    )

    recovery_summary = (
        build_runtime_repair_recovery_boundary_summary(
            safe_replay_chain,
            safe_snapshot,
            safe_executor_contract,
        )
    )

    result = {
        "boundary_type": (
            RUNTIME_REPAIR_GOVERNANCE_BOUNDARY_TYPE
        ),
        "boundary_version": (
            RUNTIME_REPAIR_GOVERNANCE_BOUNDARY_VERSION
        ),
        "transaction_id": _safe_text(
            safe_snapshot.get(
                "transaction_id"
            )
        ),
        "task_id": _safe_text(
            safe_snapshot.get(
                "task_id"
            )
        ),
        "proposal_id": _safe_text(
            safe_snapshot.get(
                "proposal_id"
            )
        ),
        "scheduler_summary": (
            freeze_runtime_export(
                scheduler_summary
            )
        ),
        "agent_loop_summary": (
            freeze_runtime_export(
                agent_loop_summary
            )
        ),
        "recovery_summary": (
            freeze_runtime_export(
                recovery_summary
            )
        ),
        "execution_allowed": False,
        "scheduler_resume_allowed": False,
        "filesystem_resume_allowed": False,
        "human_summary": (
            "Governance boundary prepared."
        ),
    }

    return freeze_runtime_export(
        result
    )


def build_runtime_repair_scheduler_boundary_summary(
    replay_chain: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    executor_contract: Mapping[str, Any],
) -> Dict[str, Any]:
    return freeze_runtime_export(
        {
            "summary_type": (
                "runtime_repair_scheduler_boundary_summary"
            ),
            "transaction_id": _safe_text(
                snapshot.get(
                    "transaction_id"
                )
            ),
            "transaction_state": _safe_text(
                snapshot.get(
                    "transaction_state"
                )
            ),
            "queue_item_count": int(
                replay_chain.get(
                    "queue_item_count",
                    0,
                )
            ),
            "replay_safe": bool(
                replay_chain.get(
                    "replay_safe"
                )
            ),
            "execution_allowed": bool(
                executor_contract.get(
                    "execution_allowed"
                )
            ),
            "scheduler_resume_allowed": False,
        }
    )


def build_runtime_repair_agent_loop_boundary_summary(
    replay_chain: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    executor_contract: Mapping[str, Any],
) -> Dict[str, Any]:
    return freeze_runtime_export(
        {
            "summary_type": (
                "runtime_repair_agent_loop_boundary_summary"
            ),
            "task_id": _safe_text(
                snapshot.get(
                    "task_id"
                )
            ),
            "proposal_id": _safe_text(
                snapshot.get(
                    "proposal_id"
                )
            ),
            "transaction_state": _safe_text(
                snapshot.get(
                    "transaction_state"
                )
            ),
            "continuation_allowed": bool(
                replay_chain.get(
                    "continuation_allowed"
                )
            ),
            "dry_run_only": bool(
                executor_contract.get(
                    "dry_run_only"
                )
            ),
            "filesystem_write_allowed": False,
        }
    )


def build_runtime_repair_recovery_boundary_summary(
    replay_chain: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    executor_contract: Mapping[str, Any],
) -> Dict[str, Any]:
    return freeze_runtime_export(
        {
            "summary_type": (
                "runtime_repair_recovery_boundary_summary"
            ),
            "snapshot_id": _safe_text(
                snapshot.get(
                    "snapshot_id"
                )
            ),
            "chain_id": _safe_text(
                replay_chain.get(
                    "chain_id"
                )
            ),
            "replay_safe": bool(
                replay_chain.get(
                    "replay_safe"
                )
            ),
            "execution_allowed": bool(
                executor_contract.get(
                    "execution_allowed"
                )
            ),
            "filesystem_resume_allowed": False,
        }
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()