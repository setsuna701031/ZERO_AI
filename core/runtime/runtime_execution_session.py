from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from core.runtime.runtime_lifecycle_pipeline import (
    RuntimeLifecyclePipeline,
    RuntimeLifecycleRecord,
)


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
        refreshed = replace(
            session,
            lifecycle_records=self.lifecycle_pipeline.get_records(
                session.lifecycle_id
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
        return replace(session, lifecycle_records=list(session.lifecycle_records))

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
