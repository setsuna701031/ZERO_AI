from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any
from pathlib import Path

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

# ---------------------------------------------------------------------------
# Runtime Transition Constitution Sync v1 compatibility layer
# ---------------------------------------------------------------------------
#
# Keep the historical transition evidence helpers above intact. The v1
# canonical evidence wrapper below adds a shared schema surface without removing
# build_transition_evidence(...), transition_evidence_payload(...), or the
# existing lineage helpers used by older runtime paths.

from dataclasses import dataclass, field

from core.runtime.runtime_evidence_surface import register_evidence
from core.runtime.runtime_transition_record import (
    RUNTIME_TRANSITION_RECORD_SCHEMA,
    RuntimeTransitionRecord,
)


RUNTIME_TRANSITION_EVIDENCE_SCHEMA = "runtime_transition_evidence.v1"


@dataclass(frozen=True)
class RuntimeTransitionEvidence:
    evidence_id: str
    transition_id: str
    source: str
    schema: str = RUNTIME_TRANSITION_EVIDENCE_SCHEMA
    record_schema: str = RUNTIME_TRANSITION_RECORD_SCHEMA
    allowed: bool = False
    blocked: bool | None = None
    guard_ok: bool | None = None
    reason: str = ""
    status: str = ""
    from_state: str = ""
    to_state: str = ""
    canonical_from_status: str = ""
    canonical_to_status: str = ""
    enforcement_mode: str = ""
    enforcement_classification: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        evidence_id = _text(self.evidence_id)
        transition_id = _text(self.transition_id)
        source = _text(self.source)

        if not evidence_id:
            raise ValueError("evidence_id is required")
        if not transition_id:
            raise ValueError("transition_id is required")
        if not source:
            raise ValueError("source is required")

        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "transition_id", transition_id)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "reason", _text(self.reason))
        object.__setattr__(self, "status", _text(self.status))
        object.__setattr__(self, "from_state", _text(self.from_state))
        object.__setattr__(self, "to_state", _text(self.to_state))
        object.__setattr__(self, "canonical_from_status", _text(self.canonical_from_status))
        object.__setattr__(self, "canonical_to_status", _text(self.canonical_to_status))
        object.__setattr__(self, "enforcement_mode", _text(self.enforcement_mode))
        object.__setattr__(self, "enforcement_classification", _text(self.enforcement_classification))
        object.__setattr__(self, "metadata", copy.deepcopy(dict(self.metadata or {})))
        object.__setattr__(self, "evidence", copy.deepcopy(dict(self.evidence or {})))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_id": self.evidence_id,
            "transition_id": self.transition_id,
            "source": self.source,
            "record_schema": self.record_schema,
            "allowed": self.allowed,
            "blocked": self.blocked,
            "guard_ok": self.guard_ok,
            "reason": self.reason,
            "status": self.status,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "canonical_from_status": self.canonical_from_status,
            "canonical_to_status": self.canonical_to_status,
            "enforcement_mode": self.enforcement_mode,
            "enforcement_classification": self.enforcement_classification,
            "metadata": copy.deepcopy(self.metadata),
            "evidence": copy.deepcopy(self.evidence),
        }


def build_runtime_transition_evidence(
    record: RuntimeTransitionRecord | dict[str, Any],
    *,
    evidence_id: str | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransitionEvidence:
    transition_record = (
        record
        if isinstance(record, RuntimeTransitionRecord)
        else RuntimeTransitionRecord.from_mapping(record)
    )

    merged_metadata = {
        **copy.deepcopy(transition_record.metadata),
        **copy.deepcopy(dict(metadata or {})),
    }

    return RuntimeTransitionEvidence(
        evidence_id=evidence_id or f"{transition_record.transition_id}:evidence",
        transition_id=transition_record.transition_id,
        source=source or transition_record.source,
        allowed=transition_record.allowed,
        blocked=transition_record.blocked,
        guard_ok=transition_record.guard_ok,
        reason=transition_record.reason,
        status=transition_record.status,
        from_state=transition_record.from_state,
        to_state=transition_record.to_state,
        canonical_from_status=transition_record.canonical_from_status,
        canonical_to_status=transition_record.canonical_to_status,
        enforcement_mode=transition_record.enforcement_mode,
        enforcement_classification=transition_record.enforcement_classification,
        metadata=merged_metadata,
        evidence={
            **copy.deepcopy(transition_record.evidence),
            "transition_record": transition_record.to_dict(),
        },
    )


def export_runtime_transition_evidence(
    *,
    repo_root: Path | str,
    task_id: str,
    transition_evidence: RuntimeTransitionEvidence | dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export and index runtime transition evidence.

    This is an evidence-surface integration point only. It does not create,
    approve, reject, or execute transitions.
    """
    payload = (
        transition_evidence.to_dict()
        if isinstance(transition_evidence, RuntimeTransitionEvidence)
        else copy.deepcopy(transition_evidence if isinstance(transition_evidence, dict) else {})
    )
    if not payload:
        return {}

    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "runtime_transition_task"
    evidence_id = _text(payload.get("evidence_id") or payload.get("transition_id")) or "transition"
    safe_evidence_id = _safe_filename(evidence_id) or "transition"
    evidence_dir = root / "workspace" / "evidence" / "runtime_transition"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{safe_task_id}_{safe_evidence_id}_runtime_transition_evidence.json"

    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    surface_metadata = {
        "artifact_path": str(evidence_path),
        "evidence_path": str(evidence_path),
        "schema": _text(payload.get("schema")) or RUNTIME_TRANSITION_EVIDENCE_SCHEMA,
        "transition_id": _text(payload.get("transition_id")),
        "evidence_id": _text(payload.get("evidence_id")),
    }
    if isinstance(metadata, dict):
        surface_metadata.update(copy.deepcopy(metadata))

    register_evidence(
        task_id,
        "runtime_transition",
        evidence_path,
        surface_metadata,
        repo_root=root,
    )

    return {
        "evidence_type": "runtime_transition",
        "evidence_path": str(evidence_path),
        "artifact_path": str(evidence_path),
        "schema": surface_metadata["schema"],
        "payload": copy.deepcopy(payload),
    }


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._-")[:120]


def runtime_transition_evidence_from_legacy_metadata(
    metadata: dict[str, Any],
    *,
    evidence_id: str,
    transition_id: str,
    source: str,
) -> RuntimeTransitionEvidence:
    payload = copy.deepcopy(dict(metadata or {}))
    return RuntimeTransitionEvidence(
        evidence_id=evidence_id,
        transition_id=transition_id,
        source=source,
        allowed=bool(payload.get("transition_allowed", payload.get("allowed", False))),
        blocked=payload.get("blocked"),
        guard_ok=(
            payload.get("runtime_transition_guard", {}).get("ok")
            if isinstance(payload.get("runtime_transition_guard"), dict)
            else None
        ),
        reason=payload.get("transition_reason") or payload.get("reason") or "legacy_transition_metadata",
        status=payload.get("status") or payload.get("canonical_status") or "unknown",
        from_state=payload.get("from_state") or payload.get("lifecycle_from_state") or "",
        to_state=payload.get("to_state") or payload.get("lifecycle_to_state") or "",
        canonical_from_status=payload.get("canonical_from_status", ""),
        canonical_to_status=payload.get("canonical_to_status", ""),
        enforcement_mode=payload.get("enforcement_mode", ""),
        enforcement_classification=payload.get("enforcement_classification", ""),
        metadata=payload,
        evidence={"legacy_metadata": payload},
    )


# Backward-compatible alias for the generated v1 tests.
transition_evidence_from_legacy_metadata = runtime_transition_evidence_from_legacy_metadata
