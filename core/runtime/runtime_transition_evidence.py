from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_status import normalize_runtime_status


def build_transition_evidence(
    from_status: Any,
    to_status: Any,
    *,
    trigger: str = "",
    source: str = "",
    reason: str = "",
    runtime_execution_result: Any = None,
    metadata: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = runtime_execution_result if isinstance(runtime_execution_result, dict) else {}
    merged_metadata = copy.deepcopy(metadata) if isinstance(metadata, dict) else {}
    merged_evidence = copy.deepcopy(evidence) if isinstance(evidence, dict) else {}
    inferred_reason = reason or transition_reason_from_execution_result(
        {
            **payload,
            "from_status": from_status,
            "to_status": to_status,
            "metadata": merged_metadata,
            "evidence": merged_evidence,
        }
    )
    inferred_trigger = trigger or transition_trigger_from_execution_result(payload) or _text(
        merged_metadata.get("trigger") or merged_metadata.get("action") or merged_metadata.get("phase")
    )
    inferred_source = source or transition_source_from_payload(
        {
            **payload,
            "metadata": merged_metadata,
            "evidence": merged_evidence,
        }
    )
    normalized_from = normalize_runtime_status(from_status)
    normalized_to = normalize_runtime_status(to_status)
    transition_evidence = {
        "transition_evidence_id": "",
        "from_status": normalized_from,
        "to_status": normalized_to,
        "trigger": inferred_trigger,
        "source": inferred_source,
        "reason": inferred_reason,
        "evidence_timestamp": _text(
            merged_metadata.get("timestamp")
            or merged_metadata.get("created_at")
            or merged_evidence.get("timestamp")
            or merged_evidence.get("created_at")
        ),
        "runtime_execution_result": copy.deepcopy(payload),
        "metadata": merged_metadata,
        "evidence": merged_evidence,
    }
    transition_evidence["transition_evidence_id"] = _transition_evidence_id(transition_evidence)
    return transition_evidence


def transition_evidence_payload(
    transition: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transition_payload = copy.deepcopy(transition) if isinstance(transition, dict) else {}
    transition_evidence = build_transition_evidence(
        transition_payload.get("from_status"),
        transition_payload.get("to_status"),
        trigger=_text(transition_payload.get("trigger")),
        source=_text(transition_payload.get("source")),
        reason=_text(transition_payload.get("reason")),
        runtime_execution_result=transition_payload.get("runtime_execution_result"),
        metadata=metadata if metadata is not None else transition_payload.get("metadata"),
        evidence=evidence if evidence is not None else transition_payload.get("evidence"),
    )
    return {
        **transition_payload,
        "transition_reason": transition_evidence["reason"],
        "transition_trigger": transition_evidence["trigger"],
        "transition_source": transition_evidence["source"],
        "transition_evidence": transition_evidence,
    }


def transition_reason_from_execution_result(payload: Any) -> str:
    data = payload if isinstance(payload, dict) else {}
    from_status = normalize_runtime_status(data.get("from_status"))
    to_status = normalize_runtime_status(data.get("to_status"))
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}

    explicit = _text(data.get("reason") or metadata.get("reason") or evidence.get("reason"))
    if explicit:
        return explicit

    if to_status == "running":
        return "runtime execution started"
    if to_status == "executed" and data.get("ok") is True:
        return "execution completed"
    if from_status == "executed" and to_status == "verifying":
        return "verification phase entered"
    if to_status == "verified" and data.get("verification_passed") is True:
        return "verification completed"
    if to_status == "failed":
        if data.get("verification_passed") is False:
            return "verification failure"
        return "execution failure"
    if to_status == "blocked":
        return "policy blocked / approval denied / governance rejection"
    if to_status in {"rolling_back", "rolled_back"}:
        return "rollback requested / rollback snapshot restore"
    if to_status in {"recovering", "recovered"}:
        return "runtime recovery reconstruction"
    if to_status in {"replaying", "replayed"}:
        return "runtime replay execution"
    if to_status == "sealed":
        return "freeze accepted / seal committed / runtime finalized"
    if data.get("blocked") is True:
        return "policy blocked / approval denied / governance rejection"
    if data.get("failed") is True:
        return "execution failure"
    if data.get("verification_passed") is True:
        return "verification completed"
    if data.get("ok") is True:
        return "execution completed"
    return "runtime transition recorded"


def transition_trigger_from_execution_result(payload: Any) -> str:
    data = payload if isinstance(payload, dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    if _text(metadata.get("trigger")):
        return _text(metadata.get("trigger"))
    if data.get("blocked") is True:
        return "governance"
    if data.get("failed") is True:
        return "failure"
    if data.get("verification_passed") is True:
        return "verification"
    if data.get("ok") is True or data.get("executed") is True:
        return "execution_result"
    return ""


def transition_source_from_payload(payload: Any) -> str:
    data = payload if isinstance(payload, dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    return _text(
        data.get("source")
        or metadata.get("source")
        or evidence.get("source")
        or "runtime"
    )


def transition_lineage_summary(payload: Any) -> dict[str, Any]:
    data = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    transition = build_transition_evidence(
        data.get("from_status") or data.get("canonical_from_status"),
        data.get("to_status") or data.get("canonical_to_status") or data.get("canonical_status"),
        trigger=_text(data.get("transition_trigger") or data.get("trigger")),
        source=_text(data.get("transition_source") or data.get("source")),
        reason=_text(data.get("transition_reason") or data.get("reason")),
        runtime_execution_result=data.get("runtime_execution_result"),
        metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        evidence=data.get("evidence") if isinstance(data.get("evidence"), dict) else None,
    )
    return {
        "canonical_status": data.get("canonical_status") or transition["to_status"],
        "transition_reason": transition["reason"],
        "transition_trigger": transition["trigger"],
        "transition_source": transition["source"],
        "transition_evidence": merge_transition_evidence(
            data.get("transition_evidence"),
            transition,
        ),
    }


def merge_transition_evidence(existing: Any, incoming: Any) -> dict[str, Any]:
    existing_payload = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    incoming_payload = copy.deepcopy(incoming) if isinstance(incoming, dict) else {}
    history = []
    if isinstance(existing_payload.get("history"), list):
        history.extend(copy.deepcopy(existing_payload.get("history")))
    elif existing_payload:
        history.append(copy.deepcopy(existing_payload))
    if incoming_payload:
        history.append(copy.deepcopy(incoming_payload))
    merged = {**existing_payload, **incoming_payload}
    if history:
        merged["history"] = history
    return merged


def _transition_evidence_id(payload: dict[str, Any]) -> str:
    seed = {
        key: value
        for key, value in payload.items()
        if key != "transition_evidence_id"
    }
    encoded = json.dumps(seed, sort_keys=True, default=str, separators=(",", ":"))
    return "transition-evidence-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _text(value: Any) -> str:
    return str(value or "").strip()
