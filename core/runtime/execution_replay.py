from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.execution_plan import ExecutionPlan
from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot


class ExecutionReplayRejected(RuntimeError):
    pass


class ExecutionReplayRecord:
    def __init__(
        self,
        replay_id: str,
        snapshot_id: str,
        plan_id: str,
        snapshot_fingerprint: str,
        plan_fingerprint: str,
        replay_execution_order: list[str],
        operation_fingerprints: dict[str, str],
        aggregate_status: str,
        verification_result: str,
        mismatches: list[dict[str, Any]] | None = None,
    ) -> None:
        self._replay_id = self._validate_text("replay_id", replay_id)
        self._snapshot_id = snapshot_id
        self._plan_id = plan_id
        self._snapshot_fingerprint = snapshot_fingerprint
        self._plan_fingerprint = plan_fingerprint
        self._replay_execution_order = list(replay_execution_order)
        self._operation_fingerprints = copy.deepcopy(operation_fingerprints)
        self._aggregate_status = aggregate_status
        self._verification_result = verification_result
        self._mismatches = copy.deepcopy(list(mismatches or []))

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
    def snapshot_fingerprint(self) -> str:
        return self._snapshot_fingerprint

    @property
    def plan_fingerprint(self) -> str:
        return self._plan_fingerprint

    @property
    def replay_execution_order(self) -> list[str]:
        return list(self._replay_execution_order)

    @property
    def operation_fingerprints(self) -> dict[str, str]:
        return copy.deepcopy(self._operation_fingerprints)

    @property
    def aggregate_status(self) -> str:
        return self._aggregate_status

    @property
    def verification_result(self) -> str:
        return self._verification_result

    @property
    def mismatches(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._mismatches)

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
            "replay_id": self._replay_id,
            "snapshot_id": self._snapshot_id,
            "plan_id": self._plan_id,
            "snapshot_fingerprint": self._snapshot_fingerprint,
            "plan_fingerprint": self._plan_fingerprint,
            "replay_execution_order": self._replay_execution_order,
            "operation_fingerprints": self._operation_fingerprints,
            "aggregate_status": self._aggregate_status,
            "verification_result": self._verification_result,
            "mismatches": self._mismatches,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise ExecutionReplayRejected(
                f"execution replay {field_name} is required"
            )

        return value


class ExecutionReplayVerifier:
    VERIFIED = "verified"
    MISMATCHED = "mismatched"

    def __init__(self, replay_id: str) -> None:
        self.replay_id = self._validate_text("replay_id", replay_id)

    def verify_snapshot(
        self,
        snapshot: ExecutionPlanSnapshot,
    ) -> ExecutionReplayRecord:
        return ExecutionReplayRecord(
            replay_id=self.replay_id,
            snapshot_id=snapshot.snapshot_id,
            plan_id=snapshot.plan_id,
            snapshot_fingerprint=snapshot.fingerprint,
            plan_fingerprint=snapshot.plan_fingerprint,
            replay_execution_order=snapshot.execution_order,
            operation_fingerprints=snapshot.operation_fingerprints,
            aggregate_status=snapshot.status,
            verification_result=self.VERIFIED,
            mismatches=[],
        )

    def verify_plan_against_snapshot(
        self,
        plan: ExecutionPlan,
        snapshot: ExecutionPlanSnapshot,
    ) -> ExecutionReplayRecord:
        operations = plan.execution_order()
        replay_execution_order = [
            operation.operation_id
            for operation in operations
        ]
        operation_fingerprints = {
            operation.operation_id: operation.fingerprint
            for operation in operations
        }
        mismatches = self._collect_mismatches(
            plan=plan,
            snapshot=snapshot,
            replay_execution_order=replay_execution_order,
            operation_fingerprints=operation_fingerprints,
        )

        return ExecutionReplayRecord(
            replay_id=self.replay_id,
            snapshot_id=snapshot.snapshot_id,
            plan_id=plan.plan_id,
            snapshot_fingerprint=snapshot.fingerprint,
            plan_fingerprint=plan.fingerprint,
            replay_execution_order=replay_execution_order,
            operation_fingerprints=operation_fingerprints,
            aggregate_status=plan.status,
            verification_result=self.MISMATCHED if mismatches else self.VERIFIED,
            mismatches=mismatches,
        )

    def _collect_mismatches(
        self,
        plan: ExecutionPlan,
        snapshot: ExecutionPlanSnapshot,
        replay_execution_order: list[str],
        operation_fingerprints: dict[str, str],
    ) -> list[dict[str, Any]]:
        mismatches: list[dict[str, Any]] = []
        snapshot_operation_fingerprints = snapshot.operation_fingerprints

        if plan.plan_id != snapshot.plan_id:
            mismatches.append(
                self._mismatch("plan_id_mismatch", snapshot.plan_id, plan.plan_id)
            )
        if plan.fingerprint != snapshot.plan_fingerprint:
            mismatches.append(
                self._mismatch(
                    "plan_fingerprint_mismatch",
                    snapshot.plan_fingerprint,
                    plan.fingerprint,
                )
            )
        if replay_execution_order != snapshot.execution_order:
            mismatches.append(
                self._mismatch(
                    "execution_order_mismatch",
                    snapshot.execution_order,
                    replay_execution_order,
                )
            )

        snapshot_operation_ids = set(snapshot_operation_fingerprints)
        replay_operation_ids = set(operation_fingerprints)
        for operation_id in sorted(snapshot_operation_ids - replay_operation_ids):
            mismatches.append(
                {
                    "type": "missing_operation",
                    "operation_id": operation_id,
                    "expected": snapshot_operation_fingerprints[operation_id],
                    "actual": None,
                }
            )
        for operation_id in sorted(replay_operation_ids - snapshot_operation_ids):
            mismatches.append(
                {
                    "type": "extra_operation",
                    "operation_id": operation_id,
                    "expected": None,
                    "actual": operation_fingerprints[operation_id],
                }
            )
        for operation_id in sorted(snapshot_operation_ids & replay_operation_ids):
            expected = snapshot_operation_fingerprints[operation_id]
            actual = operation_fingerprints[operation_id]
            if actual != expected:
                mismatches.append(
                    {
                        "type": "operation_fingerprint_mismatch",
                        "operation_id": operation_id,
                        "expected": expected,
                        "actual": actual,
                    }
                )

        if plan.status != snapshot.status:
            mismatches.append(
                self._mismatch(
                    "aggregate_status_mismatch",
                    snapshot.status,
                    plan.status,
                )
            )

        return mismatches

    def _mismatch(self, mismatch_type: str, expected: Any, actual: Any) -> dict[str, Any]:
        return {
            "type": mismatch_type,
            "expected": copy.deepcopy(expected),
            "actual": copy.deepcopy(actual),
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise ExecutionReplayRejected(
                f"execution replay {field_name} is required"
            )

        return value
