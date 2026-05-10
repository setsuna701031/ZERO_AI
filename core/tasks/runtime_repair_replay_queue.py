from __future__ import annotations

import hashlib
import json

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_state_hygiene import (
    freeze_runtime_export,
    make_json_safe,
)


RUNTIME_REPAIR_REPLAY_QUEUE_TYPE = (
    "runtime_repair_replay_queue"
)

RUNTIME_REPAIR_REPLAY_QUEUE_VERSION = (
    "runtime_repair_replay_queue.v1"
)


def build_runtime_repair_replay_queue_item(
    snapshot: Any,
    *,
    parent_snapshot_id: Any = None,
) -> Dict[str, Any]:
    safe_snapshot = (
        snapshot
        if isinstance(snapshot, Mapping)
        else {}
    )

    snapshot_id = _safe_text(
        safe_snapshot.get(
            "snapshot_id"
        )
    )

    recovery_payload = (
        safe_snapshot.get(
            "recovery_payload"
        )
        if isinstance(
            safe_snapshot.get(
                "recovery_payload"
            ),
            Mapping,
        )
        else {}
    )

    hydration_contract = (
        safe_snapshot.get(
            "hydration_contract"
        )
        if isinstance(
            safe_snapshot.get(
                "hydration_contract"
            ),
            Mapping,
        )
        else {}
    )

    queue_item = {
        "queue_item_type": (
            "runtime_repair_replay_queue_item"
        ),
        "queue_item_id": "",
        "snapshot_id": snapshot_id,
        "parent_snapshot_id": _safe_text(
            parent_snapshot_id
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
        "transaction_state": _safe_text(
            safe_snapshot.get(
                "transaction_state"
            )
        ),
        "recovery_payload": (
            freeze_runtime_export(
                recovery_payload
            )
        ),
        "hydration_contract": (
            freeze_runtime_export(
                hydration_contract
            )
        ),
        "replay_safe": bool(
            safe_snapshot.get(
                "replay_safe"
            )
        ),
        "recovery_required": bool(
            recovery_payload.get(
                "recovery_required"
            )
        ),
        "continuation_allowed": bool(
            hydration_contract.get(
                "hydration_allowed"
            )
        ),
        "queue_status": "queued",
        "filesystem_recovery_required": False,
    }

    queue_item["queue_item_id"] = (
        _build_queue_item_id(
            queue_item
        )
    )

    return freeze_runtime_export(
        queue_item
    )


def build_runtime_repair_replay_chain(
    queue_items: Any,
) -> Dict[str, Any]:
    safe_items = (
        queue_items
        if isinstance(queue_items, list)
        else []
    )

    normalized: List[Dict[str, Any]] = []

    for item in safe_items:
        if not isinstance(
            item,
            Mapping,
        ):
            continue

        normalized.append(
            freeze_runtime_export(
                item
            )
        )

    chain = {
        "chain_type": (
            "runtime_repair_replay_chain"
        ),
        "chain_id": (
            _build_replay_chain_id(
                normalized
            )
        ),
        "queue_item_count": (
            len(normalized)
        ),
        "replay_safe": all(
            bool(
                x.get("replay_safe")
            )
            for x in normalized
        ),
        "continuation_allowed": all(
            bool(
                x.get(
                    "continuation_allowed"
                )
            )
            for x in normalized
        ),
        "queue_items": normalized,
    }

    return freeze_runtime_export(
        chain
    )


def build_runtime_repair_recovery_continuation_metadata(
    replay_chain: Any,
) -> Dict[str, Any]:
    safe_chain = (
        replay_chain
        if isinstance(
            replay_chain,
            Mapping,
        )
        else {}
    )

    queue_items = (
        safe_chain.get(
            "queue_items"
        )
        if isinstance(
            safe_chain.get(
                "queue_items"
            ),
            list,
        )
        else []
    )

    return freeze_runtime_export(
        {
            "metadata_type": (
                "runtime_repair_recovery_continuation_metadata"
            ),
            "chain_id": _safe_text(
                safe_chain.get(
                    "chain_id"
                )
            ),
            "queue_item_count": (
                len(queue_items)
            ),
            "continuation_allowed": bool(
                safe_chain.get(
                    "continuation_allowed"
                )
            ),
            "replay_safe": bool(
                safe_chain.get(
                    "replay_safe"
                )
            ),
            "scheduler_resume_allowed": False,
            "filesystem_resume_allowed": False,
            "human_summary": (
                "Replay continuation metadata prepared."
            ),
        }
    )


def summarize_runtime_repair_replay_queue(
    replay_chain: Any,
) -> Dict[str, Any]:
    safe_chain = (
        replay_chain
        if isinstance(
            replay_chain,
            Mapping,
        )
        else {}
    )

    return freeze_runtime_export(
        {
            "chain_id": _safe_text(
                safe_chain.get(
                    "chain_id"
                )
            ),
            "queue_item_count": int(
                safe_chain.get(
                    "queue_item_count",
                    0,
                )
            ),
            "replay_safe": bool(
                safe_chain.get(
                    "replay_safe"
                )
            ),
            "continuation_allowed": bool(
                safe_chain.get(
                    "continuation_allowed"
                )
            ),
        }
    )


def _build_queue_item_id(
    queue_item: Mapping[str, Any],
) -> str:
    payload = {
        "snapshot_id": (
            queue_item.get(
                "snapshot_id"
            )
        ),
        "transaction_id": (
            queue_item.get(
                "transaction_id"
            )
        ),
        "transaction_state": (
            queue_item.get(
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

    snapshot_id = _safe_text(
        queue_item.get(
            "snapshot_id"
        )
    ) or "unknown"

    return (
        f"runtime_replay_queue:"
        f"{snapshot_id}:"
        f"{digest}"
    )


def _build_replay_chain_id(
    queue_items: List[Mapping[str, Any]],
) -> str:
    payload = []

    for item in queue_items:
        payload.append(
            {
                "queue_item_id": (
                    item.get(
                        "queue_item_id"
                    )
                ),
                "snapshot_id": (
                    item.get(
                        "snapshot_id"
                    )
                ),
            }
        )

    encoded = json.dumps(
        make_json_safe(payload),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    digest = hashlib.sha1(
        encoded.encode("utf-8")
    ).hexdigest()[:12]

    return (
        f"runtime_replay_chain:{digest}"
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()