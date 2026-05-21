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
from core.runtime.runtime_seal import attach_runtime_seal
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


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
        stdout: str = "",
        stderr: str = "",
        pytest_results: Any = None,
        impacted_plan: Any = None,
        verification_traces: Any = None,
        rollback_traces: Any = None,
        recovery_traces: Any = None,
        replay_traces: Any = None,
        mutation_summaries: Any = None,
        runtime_state_transitions: Any = None,
        execution_result: Any = None,
    ) -> None:
        self._bundle_id = self._validate_text("bundle_id", bundle_id)
        self._canonical_mode = not all(
            item is not None
            for item in (snapshot, replay_record, audit_record, rollback_record)
        )
        if not self._canonical_mode:
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
        self._stdout = str(stdout or "")
        self._stderr = str(stderr or "")
        self._pytest_results = copy.deepcopy(pytest_results)
        self._impacted_plan = copy.deepcopy(impacted_plan)
        self._verification_traces = copy.deepcopy(verification_traces or [])
        self._rollback_traces = copy.deepcopy(rollback_traces or [])
        self._recovery_traces = copy.deepcopy(recovery_traces or [])
        self._replay_traces = copy.deepcopy(replay_traces or [])
        self._mutation_summaries = copy.deepcopy(mutation_summaries or [])
        self._runtime_state_transitions = copy.deepcopy(runtime_state_transitions or [])
        self._execution_result = copy.deepcopy(execution_result)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @classmethod
    def from_runtime_execution(
        cls,
        *,
        bundle_id: str,
        execution_result: Any,
        stdout: str = "",
        stderr: str = "",
        pytest_results: Any = None,
        impacted_plan: Any = None,
        verification_traces: Any = None,
        rollback_traces: Any = None,
        recovery_traces: Any = None,
        replay_traces: Any = None,
        mutation_summaries: Any = None,
        runtime_state_transitions: Any = None,
        metadata: Any = None,
    ) -> "RuntimeEvidenceBundle":
        result_payload = (
            execution_result.to_dict()
            if hasattr(execution_result, "to_dict")
            else copy.deepcopy(execution_result)
        )
        return cls(
            bundle_id=bundle_id,
            snapshot=None,
            replay_record=None,
            audit_record=None,
            rollback_record=None,
            metadata=metadata,
            stdout=stdout or str((result_payload or {}).get("stdout") or ""),
            stderr=stderr or str((result_payload or {}).get("stderr") or ""),
            pytest_results=pytest_results,
            impacted_plan=impacted_plan,
            verification_traces=verification_traces,
            rollback_traces=rollback_traces,
            recovery_traces=recovery_traces,
            replay_traces=replay_traces,
            mutation_summaries=mutation_summaries,
            runtime_state_transitions=runtime_state_transitions,
            execution_result=result_payload,
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
        if self._canonical_mode:
            if isinstance(self._execution_result, dict):
                return str(self._execution_result.get("status") or "")
            return ""
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
        if self._canonical_mode:
            canonical = self._canonical_payload()
            canonical.pop("created_at", None)
            return canonical
        payload = {
            "bundle_id": self._bundle_id,
            "snapshot_fingerprint": self._snapshot.fingerprint,
            "replay_fingerprint": self._replay_record.fingerprint,
            "audit_fingerprint": self._audit_record.fingerprint,
            "rollback_fingerprint": self._rollback_record.fingerprint,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
        }
        if self._canonical_mode:
            canonical = self._canonical_payload()
            canonical.pop("created_at", None)
            payload["canonical"] = canonical
        return payload

    def to_dict(self) -> dict[str, Any]:
        if self._canonical_mode:
            return attach_runtime_seal(
                self._canonical_payload(),
                artifact_type="runtime_evidence_bundle",
            )
        payload = {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_evidence_bundle",
            "bundle_id": self.bundle_id,
            "plan_id": self.plan_id,
            "snapshot_id": self.snapshot_id,
            "aggregate_status": self.aggregate_status,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "runtime_args": self.runtime_args,
            "fingerprint": self.fingerprint,
        }
        return attach_runtime_seal(payload, artifact_type="runtime_evidence_bundle")

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_evidence_bundle",
            "bundle_id": self._bundle_id,
            "created_at": self._created_at,
            "stdout": self._stdout,
            "stderr": self._stderr,
            "pytest_results": copy.deepcopy(self._pytest_results),
            "impacted_plan": copy.deepcopy(self._impacted_plan),
            "verification_traces": copy.deepcopy(self._verification_traces),
            "rollback_traces": copy.deepcopy(self._rollback_traces),
            "recovery_traces": copy.deepcopy(self._recovery_traces),
            "replay_traces": copy.deepcopy(self._replay_traces),
            "mutation_summaries": copy.deepcopy(self._mutation_summaries),
            "runtime_state_transitions": copy.deepcopy(self._runtime_state_transitions),
            "execution_result": copy.deepcopy(self._execution_result),
            "metadata": copy.deepcopy(self._metadata),
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
