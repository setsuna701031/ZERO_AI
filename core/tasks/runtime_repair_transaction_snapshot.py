from __future__ import annotations

import hashlib
import json

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_state_hygiene import (
    freeze_runtime_export,
    make_json_safe,
)


RUNTIME_REPAIR_TRANSACTION_SNAPSHOT_TYPE = (
    "runtime_repair_transaction_snapshot"
)

RUNTIME_REPAIR_TRANSACTION_SNAPSHOT_VERSION = (
    "runtime_repair_transaction_snapshot.v1"
)


def build_runtime_repair_transaction_snapshot(
    transaction: Any,
    *,
    controlled_apply: Any = None,
    executor_contract: Any = None,
) -> Dict[str, Any]:
    """
    Deterministic replay-safe transaction snapshot layer.

    This layer NEVER:
    - writes files
    - schedules tasks
    - executes commands
    - mutates runtime state
    - persists to disk

    It only creates:
    - replay-safe snapshot payload
    - crash recovery payload
    - hydration-safe export
    """

    tx = (
        transaction
        if isinstance(transaction, Mapping)
        else {}
    )

    apply_data = (
        controlled_apply
        if isinstance(
            controlled_apply,
            Mapping,
        )
        else {}
    )

    executor_data = (
        executor_contract
        if isinstance(
            executor_contract,
            Mapping,
        )
        else {}
    )

    staged_mutations = (
        tx.get("staged_mutations")
        if isinstance(
            tx.get(
                "staged_mutations"
            ),
            list,
        )
        else []
    )

    committed_mutations = (
        tx.get("committed_mutations")
        if isinstance(
            tx.get(
                "committed_mutations"
            ),
            list,
        )
        else []
    )

    rolled_back_mutations = (
        tx.get("rolled_back_mutations")
        if isinstance(
            tx.get(
                "rolled_back_mutations"
            ),
            list,
        )
        else []
    )

    audit_events = (
        tx.get("audit_events")
        if isinstance(
            tx.get(
                "audit_events"
            ),
            list,
        )
        else []
    )

    snapshot = {
        "snapshot_type": (
            RUNTIME_REPAIR_TRANSACTION_SNAPSHOT_TYPE
        ),
        "snapshot_version": (
            RUNTIME_REPAIR_TRANSACTION_SNAPSHOT_VERSION
        ),
        "snapshot_id": "",
        "transaction_id": _safe_text(
            tx.get(
                "transaction_id"
            )
        ),
        "task_id": _safe_text(
            tx.get(
                "task_id"
            )
        ),
        "proposal_id": _safe_text(
            tx.get(
                "proposal_id"
            )
        ),
        "transaction_state": _safe_text(
            tx.get("state")
        ),
        "transaction_summary": _safe_text(
            tx.get("summary")
        ),
        "staged_mutation_count": (
            len(staged_mutations)
        ),
        "committed_mutation_count": (
            len(committed_mutations)
        ),
        "rolled_back_mutation_count": (
            len(rolled_back_mutations)
        ),
        "audit_event_count": (
            len(audit_events)
        ),
        "controlled_apply": (
            freeze_runtime_export(
                apply_data
            )
        ),
        "executor_contract": (
            freeze_runtime_export(
                executor_data
            )
        ),
        "recovery_payload": (
            build_runtime_repair_recovery_payload(
                tx,
                controlled_apply=apply_data,
                executor_contract=executor_data,
            )
        ),
        "hydration_contract": (
            build_runtime_repair_hydration_contract(
                tx,
                controlled_apply=apply_data,
                executor_contract=executor_data,
            )
        ),
        "replay_safe": True,
        "filesystem_persisted": False,
        "human_summary": (
            build_runtime_repair_snapshot_summary(
                tx
            )
        ),
    }

    snapshot["snapshot_id"] = (
        _build_snapshot_id(
            snapshot
        )
    )

    return freeze_runtime_export(
        snapshot
    )


def build_runtime_repair_recovery_payload(
    transaction: Mapping[str, Any],
    *,
    controlled_apply: Mapping[str, Any],
    executor_contract: Mapping[str, Any],
) -> Dict[str, Any]:
    return freeze_runtime_export(
        {
            "payload_type": (
                "runtime_repair_recovery_payload"
            ),
            "transaction_id": _safe_text(
                transaction.get(
                    "transaction_id"
                )
            ),
            "transaction_state": _safe_text(
                transaction.get("state")
            ),
            "apply_allowed": bool(
                controlled_apply.get(
                    "apply_allowed"
                )
            ),
            "execution_allowed": bool(
                executor_contract.get(
                    "execution_allowed"
                )
            ),
            "dry_run_only": bool(
                executor_contract.get(
                    "dry_run_only"
                )
            ),
            "recovery_required": False,
            "filesystem_recovery_required": False,
        }
    )


def build_runtime_repair_hydration_contract(
    transaction: Mapping[str, Any],
    *,
    controlled_apply: Mapping[str, Any],
    executor_contract: Mapping[str, Any],
) -> Dict[str, Any]:
    return freeze_runtime_export(
        {
            "contract_type": (
                "runtime_repair_hydration_contract"
            ),
            "transaction_id": _safe_text(
                transaction.get(
                    "transaction_id"
                )
            ),
            "transaction_state": _safe_text(
                transaction.get("state")
            ),
            "controlled_apply_present": bool(
                controlled_apply
            ),
            "executor_contract_present": bool(
                executor_contract
            ),
            "replay_safe": True,
            "hydration_allowed": True,
            "filesystem_write_allowed": False,
        }
    )


def summarize_runtime_repair_transaction_snapshot(
    snapshot: Any,
) -> Dict[str, Any]:
    safe = (
        snapshot
        if isinstance(
            snapshot,
            Mapping,
        )
        else {}
    )

    return freeze_runtime_export(
        {
            "snapshot_id": _safe_text(
                safe.get(
                    "snapshot_id"
                )
            ),
            "transaction_id": _safe_text(
                safe.get(
                    "transaction_id"
                )
            ),
            "task_id": _safe_text(
                safe.get(
                    "task_id"
                )
            ),
            "proposal_id": _safe_text(
                safe.get(
                    "proposal_id"
                )
            ),
            "transaction_state": _safe_text(
                safe.get(
                    "transaction_state"
                )
            ),
            "replay_safe": bool(
                safe.get(
                    "replay_safe"
                )
            ),
            "filesystem_persisted": bool(
                safe.get(
                    "filesystem_persisted"
                )
            ),
        }
    )


def build_runtime_repair_snapshot_summary(
    transaction: Mapping[str, Any],
) -> str:
    state = _safe_text(
        transaction.get("state")
    ) or "unknown"

    tx_id = _safe_text(
        transaction.get(
            "transaction_id"
        )
    ) or "unknown_transaction"

    return (
        f"Runtime repair snapshot created "
        f"for transaction {tx_id} "
        f"in state {state}."
    )


def _build_snapshot_id(
    snapshot: Mapping[str, Any],
) -> str:
    payload = {
        "transaction_id": (
            snapshot.get(
                "transaction_id"
            )
        ),
        "task_id": (
            snapshot.get(
                "task_id"
            )
        ),
        "proposal_id": (
            snapshot.get(
                "proposal_id"
            )
        ),
        "transaction_state": (
            snapshot.get(
                "transaction_state"
            )
        ),
    }

    encoded = json.dumps(
        make_json_safe(payload),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    digest = hashlib.sha1(
        encoded.encode("utf-8")
    ).hexdigest()[:12]

    transaction_id = _safe_text(
        snapshot.get(
            "transaction_id"
        )
    ) or "unknown"

    return (
        f"runtime_snapshot:"
        f"{transaction_id}:"
        f"{digest}"
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()