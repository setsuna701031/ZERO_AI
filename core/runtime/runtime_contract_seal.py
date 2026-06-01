from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_evidence_surface import list_evidence


RUNTIME_CONTRACT_SEAL_SCHEMA = "runtime_contract_seal.v1"

REQUIRED_CONTRACT_CHAINS = (
    "runtime_ownership",
    "runtime_execution_authority",
    "recovery_report",
    "runtime_transition",
    "mutation_audit",
)


@dataclass(frozen=True)
class RuntimeContractSealReport:
    task_id: str
    sealed: bool
    status: str
    reason: str
    ownership_status: dict[str, Any]
    execution_authority_status: dict[str, Any]
    recovery_evidence_status: dict[str, Any]
    transition_evidence_status: dict[str, Any]
    mutation_evidence_status: dict[str, Any]
    evidence_registry_status: dict[str, Any]
    missing_chains: tuple[str, ...] = ()
    schema: str = RUNTIME_CONTRACT_SEAL_SCHEMA
    fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", _fingerprint(self._payload(include_fingerprint=False)))

    def to_dict(self) -> dict[str, Any]:
        return self._payload(include_fingerprint=True)

    def _payload(self, *, include_fingerprint: bool) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "task_id": self.task_id,
            "sealed": self.sealed,
            "status": self.status,
            "reason": self.reason,
            "ownership_status": copy.deepcopy(self.ownership_status),
            "execution_authority_status": copy.deepcopy(self.execution_authority_status),
            "recovery_evidence_status": copy.deepcopy(self.recovery_evidence_status),
            "transition_evidence_status": copy.deepcopy(self.transition_evidence_status),
            "mutation_evidence_status": copy.deepcopy(self.mutation_evidence_status),
            "evidence_registry_status": copy.deepcopy(self.evidence_registry_status),
            "missing_chains": list(self.missing_chains),
            "metadata": copy.deepcopy(self.metadata),
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
        return payload


def build_runtime_contract_seal(
    *,
    task_id: str,
    repo_root: Any | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RuntimeContractSealReport:
    evidence_items = list_evidence(task_id, repo_root=repo_root)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for item in evidence_items:
        evidence_type = str(item.get("evidence_type") or "").strip()
        if not evidence_type:
            continue
        by_type.setdefault(evidence_type, []).append(copy.deepcopy(item))

    chain_status = {
        evidence_type: _chain_status(evidence_type, by_type.get(evidence_type, []))
        for evidence_type in REQUIRED_CONTRACT_CHAINS
    }
    missing = tuple(
        evidence_type
        for evidence_type, status in chain_status.items()
        if not bool(status.get("present"))
    )
    registry_status = {
        "schema": "runtime_contract_evidence_registry_status.v1",
        "ok": not missing,
        "task_id": str(task_id or ""),
        "evidence_count": len(evidence_items),
        "required_evidence_types": list(REQUIRED_CONTRACT_CHAINS),
        "present_evidence_types": sorted(by_type),
        "missing_evidence_types": list(missing),
    }
    sealed = not missing
    return RuntimeContractSealReport(
        task_id=str(task_id or ""),
        sealed=sealed,
        status="sealed" if sealed else "failed",
        reason="runtime_contract_seal_complete" if sealed else "runtime_contract_missing_required_chain",
        ownership_status=chain_status["runtime_ownership"],
        execution_authority_status=chain_status["runtime_execution_authority"],
        recovery_evidence_status=chain_status["recovery_report"],
        transition_evidence_status=chain_status["runtime_transition"],
        mutation_evidence_status=chain_status["mutation_audit"],
        evidence_registry_status=registry_status,
        missing_chains=missing,
        metadata={
            **copy.deepcopy(dict(metadata or {})),
            "no_execution_performed": True,
            "seal_only": True,
        },
    )


def _chain_status(evidence_type: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "runtime_contract_chain_status.v1",
        "evidence_type": evidence_type,
        "present": bool(items),
        "status": "present" if items else "missing",
        "count": len(items),
        "items": copy.deepcopy(items),
    }


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "REQUIRED_CONTRACT_CHAINS",
    "RUNTIME_CONTRACT_SEAL_SCHEMA",
    "RuntimeContractSealReport",
    "build_runtime_contract_seal",
]
