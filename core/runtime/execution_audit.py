from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.runtime.execution_replay import ExecutionReplayRecord


class ExecutionAuditRejected(RuntimeError):
    pass


class ExecutionAuditRecord:
    def __init__(
        self,
        audit_id: str,
        replay_id: str,
        snapshot_id: str,
        plan_id: str,
        verification_result: str,
        mismatches: list[dict[str, Any]] | None,
        replay_fingerprint: str,
        aggregate_status: str,
        execution_order: list[str],
        operation_fingerprints: dict[str, str],
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._audit_id = self._validate_text("audit_id", audit_id)
        self._replay_id = replay_id
        self._snapshot_id = snapshot_id
        self._plan_id = plan_id
        self._verification_result = verification_result
        self._mismatches = copy.deepcopy(list(mismatches or []))
        self._replay_fingerprint = replay_fingerprint
        self._aggregate_status = aggregate_status
        self._execution_order = list(execution_order)
        self._operation_fingerprints = copy.deepcopy(operation_fingerprints)
        self._metadata = copy.deepcopy(metadata)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @classmethod
    def from_replay_record(
        cls,
        audit_id: str,
        replay_record: ExecutionReplayRecord,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> "ExecutionAuditRecord":
        return cls(
            audit_id=audit_id,
            replay_id=replay_record.replay_id,
            snapshot_id=replay_record.snapshot_id,
            plan_id=replay_record.plan_id,
            verification_result=replay_record.verification_result,
            mismatches=replay_record.mismatches,
            replay_fingerprint=replay_record.fingerprint,
            aggregate_status=replay_record.aggregate_status,
            execution_order=replay_record.replay_execution_order,
            operation_fingerprints=replay_record.operation_fingerprints,
            metadata=metadata,
            runtime_args=runtime_args,
            created_at=created_at,
        )

    @property
    def audit_id(self) -> str:
        return self._audit_id

    @property
    def replay_id(self) -> str:
        return self._replay_id

    @property
    def snapshot_id(self) -> str:
        return self._snapshot_id

    @property
    def plan_id(self) -> str:
        return self._plan_id

    @property
    def verification_result(self) -> str:
        return self._verification_result

    @property
    def mismatches(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._mismatches)

    @property
    def replay_fingerprint(self) -> str:
        return self._replay_fingerprint

    @property
    def aggregate_status(self) -> str:
        return self._aggregate_status

    @property
    def execution_order(self) -> list[str]:
        return list(self._execution_order)

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
            "audit_id": self._audit_id,
            "replay_id": self._replay_id,
            "snapshot_id": self._snapshot_id,
            "plan_id": self._plan_id,
            "verification_result": self._verification_result,
            "mismatches": self._mismatches,
            "replay_fingerprint": self._replay_fingerprint,
            "aggregate_status": self._aggregate_status,
            "execution_order": self._execution_order,
            "operation_fingerprints": self._operation_fingerprints,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise ExecutionAuditRejected(
                f"execution audit {field_name} is required"
            )

        return value


class ExecutionAuditTrail:
    def __init__(self) -> None:
        self._records: dict[str, ExecutionAuditRecord] = {}
        self._order: list[str] = []

    def append_record(
        self,
        record: ExecutionAuditRecord,
    ) -> ExecutionAuditRecord:
        audit_id = self._validate_text("audit_id", getattr(record, "audit_id", None))
        if audit_id in self._records:
            raise ExecutionAuditRejected(
                f"execution audit duplicate audit_id: {audit_id!r}"
            )

        self._records[audit_id] = copy.deepcopy(record)
        self._order.append(audit_id)
        return copy.deepcopy(self._records[audit_id])

    def get_record(self, audit_id: str) -> ExecutionAuditRecord:
        audit_id = self._validate_text("audit_id", audit_id)
        record = self._records.get(audit_id)
        if record is None:
            raise ExecutionAuditRejected(
                f"execution audit unknown audit_id: {audit_id!r}"
            )

        return copy.deepcopy(record)

    def list_records(self) -> list[ExecutionAuditRecord]:
        return [
            copy.deepcopy(self._records[audit_id])
            for audit_id in self._order
        ]

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            [
                self._records[audit_id].fingerprint
                for audit_id in self._order
            ],
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise ExecutionAuditRejected(
                f"execution audit {field_name} is required"
            )

        return value
