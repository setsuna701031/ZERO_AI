from __future__ import annotations

import hashlib
import json

from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_audit_artifact import (
    build_runtime_audit_artifact,
)
from core.tasks.runtime_audit_registry import (
    RuntimeAuditRegistry,
)
from core.tasks.runtime_state_hygiene import (
    freeze_runtime_export,
    make_json_safe,
)


RUNTIME_REPAIR_REVIEW_ARTIFACT_TYPE = (
    "runtime_repair_review_artifact"
)

RUNTIME_REPAIR_REVIEW_ARTIFACT_VERSION = (
    "runtime_repair_review_artifact.v1"
)


def build_runtime_repair_review_artifact(
    review: Any,
    *,
    review_action: Any = None,
) -> Dict[str, Any]:
    """Build a replayable audit artifact for a repair review lifecycle.

    This layer is read-only and side-effect free.
    It does not schedule tasks, execute tools, apply patches,
    mutate runtime state, or call planners.
    """
    safe_review = (
        review if isinstance(review, Mapping) else {}
    )

    safe_action = (
        review_action
        if isinstance(review_action, Mapping)
        else {}
    )

    preview = (
        safe_review.get("preview")
        if isinstance(
            safe_review.get("preview"),
            Mapping,
        )
        else {}
    )

    confirmation_gate = (
        safe_review.get("confirmation_gate")
        if isinstance(
            safe_review.get(
                "confirmation_gate"
            ),
            Mapping,
        )
        else {}
    )

    timeline = build_runtime_repair_review_timeline(
        safe_review,
        review_action=safe_action,
    )

    artifact = {
        "artifact_type": (
            RUNTIME_REPAIR_REVIEW_ARTIFACT_TYPE
        ),
        "artifact_version": (
            RUNTIME_REPAIR_REVIEW_ARTIFACT_VERSION
        ),
        "artifact_id": "",
        "transaction_id": _safe_text(
            safe_review.get(
                "transaction_id"
            )
        ),
        "task_id": _safe_text(
            safe_review.get(
                "task_id"
            )
        ),
        "proposal_id": _safe_text(
            safe_review.get(
                "proposal_id"
            )
        ),
        "review_state": _safe_text(
            safe_review.get(
                "review_state"
            )
        ),
        "risk_level": _safe_text(
            safe_review.get(
                "risk_level"
            )
        ),
        "confirmation_status": _safe_text(
            confirmation_gate.get(
                "confirmation_status"
            )
        ),
        "allowed_next_action": _safe_text(
            safe_review.get(
                "allowed_next_action"
            )
        ),
        "human_summary": _safe_text(
            safe_review.get(
                "human_summary"
            )
        ),
        "mutation_counts": (
            preview.get("mutation_counts")
            if isinstance(
                preview.get(
                    "mutation_counts"
                ),
                Mapping,
            )
            else {}
        ),
        "review_timeline": timeline,
        "review_action": (
            freeze_runtime_export(
                safe_action
            )
        ),
        "raw_review": freeze_runtime_export(
            safe_review
        ),
    }

    artifact["artifact_id"] = (
        _build_review_artifact_id(
            artifact
        )
    )

    return freeze_runtime_export(
        artifact
    )


def register_runtime_repair_review_artifact(
    review: Any,
    *,
    review_action: Any = None,
    audit_registry: Optional[
        RuntimeAuditRegistry
    ] = None,
) -> Dict[str, Any]:
    artifact = (
        build_runtime_repair_review_artifact(
            review,
            review_action=review_action,
        )
    )

    review_snapshot = {
        "task_id": artifact.get("task_id"),
        "status": artifact.get(
            "review_state"
        ),
        "goal": artifact.get(
            "human_summary"
        ),
        "review_timeline": artifact.get(
            "review_timeline"
        ),
        "review_artifact": artifact,
        "timeline": (
            artifact.get(
                "review_timeline"
            )
        ),
        "normalized_events": (
            artifact.get(
                "review_timeline"
            )
        ),
    }

    runtime_artifact = (
        build_runtime_audit_artifact(
            review_snapshot
        )
    )

    if audit_registry is not None:
        return (
            audit_registry
            .register_runtime_audit_artifact(
                runtime_artifact
            )
        )

    return runtime_artifact


def build_runtime_repair_review_timeline(
    review: Any,
    *,
    review_action: Any = None,
) -> List[Dict[str, Any]]:
    safe_review = (
        review if isinstance(review, Mapping) else {}
    )

    safe_action = (
        review_action
        if isinstance(review_action, Mapping)
        else {}
    )

    timeline: List[Dict[str, Any]] = []

    timeline.append(
        {
            "event_type": (
                "review_created"
            ),
            "review_state": _safe_text(
                safe_review.get(
                    "review_state"
                )
            ),
            "risk_level": _safe_text(
                safe_review.get(
                    "risk_level"
                )
            ),
            "summary": _safe_text(
                safe_review.get(
                    "human_summary"
                )
            ),
        }
    )

    action_type = _safe_text(
        safe_action.get(
            "review_action"
        )
    )

    if action_type:
        timeline.append(
            {
                "event_type": (
                    "review_action"
                ),
                "action": action_type,
                "review_state": _safe_text(
                    safe_action.get(
                        "review_state"
                    )
                ),
                "summary": _safe_text(
                    safe_action.get(
                        "human_summary"
                    )
                ),
            }
        )

    return timeline


def summarize_runtime_repair_review_artifact(
    artifact: Any,
) -> Dict[str, Any]:
    safe = (
        artifact if isinstance(artifact, Mapping)
        else {}
    )

    timeline = _safe_list_of_dicts(
        safe.get("review_timeline")
    )

    return freeze_runtime_export(
        {
            "artifact_id": _safe_text(
                safe.get(
                    "artifact_id"
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
            "review_state": _safe_text(
                safe.get(
                    "review_state"
                )
            ),
            "risk_level": _safe_text(
                safe.get(
                    "risk_level"
                )
            ),
            "timeline_event_count": (
                len(timeline)
            ),
            "human_summary": _safe_text(
                safe.get(
                    "human_summary"
                )
            ),
        }
    )


def _build_review_artifact_id(
    artifact: Mapping[str, Any],
) -> str:
    payload = {
        "transaction_id": artifact.get(
            "transaction_id"
        ),
        "task_id": artifact.get(
            "task_id"
        ),
        "proposal_id": artifact.get(
            "proposal_id"
        ),
        "review_state": artifact.get(
            "review_state"
        ),
        "risk_level": artifact.get(
            "risk_level"
        ),
        "allowed_next_action": (
            artifact.get(
                "allowed_next_action"
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
        artifact.get(
            "transaction_id"
        )
    ) or "unknown_transaction"

    review_state = _safe_text(
        artifact.get(
            "review_state"
        )
    ) or "unknown"

    return (
        f"runtime_review:"
        f"{transaction_id}:"
        f"{review_state}:"
        f"{digest}"
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _safe_list_of_dicts(
    value: Any,
) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    result: List[Dict[str, Any]] = []

    for item in value:
        if isinstance(item, Mapping):
            result.append(dict(item))

    return result