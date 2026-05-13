from __future__ import annotations

import copy
import json
from typing import Any

from core.runtime.execution_audit import ExecutionAuditRecord
from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot
from core.runtime.execution_replay import ExecutionReplayRecord
from core.runtime.rollback_verification import RollbackVerificationRecord
from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle


class RuntimeEvidenceSerializationRejected(RuntimeError):
    pass


class RuntimeEvidenceSerializer:
    SCHEMA_VERSION = "runtime_evidence_bundle.v1"

    def serialize_bundle(self, bundle: RuntimeEvidenceBundle) -> str:
        payload = self._bundle_to_payload(bundle)
        return self._canonical_json(payload)

    def deserialize_bundle(self, payload: str | dict[str, Any]) -> RuntimeEvidenceBundle:
        data = self._load_payload(payload)
        self._require_top_level(data)

        snapshot = self._snapshot_from_payload(data["snapshot"])
        replay_record = self._replay_from_payload(data["replay"])
        audit_record = self._audit_from_payload(data["audit"])
        rollback_record = self._rollback_from_payload(data["rollback_verification"])
        bundle_payload = data["bundle"]

        bundle = RuntimeEvidenceBundle(
            bundle_payload["bundle_id"],
            snapshot,
            replay_record,
            audit_record,
            rollback_record,
            metadata=bundle_payload.get("metadata"),
            runtime_args=bundle_payload.get("runtime_args"),
            created_at=None,
        )

        self._validate_identity_payload(data, bundle)
        self._validate_fingerprint(
            "snapshot",
            data["fingerprints"]["snapshot"],
            snapshot.fingerprint,
        )
        self._validate_fingerprint(
            "replay",
            data["fingerprints"]["replay"],
            replay_record.fingerprint,
        )
        self._validate_fingerprint(
            "audit",
            data["fingerprints"]["audit"],
            audit_record.fingerprint,
        )
        self._validate_fingerprint(
            "rollback",
            data["fingerprints"]["rollback"],
            rollback_record.fingerprint,
        )
        self._validate_fingerprint(
            "bundle",
            data["fingerprints"]["bundle"],
            bundle.fingerprint,
        )

        return bundle

    def _bundle_to_payload(self, bundle: RuntimeEvidenceBundle) -> dict[str, Any]:
        snapshot = bundle.snapshot
        replay_record = bundle.replay_record
        audit_record = bundle.audit_record
        rollback_record = bundle.rollback_record
        return {
            "schema_version": self.SCHEMA_VERSION,
            "bundle": {
                "bundle_id": bundle.bundle_id,
                "plan_id": bundle.plan_id,
                "snapshot_id": bundle.snapshot_id,
                "aggregate_status": bundle.aggregate_status,
                "metadata": bundle.metadata,
                "runtime_args": bundle.runtime_args,
            },
            "snapshot": self._snapshot_payload(snapshot),
            "replay": self._replay_payload(replay_record),
            "audit": self._audit_payload(audit_record),
            "rollback_verification": self._rollback_payload(rollback_record),
            "fingerprints": {
                "bundle": bundle.fingerprint,
                "snapshot": snapshot.fingerprint,
                "replay": replay_record.fingerprint,
                "audit": audit_record.fingerprint,
                "rollback": rollback_record.fingerprint,
            },
        }

    def _snapshot_payload(self, snapshot: ExecutionPlanSnapshot) -> dict[str, Any]:
        return {
            "snapshot_id": snapshot.snapshot_id,
            "plan_id": snapshot.plan_id,
            "plan_fingerprint": snapshot.plan_fingerprint,
            "execution_order": snapshot.execution_order,
            "operation_fingerprints": snapshot.operation_fingerprints,
            "aggregate_status": snapshot.status,
            "metadata": snapshot.metadata,
            "runtime_args": snapshot.runtime_args,
            "fingerprint": snapshot.fingerprint,
        }

    def _replay_payload(self, record: ExecutionReplayRecord) -> dict[str, Any]:
        return {
            "replay_id": record.replay_id,
            "snapshot_id": record.snapshot_id,
            "plan_id": record.plan_id,
            "snapshot_fingerprint": record.snapshot_fingerprint,
            "plan_fingerprint": record.plan_fingerprint,
            "replay_execution_order": record.replay_execution_order,
            "operation_fingerprints": record.operation_fingerprints,
            "aggregate_status": record.aggregate_status,
            "verification_result": record.verification_result,
            "mismatches": record.mismatches,
            "fingerprint": record.fingerprint,
        }

    def _audit_payload(self, record: ExecutionAuditRecord) -> dict[str, Any]:
        return {
            "audit_id": record.audit_id,
            "replay_id": record.replay_id,
            "snapshot_id": record.snapshot_id,
            "plan_id": record.plan_id,
            "verification_result": record.verification_result,
            "mismatches": record.mismatches,
            "replay_fingerprint": record.replay_fingerprint,
            "aggregate_status": record.aggregate_status,
            "execution_order": record.execution_order,
            "operation_fingerprints": record.operation_fingerprints,
            "metadata": record.metadata,
            "runtime_args": record.runtime_args,
            "fingerprint": record.fingerprint,
        }

    def _rollback_payload(self, record: RollbackVerificationRecord) -> dict[str, Any]:
        return {
            "rollback_id": record.rollback_id,
            "snapshot_id": record.snapshot_id,
            "plan_id": record.plan_id,
            "execution_order": record.execution_order,
            "rollback_order": record.rollback_order,
            "verification_result": record.verification_result,
            "mismatches": record.mismatches,
            "snapshot_fingerprint": record.snapshot_fingerprint,
            "aggregate_status": record.aggregate_status,
            "operation_fingerprints": record.operation_fingerprints,
            "metadata": record.metadata,
            "runtime_args": record.runtime_args,
            "fingerprint": record.fingerprint,
        }

    def _snapshot_from_payload(self, payload: dict[str, Any]) -> ExecutionPlanSnapshot:
        self._require_fields(
            "snapshot",
            payload,
            [
                "snapshot_id",
                "plan_id",
                "plan_fingerprint",
                "execution_order",
                "operation_fingerprints",
                "aggregate_status",
                "metadata",
                "runtime_args",
                "fingerprint",
            ],
        )
        snapshot = object.__new__(ExecutionPlanSnapshot)
        snapshot._snapshot_id = payload["snapshot_id"]
        snapshot._plan_id = payload["plan_id"]
        snapshot._plan_fingerprint = payload["plan_fingerprint"]
        snapshot._execution_order = list(payload["execution_order"])
        snapshot._operation_fingerprints = copy.deepcopy(payload["operation_fingerprints"])
        snapshot._status = payload["aggregate_status"]
        snapshot._metadata = copy.deepcopy(payload["metadata"])
        snapshot._runtime_args = copy.deepcopy(payload["runtime_args"])
        snapshot._created_at = None
        self._validate_fingerprint("snapshot", payload["fingerprint"], snapshot.fingerprint)
        return snapshot

    def _replay_from_payload(self, payload: dict[str, Any]) -> ExecutionReplayRecord:
        self._require_fields(
            "replay",
            payload,
            [
                "replay_id",
                "snapshot_id",
                "plan_id",
                "snapshot_fingerprint",
                "plan_fingerprint",
                "replay_execution_order",
                "operation_fingerprints",
                "aggregate_status",
                "verification_result",
                "mismatches",
                "fingerprint",
            ],
        )
        record = ExecutionReplayRecord(
            replay_id=payload["replay_id"],
            snapshot_id=payload["snapshot_id"],
            plan_id=payload["plan_id"],
            snapshot_fingerprint=payload["snapshot_fingerprint"],
            plan_fingerprint=payload["plan_fingerprint"],
            replay_execution_order=payload["replay_execution_order"],
            operation_fingerprints=payload["operation_fingerprints"],
            aggregate_status=payload["aggregate_status"],
            verification_result=payload["verification_result"],
            mismatches=payload["mismatches"],
        )
        self._validate_fingerprint("replay", payload["fingerprint"], record.fingerprint)
        return record

    def _audit_from_payload(self, payload: dict[str, Any]) -> ExecutionAuditRecord:
        self._require_fields(
            "audit",
            payload,
            [
                "audit_id",
                "replay_id",
                "snapshot_id",
                "plan_id",
                "verification_result",
                "mismatches",
                "replay_fingerprint",
                "aggregate_status",
                "execution_order",
                "operation_fingerprints",
                "metadata",
                "runtime_args",
                "fingerprint",
            ],
        )
        record = ExecutionAuditRecord(
            audit_id=payload["audit_id"],
            replay_id=payload["replay_id"],
            snapshot_id=payload["snapshot_id"],
            plan_id=payload["plan_id"],
            verification_result=payload["verification_result"],
            mismatches=payload["mismatches"],
            replay_fingerprint=payload["replay_fingerprint"],
            aggregate_status=payload["aggregate_status"],
            execution_order=payload["execution_order"],
            operation_fingerprints=payload["operation_fingerprints"],
            metadata=payload["metadata"],
            runtime_args=payload["runtime_args"],
        )
        self._validate_fingerprint("audit", payload["fingerprint"], record.fingerprint)
        return record

    def _rollback_from_payload(
        self,
        payload: dict[str, Any],
    ) -> RollbackVerificationRecord:
        self._require_fields(
            "rollback_verification",
            payload,
            [
                "rollback_id",
                "snapshot_id",
                "plan_id",
                "execution_order",
                "rollback_order",
                "verification_result",
                "mismatches",
                "snapshot_fingerprint",
                "aggregate_status",
                "operation_fingerprints",
                "metadata",
                "runtime_args",
                "fingerprint",
            ],
        )
        record = RollbackVerificationRecord(
            rollback_id=payload["rollback_id"],
            snapshot_id=payload["snapshot_id"],
            plan_id=payload["plan_id"],
            execution_order=payload["execution_order"],
            rollback_order=payload["rollback_order"],
            verification_result=payload["verification_result"],
            mismatches=payload["mismatches"],
            snapshot_fingerprint=payload["snapshot_fingerprint"],
            aggregate_status=payload["aggregate_status"],
            operation_fingerprints=payload["operation_fingerprints"],
            metadata=payload["metadata"],
            runtime_args=payload["runtime_args"],
        )
        self._validate_fingerprint(
            "rollback_verification",
            payload["fingerprint"],
            record.fingerprint,
        )
        return record

    def _load_payload(self, payload: str | dict[str, Any]) -> dict[str, Any]:
        try:
            if isinstance(payload, str):
                data = json.loads(payload)
            elif isinstance(payload, dict):
                data = copy.deepcopy(payload)
            else:
                raise TypeError("payload must be a canonical JSON string or dict")
            return json.loads(self._canonical_json(data))
        except Exception as exc:
            raise RuntimeEvidenceSerializationRejected(
                "runtime evidence serialization payload is invalid"
            ) from exc

    def _require_top_level(self, payload: dict[str, Any]) -> None:
        self._require_fields(
            "payload",
            payload,
            [
                "schema_version",
                "bundle",
                "snapshot",
                "replay",
                "audit",
                "rollback_verification",
                "fingerprints",
            ],
        )
        if payload["schema_version"] != self.SCHEMA_VERSION:
            raise RuntimeEvidenceSerializationRejected(
                "runtime evidence serialization schema_version mismatch"
            )
        self._require_fields(
            "bundle",
            payload["bundle"],
            [
                "bundle_id",
                "plan_id",
                "snapshot_id",
                "aggregate_status",
                "metadata",
                "runtime_args",
            ],
        )
        self._require_fields(
            "fingerprints",
            payload["fingerprints"],
            ["bundle", "snapshot", "replay", "audit", "rollback"],
        )

    def _validate_identity_payload(
        self,
        payload: dict[str, Any],
        bundle: RuntimeEvidenceBundle,
    ) -> None:
        bundle_payload = payload["bundle"]
        if (
            bundle_payload["bundle_id"] != bundle.bundle_id
            or bundle_payload["plan_id"] != bundle.plan_id
            or bundle_payload["snapshot_id"] != bundle.snapshot_id
            or bundle_payload["aggregate_status"] != bundle.aggregate_status
        ):
            raise RuntimeEvidenceSerializationRejected(
                "runtime evidence serialization bundle identity mismatch"
            )

    def _validate_fingerprint(
        self,
        label: str,
        expected: str,
        actual: str,
    ) -> None:
        if expected != actual:
            raise RuntimeEvidenceSerializationRejected(
                f"runtime evidence serialization {label} fingerprint mismatch"
            )

    def _require_fields(
        self,
        label: str,
        payload: dict[str, Any],
        fields: list[str],
    ) -> None:
        if not isinstance(payload, dict):
            raise RuntimeEvidenceSerializationRejected(
                f"runtime evidence serialization {label} must be an object"
            )
        missing = [
            field
            for field in fields
            if field not in payload
        ]
        if missing:
            raise RuntimeEvidenceSerializationRejected(
                f"runtime evidence serialization {label} missing fields: {missing!r}"
            )

    def _canonical_json(self, payload: Any) -> str:
        return json.dumps(
            payload,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
