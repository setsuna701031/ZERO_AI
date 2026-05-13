from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.runtime.execution_audit import ExecutionAuditRecord
from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot
from core.runtime.execution_replay import ExecutionReplayRecord
from core.runtime.rollback_verification import RollbackVerificationRecord


class RuntimeEvidenceBundleRejected(RuntimeError):
    pass


class RuntimeEvidenceBundle:
    def __init__(
        self,
        bundle_id: str,
        snapshot: ExecutionPlanSnapshot,
        replay_record: ExecutionReplayRecord,
        audit_record: ExecutionAuditRecord,
        rollback_record: RollbackVerificationRecord,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._bundle_id = self._validate_text("bundle_id", bundle_id)
        self._validate_identity(
            snapshot=snapshot,
            replay_record=replay_record,
            audit_record=audit_record,
            rollback_record=rollback_record,
        )
        self._snapshot = copy.deepcopy(snapshot)
        self._replay_record = copy.deepcopy(replay_record)
        self._audit_record = copy.deepcopy(audit_record)
        self._rollback_record = copy.deepcopy(rollback_record)
        self._metadata = copy.deepcopy(metadata)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @property
    def bundle_id(self) -> str:
        return self._bundle_id

    @property
    def snapshot(self) -> ExecutionPlanSnapshot:
        return copy.deepcopy(self._snapshot)

    @property
    def replay_record(self) -> ExecutionReplayRecord:
        return copy.deepcopy(self._replay_record)

    @property
    def audit_record(self) -> ExecutionAuditRecord:
        return copy.deepcopy(self._audit_record)

    @property
    def rollback_record(self) -> RollbackVerificationRecord:
        return copy.deepcopy(self._rollback_record)

    @property
    def created_at(self) -> str:
        return self._created_at

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def plan_id(self) -> str:
        return self._snapshot.plan_id

    @property
    def snapshot_id(self) -> str:
        return self._snapshot.snapshot_id

    @property
    def aggregate_status(self) -> str:
        return self._snapshot.status

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
            "bundle_id": self._bundle_id,
            "snapshot_fingerprint": self._snapshot.fingerprint,
            "replay_fingerprint": self._replay_record.fingerprint,
            "audit_fingerprint": self._audit_record.fingerprint,
            "rollback_fingerprint": self._rollback_record.fingerprint,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
        }

    def _validate_identity(
        self,
        snapshot: ExecutionPlanSnapshot,
        replay_record: ExecutionReplayRecord,
        audit_record: ExecutionAuditRecord,
        rollback_record: RollbackVerificationRecord,
    ) -> None:
        expected_plan_id = snapshot.plan_id
        expected_snapshot_id = snapshot.snapshot_id
        identity_sources = [
            ("replay_record", replay_record.plan_id, replay_record.snapshot_id),
            ("audit_record", audit_record.plan_id, audit_record.snapshot_id),
            ("rollback_record", rollback_record.plan_id, rollback_record.snapshot_id),
        ]
        for source, plan_id, snapshot_id in identity_sources:
            if plan_id != expected_plan_id or snapshot_id != expected_snapshot_id:
                raise RuntimeEvidenceBundleRejected(
                    "runtime evidence bundle identity mismatch: "
                    f"{source} expected plan_id={expected_plan_id!r}, "
                    f"snapshot_id={expected_snapshot_id!r}; "
                    f"got plan_id={plan_id!r}, snapshot_id={snapshot_id!r}"
                )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeEvidenceBundleRejected(
                f"runtime evidence bundle {field_name} is required"
            )

        return value
