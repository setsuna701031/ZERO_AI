from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle
from core.runtime.runtime_execution_result import RuntimeExecutionResult
from core.runtime.runtime_serialization import DEFAULT_RUNTIME_SERIALIZER, RuntimeSerializationAuthority
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION
from core.runtime.runtime_authority_seal import (
    _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN,
    register_runtime_evidence_authority,
)
from core.runtime.runtime_execution_authority import (
    assert_runtime_capability_consistency,
    propagate_runtime_capability,
    validate_capability_provenance,
)
from core.goals.goal_lineage_contract import (
    attach_runtime_identity_graph,
    bind_runtime_identity_graph,
    canonical_runtime_identity_graph,
)

_COMPATIBILITY_KEYS = ("artifact_type", "compatible", "runtime_version", "abi_version", "reason", "migration_required", "metadata")


def _canonical_compatibility_reports(value: Any) -> list[dict[str, Any]]:
    reports = value if isinstance(value, list) else [value]
    canonical: list[dict[str, Any]] = []
    for report in reports:
        if hasattr(report, "to_dict"):
            item = report.to_dict()
        elif isinstance(report, dict) and "compatibility" in report and isinstance(report["compatibility"], dict):
            item = dict(report["compatibility"])
        elif isinstance(report, dict):
            item = dict(report)
        else:
            item = {"artifact_type": "runtime_artifact", "compatible": False, "reason": str(report)}
        if "compatible" not in item:
            item["compatible"] = bool(item.get("allowed", False))
        item.setdefault("artifact_type", "runtime_artifact")
        item.setdefault("runtime_version", RUNTIME_KERNEL_VERSION)
        item.setdefault("abi_version", RUNTIME_ABI_VERSION)
        item.setdefault("reason", "runtime_compatibility_report_canonicalized")
        item.setdefault("migration_required", False)
        item.setdefault("metadata", {})
        canonical.append({key: copy.deepcopy(item.get(key)) for key in _COMPATIBILITY_KEYS})
    return canonical


@dataclass(frozen=True)
class RuntimeEvidenceSnapshot:
    evidence_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_evidence_snapshot",
            "evidence_id": self.evidence_id,
            "payload": copy.deepcopy(self.payload),
        }


class RuntimeEvidenceAuthority:
    """Canonical authority for runtime evidence assembly.

    Preserve the Phase 6 evidence ABI: runtime_compatibility is always a list of
    reports with a top-level `compatible` key.  Do not allow wrapped gate reports
    to leak into this field.
    """

    def __init__(
        self,
        *,
        evidence_id: str,
        serializer: RuntimeSerializationAuthority | None = None,
        issuer_token: Any = None,
        capability_provenance: Any = None,
        identity_graph: Any = None,
    ) -> None:
        if issuer_token is not _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN:
            raise PermissionError("governed_runtime_evidence_owner_required")
        self.evidence_id = evidence_id
        self.serializer = serializer or DEFAULT_RUNTIME_SERIALIZER
        self._payload: dict[str, Any] = {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_evidence_authority",
            "evidence_id": evidence_id,
            "stdout": "",
            "stderr": "",
            "test_results": None,
            "mutation_summary": None,
            "verification_report": "",
            "runtime_traces": [],
            "impacted_plan": {},
            "rollback_snapshot": {},
            "runtime_state_transitions": [],
            "runtime_checkpoints": [],
            "runtime_events": [],
            "runtime_wal": {},
            "runtime_budgets": {},
            "runtime_memory_snapshots": [],
            "runtime_capability_graph": {},
            "runtime_intent_evaluation": None,
            "runtime_isolation_boundary": None,
            "runtime_mutation_sandbox": None,
            "runtime_verification_sandbox": None,
            "runtime_seals": [],
            "runtime_integrity": [],
            "runtime_compatibility": [],
            "runtime_abi": [],
            "recovery": {},
        }
        if capability_provenance is not None:
            self._payload.update(
                propagate_runtime_capability({}, capability_provenance, stage="evidence")
            )
        if identity_graph is not None:
            graph = bind_runtime_identity_graph(identity_graph, evidence_id=evidence_id)
            if capability_provenance is not None:
                provenance = validate_capability_provenance(capability_provenance)
                graph = bind_runtime_identity_graph(
                    graph,
                    execution_id=provenance.execution_id,
                    capability_id=provenance.capability_id,
                )
            self._payload = attach_runtime_identity_graph(self._payload, graph)
        register_runtime_evidence_authority(issuer_token, self)

    @property
    def runtime_capability_id(self) -> str:
        return str(self._payload.get("runtime_capability_id") or "")

    @property
    def runtime_authority_decision_id(self) -> str:
        return str(self._payload.get("runtime_authority_decision_id") or "")

    @property
    def runtime_identity_graph(self) -> dict[str, Any]:
        value = self._payload.get("runtime_identity_graph")
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def update(self, *, issuer_token: Any = None, **values: Any) -> "RuntimeEvidenceAuthority":
        if issuer_token is not _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN:
            raise PermissionError("governed_runtime_evidence_owner_required")
        if self._payload.get("runtime_capability_id"):
            protected = {
                "runtime_capability_id",
                "runtime_authority_decision_id",
                "runtime_capability_provenance",
                "runtime_identity_graph",
                "execution_id",
                "evidence_id",
            }
            for key in protected & values.keys():
                expected = self._payload.get(key)
                actual = values.get(key)
                if key == "runtime_capability_provenance":
                    assert_runtime_capability_consistency(expected, actual)
                elif key == "runtime_identity_graph":
                    if canonical_runtime_identity_graph(expected) != canonical_runtime_identity_graph(actual):
                        raise PermissionError("runtime_evidence_identity_override_forbidden")
                elif str(actual or "") != str(expected or ""):
                    raise PermissionError("runtime_evidence_capability_override_forbidden")
            for value in values.values():
                if isinstance(value, dict) and value.get("runtime_capability_id"):
                    assert_runtime_capability_consistency(self._payload, value)
        for key, value in values.items():
            if key == "runtime_compatibility":
                self._payload[key] = _canonical_compatibility_reports(value)
            else:
                self._payload[key] = copy.deepcopy(value)
        return self

    def append(self, key: str, value: Any, *, issuer_token: Any = None) -> "RuntimeEvidenceAuthority":
        if issuer_token is not _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN:
            raise PermissionError("governed_runtime_evidence_owner_required")
        if key == "runtime_compatibility":
            self._payload.setdefault(key, [])
            self._payload[key].extend(_canonical_compatibility_reports(value))
            return self
        current = self._payload.setdefault(key, [])
        if not isinstance(current, list):
            raise TypeError(f"runtime_evidence_field_not_list:{key}")
        current.append(copy.deepcopy(value))
        return self

    def merge_mapping(
        self,
        key: str,
        value: dict[str, Any],
        *,
        issuer_token: Any = None,
    ) -> "RuntimeEvidenceAuthority":
        if issuer_token is not _GOVERNED_RUNTIME_EVIDENCE_ISSUER_TOKEN:
            raise PermissionError("governed_runtime_evidence_owner_required")
        current = self._payload.setdefault(key, {})
        if not isinstance(current, dict):
            raise TypeError(f"runtime_evidence_field_not_mapping:{key}")
        current.update(copy.deepcopy(value))
        return self

    def snapshot(self) -> RuntimeEvidenceSnapshot:
        return RuntimeEvidenceSnapshot(self.evidence_id, self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = copy.deepcopy(self._payload)
        payload["runtime_compatibility"] = _canonical_compatibility_reports(payload.get("runtime_compatibility", []))
        return self.serializer.normalize(payload, artifact_type="runtime_evidence_authority")

    def to_bundle(
        self,
        *,
        bundle_id: str,
        execution_result: RuntimeExecutionResult,
    ) -> RuntimeEvidenceBundle:
        payload = self.to_dict()
        return RuntimeEvidenceBundle.from_runtime_execution(
            bundle_id=bundle_id,
            execution_result=execution_result,
            stdout=str(payload.get("stdout") or ""),
            stderr=str(payload.get("stderr") or ""),
            pytest_results=payload.get("test_results"),
            impacted_plan=payload.get("impacted_plan") or {},
            verification_traces=[payload.get("test_results") or {}],
            rollback_traces=[payload.get("rollback_snapshot") or {}],
            recovery_traces=[payload.get("recovery") or {}],
            replay_traces=[payload.get("runtime_replay") or {}],
            mutation_summaries=[payload.get("mutation_summary") or {}],
            runtime_state_transitions=payload.get("runtime_state_transitions") or [],
            metadata={
                "source": "runtime_evidence_authority",
                "runtime_wal": payload.get("runtime_wal") or {},
                "runtime_budgets": payload.get("runtime_budgets") or {},
                "runtime_memory_snapshots": payload.get("runtime_memory_snapshots") or [],
                "runtime_capability_graph": payload.get("runtime_capability_graph") or {},
                "runtime_intent_evaluation": payload.get("runtime_intent_evaluation") or {},
                "runtime_integrity": payload.get("runtime_integrity") or [],
                "runtime_compatibility": payload.get("runtime_compatibility") or [],
                "runtime_abi": payload.get("runtime_abi") or [],
                "runtime_seals": payload.get("runtime_seals") or [],
                "runtime_capability_id": payload.get("runtime_capability_id", ""),
                "runtime_authority_decision_id": payload.get("runtime_authority_decision_id", ""),
                "runtime_capability_provenance": payload.get("runtime_capability_provenance"),
                "runtime_capability_stage": payload.get("runtime_capability_stage", ""),
                "runtime_identity_graph": payload.get("runtime_identity_graph"),
                "execution_id": payload.get("execution_id", ""),
                "evidence_id": payload.get("evidence_id", ""),
            },
        )


__all__ = ["RuntimeEvidenceAuthority", "RuntimeEvidenceSnapshot"]
