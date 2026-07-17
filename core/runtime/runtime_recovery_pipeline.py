from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, dict):
            return copy.deepcopy(converted)
    return {}


def _text(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


def _call_optional(obj: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
    method = getattr(obj, method_name, None)
    if callable(method):
        return method(*args, **kwargs)
    return None


PIPELINE_STATUS_READY_TO_CONTINUE = "ready_to_continue"
PIPELINE_STATUS_REVIEW_REQUIRED = "review_required"
PIPELINE_STATUS_BLOCKED = "blocked"
PIPELINE_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class RuntimeRecoveryPipelineResult:
    pipeline_id: str
    recovery_id: str
    source_session_id: str
    source_failure: dict[str, Any]
    chain: dict[str, Any]
    execution: dict[str, Any]
    continuation: dict[str, Any]
    integration_seal: dict[str, Any]
    final_status: str
    next_action: str
    runtime_state_patch: dict[str, Any] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        events = [copy.deepcopy(item) for item in self.audit_events if isinstance(item, dict)]
        object.__setattr__(self, "audit_events", events)
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_recovery_pipeline_result",
            "pipeline_id": self.pipeline_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "source_failure": copy.deepcopy(self.source_failure),
            "chain": copy.deepcopy(self.chain),
            "execution": copy.deepcopy(self.execution),
            "continuation": copy.deepcopy(self.continuation),
            "integration_seal": copy.deepcopy(self.integration_seal),
            "final_status": self.final_status,
            "next_action": self.next_action,
            "runtime_state_patch": copy.deepcopy(self.runtime_state_patch),
            "audit_events": copy.deepcopy(self.audit_events),
            "created_at": self.created_at,
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()
        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(self.to_dict(include_fingerprint=False))


def build_recovery_pipeline_id(recovery_id: str, source_session_id: str = "") -> str:
    seed = {
        "kind": "runtime_recovery_pipeline",
        "recovery_id": str(recovery_id or ""),
        "source_session_id": str(source_session_id or ""),
    }
    return "runtime-recovery-pipeline-" + _stable_fingerprint(seed)[:16]


class RuntimeRecoveryPipeline:
    """
    Integration entrypoint for recovery runtime.

    This class intentionally does not mutate TaskRuntime/StepExecutor directly.
    It produces a controlled runtime_state_patch that the owning runtime layer can
    apply through its existing transition authority.
    """

    def __init__(
        self,
        *,
        chain_builder: Any | None = None,
        executor: Any | None = None,
        continuation_builder: Any | None = None,
        integration_sealer: Any | None = None,
        journal: Any | None = None,
    ) -> None:
        self.chain_builder = chain_builder
        self.executor = executor
        self.continuation_builder = continuation_builder
        self.integration_sealer = integration_sealer
        self.journal = journal

    def run_failure_recovery(
        self,
        *,
        source_state: dict[str, Any],
        source_failure: dict[str, Any] | None = None,
        approval_granted: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeRecoveryPipelineResult:
        state = copy.deepcopy(source_state if isinstance(source_state, dict) else {})
        failure = copy.deepcopy(source_failure if isinstance(source_failure, dict) else {})
        meta = copy.deepcopy(metadata if isinstance(metadata, dict) else {})

        recovery_id = _text(
            meta.get("recovery_id"),
            state.get("recovery_id"),
            failure.get("recovery_id"),
            default="runtime-recovery-" + _stable_fingerprint({"state": state, "failure": failure})[:12],
        )
        source_session_id = _text(
            meta.get("source_session_id"),
            state.get("session_id"),
            state.get("source_session_id"),
            failure.get("source_session_id"),
        )

        chain = self._build_chain(
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            source_state=state,
            source_failure=failure,
            metadata=meta,
        )
        execution = self._execute_recovery(chain=chain, source_state=state, metadata=meta)
        continuation = self._build_continuation(
            chain=chain,
            execution=execution,
            source_state=state,
            metadata=meta,
        )
        integration = self._seal_integration(
            chain=chain,
            execution=execution,
            continuation=continuation,
            approval_granted=approval_granted,
            metadata=meta,
        )

        final_status = _text(
            integration.get("final_status"),
            continuation.get("final_status"),
            continuation.get("status"),
            default=PIPELINE_STATUS_REVIEW_REQUIRED,
        )
        next_action = _text(
            integration.get("next_action"),
            continuation.get("next_action"),
            default="review_recovery_pipeline",
        )

        runtime_state_patch = self._build_runtime_state_patch(
            final_status=final_status,
            next_action=next_action,
            recovery_id=recovery_id,
            integration=integration,
        )

        audit_events = [
            {
                "event_type": "runtime_recovery_pipeline_started",
                "recovery_id": recovery_id,
                "source_session_id": source_session_id,
            },
            {
                "event_type": "runtime_recovery_pipeline_integrated",
                "recovery_id": recovery_id,
                "final_status": final_status,
                "next_action": next_action,
            },
        ]

        self._append_journal(
            "runtime_recovery_pipeline",
            {
                "recovery_id": recovery_id,
                "source_session_id": source_session_id,
                "final_status": final_status,
                "next_action": next_action,
            },
            metadata={"source": "runtime_recovery_pipeline"},
        )

        return RuntimeRecoveryPipelineResult(
            pipeline_id=build_recovery_pipeline_id(recovery_id, source_session_id),
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            source_failure=failure,
            chain=chain,
            execution=execution,
            continuation=continuation,
            integration_seal=integration,
            final_status=final_status,
            next_action=next_action,
            runtime_state_patch=runtime_state_patch,
            audit_events=audit_events,
        )

    def _build_chain(
        self,
        *,
        recovery_id: str,
        source_session_id: str,
        source_state: dict[str, Any],
        source_failure: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if self.chain_builder is not None:
            for method_name in ("build_chain", "create_chain", "build_recovery_chain", "recover"):
                result = _call_optional(
                    self.chain_builder,
                    method_name,
                    recovery_id=recovery_id,
                    source_session_id=source_session_id,
                    source_state=source_state,
                    source_failure=source_failure,
                    metadata=metadata,
                )
                payload = _as_dict(result)
                if payload:
                    return payload

        rollback_required = bool(
            metadata.get("rollback_required")
            or source_failure.get("rollback_required")
            or source_state.get("rollback_required")
        )
        return {
            "recovery_id": recovery_id,
            "source_session_id": source_session_id,
            "status": "planned",
            "source_failure": copy.deepcopy(source_failure),
            "rollback_required": rollback_required,
            "rollback_executed": False,
            "replay_reference": copy.deepcopy(metadata.get("replay_reference") or {}),
        }

    def _execute_recovery(
        self,
        *,
        chain: dict[str, Any],
        source_state: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if self.executor is not None:
            for method_name in ("execute_recovery", "execute", "run"):
                result = _call_optional(
                    self.executor,
                    method_name,
                    chain,
                    source_state=source_state,
                    metadata=metadata,
                )
                payload = _as_dict(result)
                if payload:
                    return payload

        rollback_required = bool(chain.get("rollback_required"))
        return {
            "recovery_id": chain.get("recovery_id", ""),
            "source_session_id": chain.get("source_session_id", ""),
            "status": "blocked" if rollback_required else "completed",
            "rollback_required": rollback_required,
            "rollback_executed": False,
        }

    def _build_continuation(
        self,
        *,
        chain: dict[str, Any],
        execution: dict[str, Any],
        source_state: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if self.continuation_builder is not None:
            for method_name in ("build_continuation", "continue_runtime", "prepare_continuation", "run"):
                result = _call_optional(
                    self.continuation_builder,
                    method_name,
                    chain=chain,
                    execution=execution,
                    source_state=source_state,
                    metadata=metadata,
                )
                payload = _as_dict(result)
                if payload:
                    return payload

        status = str(execution.get("status") or "").strip().lower()
        if status == "completed":
            return {
                "recovery_id": chain.get("recovery_id", ""),
                "source_session_id": chain.get("source_session_id", ""),
                "status": "ready_to_continue",
                "next_action": "resume_runtime",
            }
        return {
            "recovery_id": chain.get("recovery_id", ""),
            "source_session_id": chain.get("source_session_id", ""),
            "status": "blocked",
            "next_action": "wait_for_recovery_resolution",
        }

    def _seal_integration(
        self,
        *,
        chain: dict[str, Any],
        execution: dict[str, Any],
        continuation: dict[str, Any],
        approval_granted: bool,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if self.integration_sealer is not None:
            result = _call_optional(
                self.integration_sealer,
                "seal_runtime_recovery_integration",
                chain=chain,
                execution=execution,
                continuation=continuation,
                approval_granted=approval_granted,
                metadata=metadata,
            )
            payload = _as_dict(result)
            if payload:
                return payload

            if callable(self.integration_sealer):
                result = self.integration_sealer(
                    chain=chain,
                    execution=execution,
                    continuation=continuation,
                    approval_granted=approval_granted,
                    metadata=metadata,
                )
                payload = _as_dict(result)
                if payload:
                    return payload

        try:
            from core.runtime.runtime_recovery_integration import seal_runtime_recovery_integration

            return seal_runtime_recovery_integration(
                chain=chain,
                execution=execution,
                continuation=continuation,
                approval_granted=approval_granted,
                metadata=metadata,
            ).to_dict()
        except Exception:
            rollback_required = bool(chain.get("rollback_required") or execution.get("rollback_required"))
            final_status = PIPELINE_STATUS_BLOCKED if rollback_required and not approval_granted else (
                PIPELINE_STATUS_READY_TO_CONTINUE
                if str(continuation.get("status") or "") == "ready_to_continue"
                else PIPELINE_STATUS_REVIEW_REQUIRED
            )
            return {
                "recovery_id": chain.get("recovery_id", ""),
                "source_session_id": chain.get("source_session_id", ""),
                "final_status": final_status,
                "next_action": "resume_runtime" if final_status == PIPELINE_STATUS_READY_TO_CONTINUE else "review_recovery_pipeline",
                "approval_required": rollback_required,
                "approved": approval_granted,
                "sealed": True,
            }

    def _build_runtime_state_patch(
        self,
        *,
        final_status: str,
        next_action: str,
        recovery_id: str,
        integration: dict[str, Any],
    ) -> dict[str, Any]:
        if final_status == PIPELINE_STATUS_READY_TO_CONTINUE:
            status = "running"
        elif final_status == PIPELINE_STATUS_BLOCKED:
            status = "blocked"
        elif final_status == PIPELINE_STATUS_FAILED:
            status = "failed"
        else:
            status = "waiting_review"

        return {
            "status": status,
            "recovery_id": recovery_id,
            "recovery_status": final_status,
            "next_action": next_action,
            "last_recovery_integration_id": integration.get("integration_id", ""),
            "recovery_requires_approval": bool(integration.get("approval_required")),
            "recovery_approved": bool(integration.get("approved")),
        }

    def _append_journal(
        self,
        record_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.journal is None:
            return
        append = getattr(self.journal, "append", None)
        if callable(append):
            try:
                append(record_type, payload=payload, metadata=metadata or {})
            except Exception:
                return


def run_runtime_failure_recovery(
    *,
    source_state: dict[str, Any],
    source_failure: dict[str, Any] | None = None,
    approval_granted: bool = False,
    metadata: dict[str, Any] | None = None,
    pipeline: RuntimeRecoveryPipeline | None = None,
) -> RuntimeRecoveryPipelineResult:
    runtime_pipeline = pipeline if pipeline is not None else RuntimeRecoveryPipeline()
    return runtime_pipeline.run_failure_recovery(
        source_state=source_state,
        source_failure=source_failure,
        approval_granted=approval_granted,
        metadata=metadata,
    )


__all__ = [
    "PIPELINE_STATUS_READY_TO_CONTINUE",
    "PIPELINE_STATUS_REVIEW_REQUIRED",
    "PIPELINE_STATUS_BLOCKED",
    "PIPELINE_STATUS_FAILED",
    "RuntimeRecoveryPipeline",
    "RuntimeRecoveryPipelineResult",
    "build_recovery_pipeline_id",
    "run_runtime_failure_recovery",
]
