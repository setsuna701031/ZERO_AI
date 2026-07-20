from __future__ import annotations
from types import MappingProxyType
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import fingerprint

REFERENCE_SCHEMA = "zero.engineering.task_artifact_reference.v1"
LINKAGE_KEYS = (
    "repository_identity","task_identity","proposal_identity","approval_identity",
    "authorization_identity","scope_identity","preparation_identity","token_identity",
    "transaction_identity","execution_result_identity","closure_identity",
)

def build_artifact_reference(*, phase: str, schema: str, artifact_identity: str, artifact_fingerprint: str,
                             adapter_id: str, adapter_version: str, validation_level: str,
                             validation_status: str, linkage: Mapping[str, Any] | None = None,
                             bounded_summary: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    body: dict[str, Any] = {
        "schema": REFERENCE_SCHEMA,
        "phase": phase,
        "artifact_schema": schema,
        "artifact_identity": artifact_identity,
        "artifact_fingerprint": artifact_fingerprint,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "validation_level": validation_level,
        "validation_status": validation_status,
        "bounded_summary": dict(bounded_summary or {}),
        "immutable": True,
    }
    for key in LINKAGE_KEYS:
        value = (linkage or {}).get(key)
        if value is not None:
            body[key] = value
    ref_fp = fingerprint(body)
    body["reference_id"] = "engineering-task-artifact-reference-" + ref_fp[:24]
    body["reference_fingerprint"] = fingerprint(body)
    return MappingProxyType(body)

def mutable_reference(ref: Mapping[str, Any]) -> dict[str, Any]:
    return dict(ref)

__all__ = ["REFERENCE_SCHEMA", "LINKAGE_KEYS", "build_artifact_reference", "mutable_reference"]
