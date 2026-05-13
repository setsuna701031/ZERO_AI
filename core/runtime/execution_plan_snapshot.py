from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.runtime.execution_plan import ExecutionPlan


class ExecutionPlanSnapshotRejected(RuntimeError):
    pass


class ExecutionPlanSnapshot:
    def __init__(
        self,
        snapshot_id: str,
        plan: ExecutionPlan,
        created_at: str | None = None,
    ) -> None:
        self._snapshot_id = self._validate_text("snapshot_id", snapshot_id)
        self._plan_id = plan.plan_id
        self._plan_fingerprint = plan.fingerprint
        operations = plan.execution_order()
        self._execution_order = [
            operation.operation_id
            for operation in operations
        ]
        self._operation_fingerprints = {
            operation.operation_id: operation.fingerprint
            for operation in operations
        }
        self._status = plan.status
        self._metadata = copy.deepcopy(plan.metadata)
        self._runtime_args = copy.deepcopy(plan.runtime_args)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @classmethod
    def from_plan(
        cls,
        snapshot_id: str,
        plan: ExecutionPlan,
        created_at: str | None = None,
    ) -> "ExecutionPlanSnapshot":
        return cls(snapshot_id=snapshot_id, plan=plan, created_at=created_at)

    @property
    def snapshot_id(self) -> str:
        return self._snapshot_id

    @property
    def plan_id(self) -> str:
        return self._plan_id

    @property
    def plan_fingerprint(self) -> str:
        return self._plan_fingerprint

    @property
    def status(self) -> str:
        return self._status

    @property
    def created_at(self) -> str:
        return self._created_at

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
            "snapshot_id": self._snapshot_id,
            "plan_id": self._plan_id,
            "plan_fingerprint": self._plan_fingerprint,
            "execution_order": self._execution_order,
            "operation_fingerprints": self._operation_fingerprints,
            "status": self._status,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise ExecutionPlanSnapshotRejected(
                f"execution plan snapshot {field_name} is required"
            )

        return value
