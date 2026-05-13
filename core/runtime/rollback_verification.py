from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.runtime.execution_audit import ExecutionAuditRecord
from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot


class RollbackVerificationRejected(RuntimeError):
    pass


class RollbackVerificationRecord:
    def __init__(
        self,
        rollback_id: str,
        snapshot_id: str,
        plan_id: str,
        execution_order: list[str],
        rollback_order: list[str],
        verification_result: str,
        mismatches: list[dict[str, Any]] | None,
        snapshot_fingerprint: str,
        aggregate_status: str,
        operation_fingerprints: dict[str, str],
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._rollback_id = self._validate_text("rollback_id", rollback_id)
        self._snapshot_id = snapshot_id
        self._plan_id = plan_id
        self._execution_order = list(execution_order)
        self._rollback_order = list(rollback_order)
        self._verification_result = verification_result
        self._mismatches = copy.deepcopy(list(mismatches or []))
        self._snapshot_fingerprint = snapshot_fingerprint
        self._aggregate_status = aggregate_status
        self._operation_fingerprints = copy.deepcopy(operation_fingerprints)
        self._metadata = copy.deepcopy(metadata)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @property
    def rollback_id(self) -> str:
        return self._rollback_id

    @property
    def snapshot_id(self) -> str:
        return self._snapshot_id

    @property
    def plan_id(self) -> str:
        return self._plan_id

    @property
    def execution_order(self) -> list[str]:
        return list(self._execution_order)

    @property
    def rollback_order(self) -> list[str]:
        return list(self._rollback_order)

    @property
    def verification_result(self) -> str:
        return self._verification_result

    @property
    def mismatches(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._mismatches)

    @property
    def snapshot_fingerprint(self) -> str:
        return self._snapshot_fingerprint

    @property
    def aggregate_status(self) -> str:
        return self._aggregate_status

    @property
    def operation_fingerprints(self) -> dict[str, str]:
        return copy.deepcopy(self._operation_fingerprints)

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def created_at(self) -> str:
        return self._created_at

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self._fingerprint_payload(),
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _fingerprint_payload(self) -> dict[str, Any]:
        return {
            "rollback_id": self._rollback_id,
            "snapshot_id": self._snapshot_id,
            "plan_id": self._plan_id,
            "execution_order": self._execution_order,
            "rollback_order": self._rollback_order,
            "verification_result": self._verification_result,
            "mismatches": self._mismatches,
            "snapshot_fingerprint": self._snapshot_fingerprint,
            "aggregate_status": self._aggregate_status,
            "operation_fingerprints": self._operation_fingerprints,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RollbackVerificationRejected(
                f"rollback verification {field_name} is required"
            )

        return value


class RollbackVerificationVerifier:
    VERIFIED = "verified"
    MISMATCHED = "mismatched"

    def __init__(self, rollback_id: str) -> None:
        self.rollback_id = self._validate_text("rollback_id", rollback_id)

    def verify_snapshot_rollback(
        self,
        snapshot: ExecutionPlanSnapshot,
        created_at: str | None = None,
    ) -> RollbackVerificationRecord:
        rollback_order = self._expected_rollback_order(snapshot.execution_order)
        return self._build_record(
            rollback_id=self.rollback_id,
            rollback_order=rollback_order,
            snapshot=snapshot,
            mismatches=[],
            created_at=created_at,
        )

    def verify_order_against_snapshot(
        self,
        rollback_id: str,
        rollback_order: list[str],
        snapshot: ExecutionPlanSnapshot,
        created_at: str | None = None,
    ) -> RollbackVerificationRecord:
        rollback_id = self._validate_text("rollback_id", rollback_id)
        rollback_order = list(rollback_order)
        mismatches = self._collect_order_mismatches(
            rollback_order=rollback_order,
            snapshot=snapshot,
        )
        return self._build_record(
            rollback_id=rollback_id,
            rollback_order=rollback_order,
            snapshot=snapshot,
            mismatches=mismatches,
            created_at=created_at,
        )

    def verify_audit_against_snapshot(
        self,
        rollback_id: str,
        audit_record: ExecutionAuditRecord,
        snapshot: ExecutionPlanSnapshot,
        created_at: str | None = None,
    ) -> RollbackVerificationRecord:
        rollback_id = self._validate_text("rollback_id", rollback_id)
        rollback_order = self._expected_rollback_order(audit_record.execution_order)
        mismatches = self._collect_snapshot_identity_mismatches(
            audit_record=audit_record,
            snapshot=snapshot,
        )
        mismatches.extend(
            self._collect_order_mismatches(
                rollback_order=rollback_order,
                snapshot=snapshot,
            )
        )
        return self._build_record(
            rollback_id=rollback_id,
            rollback_order=rollback_order,
            snapshot=snapshot,
            mismatches=mismatches,
            created_at=created_at,
        )

    def _build_record(
        self,
        rollback_id: str,
        rollback_order: list[str],
        snapshot: ExecutionPlanSnapshot,
        mismatches: list[dict[str, Any]],
        created_at: str | None,
    ) -> RollbackVerificationRecord:
        return RollbackVerificationRecord(
            rollback_id=rollback_id,
            snapshot_id=snapshot.snapshot_id,
            plan_id=snapshot.plan_id,
            execution_order=snapshot.execution_order,
            rollback_order=rollback_order,
            verification_result=self.MISMATCHED if mismatches else self.VERIFIED,
            mismatches=mismatches,
            snapshot_fingerprint=snapshot.fingerprint,
            aggregate_status=snapshot.status,
            operation_fingerprints=snapshot.operation_fingerprints,
            metadata=snapshot.metadata,
            runtime_args=snapshot.runtime_args,
            created_at=created_at,
        )

    def _collect_order_mismatches(
        self,
        rollback_order: list[str],
        snapshot: ExecutionPlanSnapshot,
    ) -> list[dict[str, Any]]:
        mismatches: list[dict[str, Any]] = []
        expected_order = self._expected_rollback_order(snapshot.execution_order)
        expected_ids = set(snapshot.execution_order)
        actual_ids = set(rollback_order)

        if rollback_order != expected_order:
            mismatches.append(
                {
                    "type": "rollback_order_mismatch",
                    "expected": expected_order,
                    "actual": list(rollback_order),
                }
            )

        seen: set[str] = set()
        duplicates: list[str] = []
        for operation_id in rollback_order:
            if operation_id in seen and operation_id not in duplicates:
                duplicates.append(operation_id)
            seen.add(operation_id)

        for operation_id in duplicates:
            mismatches.append(
                {
                    "type": "duplicate_operation",
                    "operation_id": operation_id,
                    "expected": "single occurrence",
                    "actual": rollback_order.count(operation_id),
                }
            )
        for operation_id in sorted(expected_ids - actual_ids):
            mismatches.append(
                {
                    "type": "missing_operation",
                    "operation_id": operation_id,
                    "expected": operation_id,
                    "actual": None,
                }
            )
        for operation_id in sorted(actual_ids - expected_ids):
            mismatches.append(
                {
                    "type": "extra_operation",
                    "operation_id": operation_id,
                    "expected": None,
                    "actual": operation_id,
                }
            )

        return mismatches

    def _collect_snapshot_identity_mismatches(
        self,
        audit_record: ExecutionAuditRecord,
        snapshot: ExecutionPlanSnapshot,
    ) -> list[dict[str, Any]]:
        mismatches: list[dict[str, Any]] = []
        if audit_record.snapshot_id != snapshot.snapshot_id:
            mismatches.append(
                {
                    "type": "snapshot_identity_mismatch",
                    "field": "snapshot_id",
                    "expected": snapshot.snapshot_id,
                    "actual": audit_record.snapshot_id,
                }
            )
        if audit_record.plan_id != snapshot.plan_id:
            mismatches.append(
                {
                    "type": "snapshot_identity_mismatch",
                    "field": "plan_id",
                    "expected": snapshot.plan_id,
                    "actual": audit_record.plan_id,
                }
            )
        if audit_record.execution_order != snapshot.execution_order:
            mismatches.append(
                {
                    "type": "snapshot_identity_mismatch",
                    "field": "execution_order",
                    "expected": snapshot.execution_order,
                    "actual": audit_record.execution_order,
                }
            )
        if audit_record.operation_fingerprints != snapshot.operation_fingerprints:
            mismatches.append(
                {
                    "type": "snapshot_identity_mismatch",
                    "field": "operation_fingerprints",
                    "expected": snapshot.operation_fingerprints,
                    "actual": audit_record.operation_fingerprints,
                }
            )
        if audit_record.aggregate_status != snapshot.status:
            mismatches.append(
                {
                    "type": "snapshot_identity_mismatch",
                    "field": "aggregate_status",
                    "expected": snapshot.status,
                    "actual": audit_record.aggregate_status,
                }
            )

        return mismatches

    def _expected_rollback_order(self, execution_order: list[str]) -> list[str]:
        return list(reversed(execution_order))

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RollbackVerificationRejected(
                f"rollback verification {field_name} is required"
            )

        return value
