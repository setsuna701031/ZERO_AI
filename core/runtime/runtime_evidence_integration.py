from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.execution_audit import ExecutionAuditRecord
from core.runtime.execution_plan import ExecutionPlan
from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot
from core.runtime.execution_replay import ExecutionReplayRecord, ExecutionReplayVerifier
from core.runtime.rollback_verification import (
    RollbackVerificationRecord,
    RollbackVerificationVerifier,
)
from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle


class RuntimeEvidenceIntegrationRejected(RuntimeError):
    pass


class RuntimeEvidenceIntegrationContext:
    def __init__(
        self,
        integration_id: str,
        plan_id: str | None = None,
        snapshot_id: str | None = None,
        replay_id: str | None = None,
        audit_id: str | None = None,
        rollback_id: str | None = None,
        bundle_id: str | None = None,
    ) -> None:
        self._identity = {
            "integration_id": self._validate_text("integration_id", integration_id),
            "plan_id": plan_id,
            "snapshot_id": snapshot_id,
            "replay_id": replay_id,
            "audit_id": audit_id,
            "rollback_id": rollback_id,
            "bundle_id": bundle_id,
        }

    @property
    def integration_id(self) -> str:
        return self._identity["integration_id"]

    @property
    def plan_id(self) -> str | None:
        return self._identity["plan_id"]

    @property
    def snapshot_id(self) -> str | None:
        return self._identity["snapshot_id"]

    @property
    def replay_id(self) -> str | None:
        return self._identity["replay_id"]

    @property
    def audit_id(self) -> str | None:
        return self._identity["audit_id"]

    @property
    def rollback_id(self) -> str | None:
        return self._identity["rollback_id"]

    @property
    def bundle_id(self) -> str | None:
        return self._identity["bundle_id"]

    @property
    def identity(self) -> dict[str, str | None]:
        return copy.deepcopy(self._identity)

    def with_updates(self, **updates: str | None) -> "RuntimeEvidenceIntegrationContext":
        identity = self.identity
        identity.update(updates)
        return RuntimeEvidenceIntegrationContext(**identity)

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeEvidenceIntegrationRejected(
                f"runtime evidence integration {field_name} is required"
            )

        return value


class RuntimeEvidenceEmitter:
    def __init__(self, integration_id: str) -> None:
        integration_id = self._validate_text("integration_id", integration_id)
        self._context = RuntimeEvidenceIntegrationContext(integration_id)
        self._emissions: list[dict[str, str]] = []

    @property
    def context(self) -> RuntimeEvidenceIntegrationContext:
        return copy.deepcopy(self._context)

    @property
    def emission_order(self) -> list[dict[str, str]]:
        return copy.deepcopy(self._emissions)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "integration_identity": self._context.identity,
                "emitted_evidence_fingerprints": self._emissions,
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def emit_snapshot(self, plan: ExecutionPlan) -> ExecutionPlanSnapshot:
        snapshot = ExecutionPlanSnapshot.from_plan(
            self._id("snapshot"),
            plan,
        )
        self._context = self._context.with_updates(
            plan_id=snapshot.plan_id,
            snapshot_id=snapshot.snapshot_id,
        )
        self._append_emission("snapshot", snapshot.fingerprint)
        return copy.deepcopy(snapshot)

    def emit_replay(
        self,
        snapshot: ExecutionPlanSnapshot,
        plan: ExecutionPlan,
    ) -> ExecutionReplayRecord:
        replay = ExecutionReplayVerifier(
            self._id("replay")
        ).verify_plan_against_snapshot(plan, snapshot)
        self._context = self._context.with_updates(
            plan_id=replay.plan_id,
            snapshot_id=replay.snapshot_id,
            replay_id=replay.replay_id,
        )
        self._append_emission("replay", replay.fingerprint)
        return copy.deepcopy(replay)

    def emit_audit(
        self,
        replay_record: ExecutionReplayRecord,
    ) -> ExecutionAuditRecord:
        audit = ExecutionAuditRecord.from_replay_record(
            self._id("audit"),
            replay_record,
        )
        self._context = self._context.with_updates(
            plan_id=audit.plan_id,
            snapshot_id=audit.snapshot_id,
            replay_id=audit.replay_id,
            audit_id=audit.audit_id,
        )
        self._append_emission("audit", audit.fingerprint)
        return copy.deepcopy(audit)

    def emit_rollback(
        self,
        snapshot: ExecutionPlanSnapshot,
    ) -> RollbackVerificationRecord:
        rollback = RollbackVerificationVerifier(
            self._id("rollback")
        ).verify_snapshot_rollback(snapshot)
        self._context = self._context.with_updates(
            plan_id=rollback.plan_id,
            snapshot_id=rollback.snapshot_id,
            rollback_id=rollback.rollback_id,
        )
        self._append_emission("rollback", rollback.fingerprint)
        return copy.deepcopy(rollback)

    def emit_bundle(
        self,
        snapshot: ExecutionPlanSnapshot,
        replay: ExecutionReplayRecord,
        audit: ExecutionAuditRecord,
        rollback: RollbackVerificationRecord,
    ) -> RuntimeEvidenceBundle:
        bundle = RuntimeEvidenceBundle(
            self._id("bundle"),
            snapshot,
            replay,
            audit,
            rollback,
        )
        self._context = self._context.with_updates(
            plan_id=bundle.plan_id,
            snapshot_id=bundle.snapshot_id,
            bundle_id=bundle.bundle_id,
        )
        self._append_emission("bundle", bundle.fingerprint)
        return copy.deepcopy(bundle)

    def _append_emission(self, evidence_type: str, fingerprint: str) -> None:
        self._emissions.append(
            {
                "type": evidence_type,
                "fingerprint": fingerprint,
            }
        )

    def _id(self, suffix: str) -> str:
        return f"{self._context.integration_id}:{suffix}"

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeEvidenceIntegrationRejected(
                f"runtime evidence integration {field_name} is required"
            )

        return value
