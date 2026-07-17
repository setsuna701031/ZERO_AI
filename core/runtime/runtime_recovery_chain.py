from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any

from core.runtime.runtime_incident import RuntimeIncidentLayer
from core.runtime.runtime_incident_reconstruction import reconstruct_runtime_incident
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_recovery_plan import (
    RuntimeRecoveryPlan,
    build_runtime_recovery_plan,
    stable_recovery_fingerprint,
    utc_timestamp,
)
from core.runtime.runtime_recovery_verifier import (
    RuntimeRecoveryVerificationResult,
    verify_runtime_recovery_chain,
)
from core.runtime.runtime_seal import attach_runtime_seal


@dataclass(frozen=True)
class RuntimeRecoveryChain:
    recovery_id: str
    source_session_id: str
    source_failure: dict[str, Any]
    recovery_plan: dict[str, Any]
    replay_reference: dict[str, Any]
    rollback_reference: dict[str, Any]
    verification_result: dict[str, Any]
    incident_summary: dict[str, Any]
    status: str
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    journal_reconstruction: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "source_failure": copy.deepcopy(self.source_failure),
            "recovery_plan": copy.deepcopy(self.recovery_plan),
            "replay_reference": copy.deepcopy(self.replay_reference),
            "rollback_reference": copy.deepcopy(self.rollback_reference),
            "verification_result": copy.deepcopy(self.verification_result),
            "incident_summary": copy.deepcopy(self.incident_summary),
            "status": self.status,
            "audit_events": [copy.deepcopy(item) for item in self.audit_events],
            "journal_reconstruction": copy.deepcopy(self.journal_reconstruction),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def sealed_dict(self) -> dict[str, Any]:
        return attach_runtime_seal(
            self.to_dict(),
            artifact_type="runtime_recovery_chain",
            metadata={"recovery_id": self.recovery_id, "status": self.status},
        )


class RuntimeRecoveryChainBuilder:
    def __init__(
        self,
        *,
        replay_engine: Any = None,
        incident_layer: RuntimeIncidentLayer | None = None,
        journal: RuntimeJournal | None = None,
    ) -> None:
        self.replay_engine = replay_engine
        self.incident_layer = incident_layer if incident_layer is not None else RuntimeIncidentLayer()
        self.journal = journal if journal is not None else RuntimeJournal()
        self._chains: dict[str, RuntimeRecoveryChain] = {}

    def build_chain(
        self,
        *,
        source_failure: dict[str, Any],
        recovery_id: str = "",
        source_session_id: str = "",
        task_id: str = "",
        source_state_before: dict[str, Any] | None = None,
        source_state_after: dict[str, Any] | None = None,
        replay_metadata: dict[str, Any] | None = None,
        rollback_reference: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryChain:
        failure_snapshot = copy.deepcopy(source_failure if isinstance(source_failure, dict) else {})
        resolved_source_session_id = str(
            source_session_id
            or failure_snapshot.get("source_session_id")
            or failure_snapshot.get("session_id")
            or ""
        ).strip()
        resolved_task_id = str(task_id or failure_snapshot.get("task_id") or "").strip()
        resolved_recovery_id = str(recovery_id or "").strip()
        if not resolved_recovery_id:
            resolved_recovery_id = self._derive_recovery_id(
                failure_snapshot,
                source_session_id=resolved_source_session_id,
                task_id=resolved_task_id,
            )

        audit_events: list[dict[str, Any]] = []
        self._append_audit(
            audit_events,
            recovery_id=resolved_recovery_id,
            event_type="failure_detected",
            payload={"source_failure": failure_snapshot},
        )

        replay_reference = self._build_replay_reference(
            recovery_id=resolved_recovery_id,
            source_session_id=resolved_source_session_id,
            replay_metadata=replay_metadata,
        )
        self._append_audit(
            audit_events,
            recovery_id=resolved_recovery_id,
            event_type="replay_reference_attached",
            payload={"replay_reference": replay_reference},
        )

        plan = build_runtime_recovery_plan(
            recovery_id=resolved_recovery_id,
            source_failure=failure_snapshot,
            source_session_id=resolved_source_session_id,
            task_id=resolved_task_id,
            replay_reference=replay_reference,
            rollback_reference=rollback_reference,
            metadata=metadata,
        )
        plan_dict = plan.to_dict()
        self._append_audit(
            audit_events,
            recovery_id=resolved_recovery_id,
            event_type="recovery_plan_built",
            payload={"recovery_plan": plan_dict},
        )

        resolved_rollback_reference = self._build_rollback_reference(
            plan=plan,
            rollback_reference=rollback_reference,
        )
        if resolved_rollback_reference:
            self._append_audit(
                audit_events,
                recovery_id=resolved_recovery_id,
                event_type="rollback_represented",
                payload={"rollback_reference": resolved_rollback_reference},
            )

        provisional_incident = reconstruct_runtime_incident(
            recovery_id=resolved_recovery_id,
            source_failure=plan.source_failure.to_dict(),
            recovery_plan=plan_dict,
            replay_reference=replay_reference,
            rollback_reference=resolved_rollback_reference,
            verification_result={},
            audit_events=audit_events,
            journal_reconstruction=self._safe_journal_reconstruction(),
        )

        verification = verify_runtime_recovery_chain(
            recovery_id=resolved_recovery_id,
            plan=plan,
            replay_reference=replay_reference,
            rollback_reference=resolved_rollback_reference,
            audit_events=audit_events,
            incident_summary=provisional_incident,
            source_state_before=copy.deepcopy(source_state_before),
            source_state_after=copy.deepcopy(source_state_after),
        )
        verification_dict = verification.to_dict()
        self._append_audit(
            audit_events,
            recovery_id=resolved_recovery_id,
            event_type="recovery_verified",
            payload={"verification_result": verification_dict},
        )

        incident_summary = reconstruct_runtime_incident(
            recovery_id=resolved_recovery_id,
            source_failure=plan.source_failure.to_dict(),
            recovery_plan=plan_dict,
            replay_reference=replay_reference,
            rollback_reference=resolved_rollback_reference,
            verification_result=verification_dict,
            audit_events=audit_events,
            journal_reconstruction=self._safe_journal_reconstruction(),
        )
        self.incident_layer.attach_event(
            {
                "event_type": "failure",
                "incident_id": incident_summary.get("incident_id"),
                "task_id": resolved_task_id,
                "recovery_id": resolved_recovery_id,
                "payload": plan.source_failure.to_dict(),
            }
        )
        self.incident_layer.attach_event(
            {
                "event_type": "recovery",
                "incident_id": incident_summary.get("incident_id"),
                "task_id": resolved_task_id,
                "recovery_id": resolved_recovery_id,
                "payload": {"status": verification.status, "verified": verification.verified},
            }
        )

        chain = RuntimeRecoveryChain(
            recovery_id=resolved_recovery_id,
            source_session_id=resolved_source_session_id,
            source_failure=plan.source_failure.to_dict(),
            recovery_plan=plan_dict,
            replay_reference=replay_reference,
            rollback_reference=resolved_rollback_reference,
            verification_result=verification_dict,
            incident_summary=incident_summary,
            status=verification.status,
            audit_events=audit_events,
            journal_reconstruction=self._safe_journal_reconstruction(),
            metadata=copy.deepcopy(metadata or {}),
        )
        chain = replace(chain, metadata={**chain.metadata, "incident_layer_summary": self.incident_layer.incident_summary()})
        self._chains[chain.recovery_id] = chain
        self._append_journal("runtime_recovery_chain_committed", chain.sealed_dict(), {"recovery_id": chain.recovery_id})
        return chain

    def get_chain(self, recovery_id: str) -> RuntimeRecoveryChain | None:
        chain = self._chains.get(str(recovery_id or ""))
        return copy.deepcopy(chain) if chain is not None else None

    def list_chains(self) -> list[RuntimeRecoveryChain]:
        return [copy.deepcopy(chain) for chain in self._chains.values()]

    def _build_replay_reference(
        self,
        *,
        recovery_id: str,
        source_session_id: str,
        replay_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        replay_id = f"{recovery_id}-replay"
        if not source_session_id:
            return {
                "replay_id": replay_id,
                "status": "missing_source_session",
                "source_session_id": "",
                "created_at": utc_timestamp(),
            }
        if self.replay_engine is None:
            return {
                "replay_id": replay_id,
                "status": "reference_only",
                "source_session_id": source_session_id,
                "created_at": utc_timestamp(),
            }
        try:
            replay = self.replay_engine.replay_session(
                replay_id=replay_id,
                source_session_id=source_session_id,
                payload={"recovery_id": recovery_id},
                metadata={"runtime_phase": "recovery_replay", **dict(replay_metadata or {})},
            )
            return {
                "replay_id": getattr(replay, "replay_id", replay_id),
                "status": "replayed" if bool(getattr(replay, "verified", False)) else "replay_unverified",
                "source_session_id": getattr(replay, "source_session_id", source_session_id),
                "record_count": len(getattr(replay, "records", []) or []),
                "verified": bool(getattr(replay, "verified", False)),
                "created_at": utc_timestamp(),
            }
        except Exception as exc:
            return {
                "replay_id": replay_id,
                "status": "replay_failed",
                "source_session_id": source_session_id,
                "error": str(exc),
                "created_at": utc_timestamp(),
            }

    def _build_rollback_reference(
        self,
        *,
        plan: RuntimeRecoveryPlan,
        rollback_reference: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if rollback_reference:
            resolved = copy.deepcopy(rollback_reference)
            resolved.setdefault("status", "represented")
            resolved.setdefault("created_at", utc_timestamp())
            return resolved
        if not plan.rollback_required:
            return {}
        return {
            "rollback_id": f"{plan.recovery_id}-rollback",
            "mode": "governed_manual_or_transaction_rollback",
            "status": "required_not_executed",
            "reason": "recovery chain represents rollback but does not blindly execute it",
            "created_at": utc_timestamp(),
        }

    def _append_audit(
        self,
        audit_events: list[dict[str, Any]],
        *,
        recovery_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        event = {
            "event_type": event_type,
            "recovery_id": recovery_id,
            "payload": copy.deepcopy(payload),
            "timestamp": utc_timestamp(),
            "source": "runtime_recovery_chain",
        }
        audit_events.append(event)
        self._append_journal("runtime_recovery_audit_event", event, {"recovery_id": recovery_id})

    def _append_journal(self, record_type: str, payload: dict[str, Any], metadata: dict[str, Any]) -> None:
        try:
            self.journal.append(record_type, payload=payload, metadata=metadata)
        except Exception:
            return

    def _safe_journal_reconstruction(self) -> dict[str, Any]:
        try:
            return self.journal.reconstruct()
        except Exception as exc:
            return {"record_count": 0, "error": str(exc)}

    def _derive_recovery_id(self, source_failure: dict[str, Any], *, source_session_id: str, task_id: str) -> str:
        seed = {
            "source_failure": source_failure,
            "source_session_id": source_session_id,
            "task_id": task_id,
            "created_at": utc_timestamp(),
        }
        return "runtime-recovery-" + stable_recovery_fingerprint(seed)[:16]


def build_runtime_recovery_chain(**kwargs: Any) -> RuntimeRecoveryChain:
    return RuntimeRecoveryChainBuilder().build_chain(**kwargs)


__all__ = [
    "RuntimeRecoveryChain",
    "RuntimeRecoveryChainBuilder",
    "build_runtime_recovery_chain",
]
