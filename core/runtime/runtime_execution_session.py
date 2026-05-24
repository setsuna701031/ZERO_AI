from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from core.runtime.runtime_lifecycle_pipeline import (
    RuntimeLifecyclePipeline,
    RuntimeLifecycleRecord,
)
from core.runtime.runtime_consistency import build_runtime_state_consistency
from core.runtime.runtime_closure import build_runtime_closure_fields
from core.runtime.runtime_recovery_readiness import build_runtime_recovery_readiness_fields


@dataclass(frozen=True)
class RuntimeExecutionSession:
    session_id: str
    lifecycle_id: str
    parent_session_id: str | None
    replay_group: str | None
    source: str
    payload: Any
    metadata: Any
    sequence: int
    lifecycle_records: list[RuntimeLifecycleRecord]
    execution_evidence: dict[str, Any] = None  # type: ignore[assignment]
    authority_metadata: dict[str, Any] = None  # type: ignore[assignment]
    consistency_metadata: dict[str, Any] = None  # type: ignore[assignment]
    closure_metadata: dict[str, Any] = None  # type: ignore[assignment]
    recovery_metadata: dict[str, Any] = None  # type: ignore[assignment]
    replay_metadata: dict[str, Any] = None  # type: ignore[assignment]


class RuntimeExecutionSessionRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeExecutionSessionManager:
    def __init__(
        self,
        lifecycle_pipeline: RuntimeLifecyclePipeline | None = None,
    ) -> None:
        self.lifecycle_pipeline = (
            lifecycle_pipeline
            if lifecycle_pipeline is not None
            else RuntimeLifecyclePipeline()
        )
        self._sessions: dict[str, RuntimeExecutionSession] = {}
        self._sequence = 0

    def create_session(
        self,
        session_id: str,
        lifecycle_id: str,
        source: str = "runtime",
        parent_session_id: str | None = None,
        replay_group: str | None = None,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionSession:
        session_id = self._validate_session_id(session_id)
        lifecycle_id = self._validate_lifecycle_id(lifecycle_id)

        if session_id in self._sessions:
            raise RuntimeExecutionSessionRejected(
                f"runtime execution session already exists: {session_id!r}"
            )

        if (
            parent_session_id is not None
            and parent_session_id not in self._sessions
        ):
            raise RuntimeExecutionSessionRejected(
                "runtime execution session parent does not exist: "
                f"{parent_session_id!r}"
            )

        self._call_lifecycle(
            self.lifecycle_pipeline.queue,
            lifecycle_id,
            payload=payload,
            metadata=metadata,
        )

        self._sequence += 1
        session = RuntimeExecutionSession(
            session_id=session_id,
            lifecycle_id=lifecycle_id,
            parent_session_id=parent_session_id,
            replay_group=replay_group,
            source=source,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            lifecycle_records=self.lifecycle_pipeline.get_records(lifecycle_id),
            execution_evidence=self._session_execution_evidence(
                session_id=session_id,
                lifecycle_id=lifecycle_id,
                source=source,
                metadata=metadata,
            ),
            authority_metadata=self._session_authority_metadata(
                source=source,
                metadata=metadata,
            ),
            consistency_metadata=self._session_consistency_metadata(
                session_id=session_id,
                lifecycle_id=lifecycle_id,
                source=source,
                metadata=metadata,
            ),
            closure_metadata=self._session_closure_metadata(
                session_id=session_id,
                lifecycle_id=lifecycle_id,
                source=source,
                metadata=metadata,
                lifecycle_status="queued",
            ),
            recovery_metadata=self._session_recovery_metadata(
                session_id=session_id,
                lifecycle_id=lifecycle_id,
                source=source,
                metadata=metadata,
                lifecycle_status="queued",
            ),
            replay_metadata=self._session_replay_metadata(
                session_id=session_id,
                lifecycle_id=lifecycle_id,
                source=source,
                metadata=metadata,
                lifecycle_status="queued",
            ),
        )
        self._sessions[session_id] = session
        return self._copy_session(session)

    def start_session(
        self,
        session_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionSession:
        session = self._get_existing_session(session_id)
        self._call_lifecycle(
            self.lifecycle_pipeline.dispatch,
            session.lifecycle_id,
            payload=payload,
            metadata=metadata,
        )
        self._call_lifecycle(
            self.lifecycle_pipeline.start_execution,
            session.lifecycle_id,
            payload=payload,
            metadata=metadata,
        )
        return self._refresh_session(session_id)

    def complete_session(
        self,
        session_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionSession:
        session = self._get_existing_session(session_id)
        self._call_lifecycle(
            self.lifecycle_pipeline.complete_execution,
            session.lifecycle_id,
            payload=payload,
            metadata=metadata,
        )
        return self._refresh_session(session_id)

    def fail_session(
        self,
        session_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionSession:
        session = self._get_existing_session(session_id)
        self._call_lifecycle(
            self.lifecycle_pipeline.fail_execution,
            session.lifecycle_id,
            payload=payload,
            metadata=metadata,
        )
        return self._refresh_session(session_id)

    def incident_session(
        self,
        session_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionSession:
        session = self._get_existing_session(session_id)
        self._call_lifecycle(
            self.lifecycle_pipeline.incident,
            session.lifecycle_id,
            payload=payload,
            metadata=metadata,
        )
        return self._refresh_session(session_id)

    def repair_session(
        self,
        session_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionSession:
        session = self._get_existing_session(session_id)
        self._call_lifecycle(
            self.lifecycle_pipeline.repair,
            session.lifecycle_id,
            payload=payload,
            metadata=metadata,
        )
        return self._refresh_session(session_id)

    def replay_session(
        self,
        session_id: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionSession:
        session = self._get_existing_session(session_id)
        self._call_lifecycle(
            self.lifecycle_pipeline.replay,
            session.lifecycle_id,
            payload=payload,
            metadata=metadata,
        )
        return self._refresh_session(session_id)

    def get_session(self, session_id: str) -> RuntimeExecutionSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None

        return self._copy_session(session)

    def get_sessions(
        self,
        replay_group: str | None = None,
    ) -> list[RuntimeExecutionSession]:
        sessions = list(self._sessions.values())
        if replay_group is not None:
            sessions = [
                session
                for session in sessions
                if session.replay_group == replay_group
            ]

        return [self._copy_session(session) for session in sessions]

    def get_lineage(self, session_id: str) -> list[RuntimeExecutionSession]:
        lineage = []
        current = self._get_existing_session(session_id)

        while current is not None:
            lineage.append(current)
            if current.parent_session_id is None:
                break
            current = self._sessions[current.parent_session_id]

        return [
            self._copy_session(session)
            for session in reversed(lineage)
        ]

    def clear(self) -> None:
        self._sessions.clear()
        self._sequence = 0
        self.lifecycle_pipeline.clear()

    def _call_lifecycle(self, operation, lifecycle_id: str, payload: Any, metadata: Any):
        try:
            return operation(lifecycle_id, payload=payload, metadata=metadata)
        except Exception as exc:
            raise RuntimeExecutionSessionRejected(
                "runtime execution session lifecycle operation failed",
                original_exception=exc,
            ) from exc

    def _refresh_session(self, session_id: str) -> RuntimeExecutionSession:
        session = self._get_existing_session(session_id)
        records = self.lifecycle_pipeline.get_records(session.lifecycle_id)
        refreshed = replace(
            session,
            lifecycle_records=records,
            consistency_metadata=self._session_consistency_metadata(
                session_id=session.session_id,
                lifecycle_id=session.lifecycle_id,
                source=session.source,
                metadata=session.metadata,
                lifecycle_status=records[-1].phase if records else "queued",
            ),
            closure_metadata=self._session_closure_metadata(
                session_id=session.session_id,
                lifecycle_id=session.lifecycle_id,
                source=session.source,
                metadata=session.metadata,
                lifecycle_status=records[-1].phase if records else "queued",
            ),
            recovery_metadata=self._session_recovery_metadata(
                session_id=session.session_id,
                lifecycle_id=session.lifecycle_id,
                source=session.source,
                metadata=session.metadata,
                lifecycle_status=records[-1].phase if records else "queued",
            ),
            replay_metadata=self._session_replay_metadata(
                session_id=session.session_id,
                lifecycle_id=session.lifecycle_id,
                source=session.source,
                metadata=session.metadata,
                lifecycle_status=records[-1].phase if records else "queued",
            ),
        )
        self._sessions[session_id] = refreshed
        return self._copy_session(refreshed)

    def _get_existing_session(self, session_id: str) -> RuntimeExecutionSession:
        session_id = self._validate_session_id(session_id)
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeExecutionSessionRejected(
                f"runtime execution session does not exist: {session_id!r}"
            )

        return session

    def _copy_session(
        self,
        session: RuntimeExecutionSession,
    ) -> RuntimeExecutionSession:
        return replace(
            session,
            lifecycle_records=list(session.lifecycle_records),
            execution_evidence=dict(session.execution_evidence or {}),
            authority_metadata=dict(session.authority_metadata or {}),
            consistency_metadata=dict(session.consistency_metadata or {}),
            closure_metadata=dict(session.closure_metadata or {}),
            recovery_metadata=dict(session.recovery_metadata or {}),
            replay_metadata=dict(session.replay_metadata or {}),
        )

    def _validate_session_id(self, session_id: str) -> str:
        if not str(session_id or "").strip():
            raise RuntimeExecutionSessionRejected(
                "runtime execution session_id is required"
            )

        return session_id

    def _validate_lifecycle_id(self, lifecycle_id: str) -> str:
        if not str(lifecycle_id or "").strip():
            raise RuntimeExecutionSessionRejected(
                "runtime execution lifecycle_id is required"
            )

        return lifecycle_id

    def _session_execution_evidence(
        self,
        *,
        session_id: str,
        lifecycle_id: str,
        source: str,
        metadata: Any,
    ) -> dict[str, Any]:
        metadata_mapping = metadata if isinstance(metadata, dict) else {}
        evidence = metadata_mapping.get("execution_evidence")
        if isinstance(evidence, dict):
            payload = dict(evidence)
        else:
            payload = {}
        payload.setdefault("execution_id", lifecycle_id)
        payload.setdefault("execution_source", str(source or "runtime_execution_session"))
        payload.setdefault("execution_status", "queued")
        payload.setdefault("execution_legality", "not_executed")
        payload.setdefault("timestamp", "")
        payload.setdefault("runtime_session_id", session_id)
        return payload

    def _session_authority_metadata(
        self,
        *,
        source: str,
        metadata: Any,
    ) -> dict[str, Any]:
        metadata_mapping = metadata if isinstance(metadata, dict) else {}
        authority = metadata_mapping.get("authority_seal")
        if isinstance(authority, dict):
            payload = dict(authority)
        else:
            payload = {}
        payload.setdefault("authority_source", str(source or "runtime_execution_session"))
        payload.setdefault("authority_scope", "runtime_execution_session")
        payload.setdefault("authority_status", "allowed")
        payload.setdefault("authority_reason", "runtime_execution_session_authorized")
        payload.setdefault("ownership_source", "core.runtime.runtime_execution_session")
        payload.setdefault("ownership_scope", "runtime_execution_session")
        return payload

    def _session_consistency_metadata(
        self,
        *,
        session_id: str,
        lifecycle_id: str,
        source: str,
        metadata: Any,
        lifecycle_status: str = "queued",
    ) -> dict[str, Any]:
        metadata_mapping = metadata if isinstance(metadata, dict) else {}
        consistency = metadata_mapping.get("consistency_seal")
        if isinstance(consistency, dict):
            return dict(consistency)
        return build_runtime_state_consistency(
            {
                **metadata_mapping,
                "runtime_session_id": session_id,
                "lifecycle_status": lifecycle_status,
                "execution_evidence": self._session_execution_evidence(
                    session_id=session_id,
                    lifecycle_id=lifecycle_id,
                    source=source,
                    metadata=metadata,
                ),
                "authority_seal": self._session_authority_metadata(
                    source=source,
                    metadata=metadata,
                ),
            }
        )

    def _session_closure_metadata(
        self,
        *,
        session_id: str,
        lifecycle_id: str,
        source: str,
        metadata: Any,
        lifecycle_status: str,
    ) -> dict[str, Any]:
        metadata_mapping = metadata if isinstance(metadata, dict) else {}
        return build_runtime_closure_fields(
            {
                **metadata_mapping,
                "lifecycle_status": lifecycle_status,
                "execution_status": lifecycle_status,
                "source": source or "runtime_execution_session",
            },
            artifact_type="runtime_execution_session",
            artifact_id=session_id or lifecycle_id,
            finalized_by=source or "runtime_execution_session",
        )

    def _session_recovery_metadata(
        self,
        *,
        session_id: str,
        lifecycle_id: str,
        source: str,
        metadata: Any,
        lifecycle_status: str,
    ) -> dict[str, Any]:
        metadata_mapping = metadata if isinstance(metadata, dict) else {}
        execution_evidence = self._session_execution_evidence(
            session_id=session_id,
            lifecycle_id=lifecycle_id,
            source=source,
            metadata=metadata,
        )
        authority = self._session_authority_metadata(source=source, metadata=metadata)
        consistency = self._session_consistency_metadata(
            session_id=session_id,
            lifecycle_id=lifecycle_id,
            source=source,
            metadata=metadata,
            lifecycle_status=lifecycle_status,
        )
        closure = self._session_closure_metadata(
            session_id=session_id,
            lifecycle_id=lifecycle_id,
            source=source,
            metadata=metadata,
            lifecycle_status=lifecycle_status,
        )
        return build_runtime_recovery_readiness_fields(
            {
                **metadata_mapping,
                "runtime_session_id": session_id,
                "lifecycle_status": lifecycle_status,
                "execution_evidence": execution_evidence,
                "authority_seal": authority,
                "consistency_seal": consistency,
                "runtime_closure": closure,
                "closure_evidence": closure.get("closure_evidence"),
            },
            artifact_type="runtime_execution_session",
            artifact_id=session_id or lifecycle_id,
        )

    def _session_replay_metadata(
        self,
        *,
        session_id: str,
        lifecycle_id: str,
        source: str,
        metadata: Any,
        lifecycle_status: str,
    ) -> dict[str, Any]:
        recovery = self._session_recovery_metadata(
            session_id=session_id,
            lifecycle_id=lifecycle_id,
            source=source,
            metadata=metadata,
            lifecycle_status=lifecycle_status,
        )
        return {
            key: recovery[key]
            for key in (
                "replay_admissible",
                "deterministic_replay",
                "replay_block_reason",
                "replay_evidence",
                "replay_state_hash",
                "replay_snapshot",
            )
            if key in recovery
        }
