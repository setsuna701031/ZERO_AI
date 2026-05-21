from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.runtime.runtime_version import RUNTIME_ABI_VERSION


@dataclass(frozen=True)
class RuntimeABIContract:
    name: str
    version: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()

    def validate(self, payload: dict[str, Any]) -> "RuntimeABIValidation":
        missing = tuple(field for field in self.required_fields if field not in payload)
        abi_version = str(payload.get("abi_version") or "")
        version_ok = abi_version == self.version
        return RuntimeABIValidation(
            contract_name=self.name,
            version=self.version,
            valid=not missing and version_ok,
            missing_fields=missing,
            reason=(
                "abi_contract_valid"
                if not missing and version_ok
                else ("abi_version_mismatch" if not version_ok else "abi_required_fields_missing")
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "required_fields": list(self.required_fields),
            "optional_fields": list(self.optional_fields),
        }


@dataclass(frozen=True)
class RuntimeABIValidation:
    contract_name: str
    version: str
    valid: bool
    missing_fields: tuple[str, ...] = ()
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": self.contract_name,
            "version": self.version,
            "valid": self.valid,
            "missing_fields": list(self.missing_fields),
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


ABI_CONTRACTS: dict[str, RuntimeABIContract] = {
    "runtime_event": RuntimeABIContract(
        "runtime_event",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "event_id", "event_type", "sequence", "timestamp", "payload", "metadata"),
    ),
    "runtime_state_transition": RuntimeABIContract(
        "runtime_state_transition",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "sequence", "old_state", "new_state", "reason", "created_at"),
    ),
    "runtime_evidence_bundle": RuntimeABIContract(
        "runtime_evidence_bundle",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "bundle_id", "created_at", "execution_result", "metadata", "runtime_seal"),
    ),
    "runtime_execution_result": RuntimeABIContract(
        "runtime_execution_result",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "execution_id", "execution_type", "status", "verified", "blocked", "evidence"),
    ),
    "runtime_wal_record": RuntimeABIContract(
        "runtime_wal_record",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "record_id", "sequence", "record_type", "timestamp", "payload", "metadata", "integrity_hash"),
    ),
    "runtime_replay_artifact": RuntimeABIContract(
        "runtime_replay_artifact",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "replay_id", "session_snapshot", "journal_records", "runtime_seal"),
    ),
    "runtime_transaction_coordinator": RuntimeABIContract(
        "runtime_transaction_coordinator",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "transactions", "snapshots"),
    ),
    "runtime_capability_graph": RuntimeABIContract(
        "runtime_capability_graph",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "nodes"),
    ),
    "runtime_intent_governance": RuntimeABIContract(
        "runtime_intent_governance",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "intent", "allowed", "risk", "reason"),
    ),
    "runtime_memory_snapshot": RuntimeABIContract(
        "runtime_memory_snapshot",
        RUNTIME_ABI_VERSION,
        ("abi_version", "runtime_version", "snapshot_id", "checkpoint_id", "state", "transactions", "fingerprint"),
    ),
}


def get_abi_contract(name: str) -> RuntimeABIContract:
    if name not in ABI_CONTRACTS:
        raise KeyError(f"runtime_abi_contract_unknown:{name}")
    return ABI_CONTRACTS[name]


def validate_abi(name: str, payload: dict[str, Any]) -> RuntimeABIValidation:
    return get_abi_contract(name).validate(payload)


def abi_manifest() -> dict[str, Any]:
    return {name: contract.to_dict() for name, contract in sorted(ABI_CONTRACTS.items())}


__all__ = [
    "ABI_CONTRACTS",
    "RuntimeABIContract",
    "RuntimeABIValidation",
    "abi_manifest",
    "get_abi_contract",
    "validate_abi",
]
