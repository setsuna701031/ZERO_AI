from __future__ import annotations

import hashlib
import json

from typing import Any, Dict, Mapping

from core.tasks.runtime_state_hygiene import (
    freeze_runtime_export,
    make_json_safe,
)


RUNTIME_REPAIR_PERSISTENCE_CONTRACT_TYPE = (
    "runtime_repair_persistence_contract"
)

RUNTIME_REPAIR_PERSISTENCE_CONTRACT_VERSION = (
    "runtime_repair_persistence_contract.v1"
)


def build_runtime_repair_persistence_contract(
    *,
    snapshot: Any,
    replay_chain: Any,
    governance_boundary: Any,
) -> Dict[str, Any]:
    safe_snapshot = (
        snapshot
        if isinstance(
            snapshot,
            Mapping,
        )
        else {}
    )

    safe_replay_chain = (
        replay_chain
        if isinstance(
            replay_chain,
            Mapping,
        )
        else {}
    )

    safe_boundary = (
        governance_boundary
        if isinstance(
            governance_boundary,
            Mapping,
        )
        else {}
    )

    snapshot_contract = (
        build_runtime_repair_snapshot_persistence_contract(
            safe_snapshot
        )
    )

    replay_contract = (
        build_runtime_repair_replay_persistence_contract(
            safe_replay_chain
        )
    )

    recovery_metadata = (
        build_runtime_repair_recovery_persistence_metadata(
            safe_snapshot,
            safe_replay_chain,
            safe_boundary,
        )
    )

    result = {
        "contract_type": (
            RUNTIME_REPAIR_PERSISTENCE_CONTRACT_TYPE
        ),
        "contract_version": (
            RUNTIME_REPAIR_PERSISTENCE_CONTRACT_VERSION
        ),
        "contract_id": (
            _build_persistence_contract_id(
                safe_snapshot,
                safe_replay_chain,
            )
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
        "snapshot_persistence_contract": (
            freeze_runtime_export(
                snapshot_contract
            )
        ),
        "replay_persistence_contract": (
            freeze_runtime_export(
                replay_contract
            )
        ),
        "recovery_persistence_metadata": (
            freeze_runtime_export(
                recovery_metadata
            )
        ),
        "journal_safe": True,
        "restoration_safe": True,
        "filesystem_write_allowed": False,
        "sqlite_allowed": False,
        "auto_restore_allowed": False,
        "human_summary": (
            "Persistence contract prepared."
        ),
    }

    return freeze_runtime_export(
        result
    )


def build_runtime_repair_snapshot_persistence_contract(
    snapshot: Mapping[str, Any],
) -> Dict[str, Any]:
    return freeze_runtime_export(
        {
            "contract_type": (
                "runtime_repair_snapshot_persistence_contract"
            ),
            "snapshot_id": _safe_text(
                snapshot.get(
                    "snapshot_id"
                )
            ),
            "transaction_id": _safe_text(
                snapshot.get(
                    "transaction_id"
                )
            ),
            "replay_safe": bool(
                snapshot.get(
                    "replay_safe"
                )
            ),
            "filesystem_persisted": False,
            "journal_safe": True,
        }
    )


def build_runtime_repair_replay_persistence_contract(
    replay_chain: Mapping[str, Any],
) -> Dict[str, Any]:
    return freeze_runtime_export(
        {
            "contract_type": (
                "runtime_repair_replay_persistence_contract"
            ),
            "chain_id": _safe_text(
                replay_chain.get(
                    "chain_id"
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
            "continuation_allowed": bool(
                replay_chain.get(
                    "continuation_allowed"
                )
            ),
            "scheduler_resume_allowed": False,
        }
    )


def build_runtime_repair_recovery_persistence_metadata(
    snapshot: Mapping[str, Any],
    replay_chain: Mapping[str, Any],
    governance_boundary: Mapping[str, Any],
) -> Dict[str, Any]:
    return freeze_runtime_export(
        {
            "metadata_type": (
                "runtime_repair_recovery_persistence_metadata"
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
            "transaction_id": _safe_text(
                snapshot.get(
                    "transaction_id"
                )
            ),
            "execution_allowed": bool(
                governance_boundary.get(
                    "execution_allowed"
                )
            ),
            "scheduler_resume_allowed": False,
            "filesystem_resume_allowed": False,
            "restoration_safe": True,
        }
    )


def summarize_runtime_repair_persistence_contract(
    contract: Any,
) -> Dict[str, Any]:
    safe_contract = (
        contract
        if isinstance(
            contract,
            Mapping,
        )
        else {}
    )

    return freeze_runtime_export(
        {
            "contract_id": _safe_text(
                safe_contract.get(
                    "contract_id"
                )
            ),
            "transaction_id": _safe_text(
                safe_contract.get(
                    "transaction_id"
                )
            ),
            "journal_safe": bool(
                safe_contract.get(
                    "journal_safe"
                )
            ),
            "restoration_safe": bool(
                safe_contract.get(
                    "restoration_safe"
                )
            ),
            "filesystem_write_allowed": bool(
                safe_contract.get(
                    "filesystem_write_allowed"
                )
            ),
        }
    )


def _build_persistence_contract_id(
    snapshot: Mapping[str, Any],
    replay_chain: Mapping[str, Any],
) -> str:
    payload = {
        "snapshot_id": (
            snapshot.get(
                "snapshot_id"
            )
        ),
        "chain_id": (
            replay_chain.get(
                "chain_id"
            )
        ),
        "transaction_id": (
            snapshot.get(
                "transaction_id"
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
        f"runtime_persistence:"
        f"{transaction_id}:"
        f"{digest}"
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()