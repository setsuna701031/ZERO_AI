from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
from typing import Any, Callable

from core.runtime.runtime_execution_session import (
    RuntimeExecutionSession,
    RuntimeExecutionSessionManager,
)


@dataclass(frozen=True)
class RuntimeReplayRecord:
    replay_id: str
    source_session_id: str
    lifecycle_id: str
    phase: str
    source: str
    payload: Any
    metadata: Any
    original_sequence: int
    replay_sequence: int


@dataclass(frozen=True)
class RuntimeReplayIntegrityRecord:
    original_execution_id: str
    replay_execution_id: str
    original_result_hash: str
    replay_result_hash: str
    integrity_verified: bool
    mismatch_reason: str | None = None


@dataclass(frozen=True)
class RuntimeReplaySession:
    replay_id: str
    source_session_id: str | None
    replay_group: str | None
    records: list[RuntimeReplayRecord]
    sequence: int
    payload: Any
    metadata: Any
    verified: bool
    integrity_records: list[RuntimeReplayIntegrityRecord] = field(default_factory=list)


class RuntimeReplayRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeReplayEngine:
    def __init__(
        self,
        session_manager: RuntimeExecutionSessionManager | None = None,
    ) -> None:
        self.session_manager = (
            session_manager
            if session_manager is not None
            else RuntimeExecutionSessionManager()
        )
        self._replays: dict[str, RuntimeReplaySession] = {}
        self._sequence = 0

    def replay_session(
        self,
        replay_id: str,
        source_session_id: str,
        payload: Any = None,
        metadata: Any = None,
        handler: Callable[[RuntimeReplayRecord], None] | None = None,
    ) -> RuntimeReplaySession:
        replay_id = self._validate_replay_id(replay_id)
        self._reject_duplicate_replay_id(replay_id)

        session = self._get_source_session(source_session_id)
        records = self._build_records(replay_id, [session])
        return self._store_replay(
            replay_id=replay_id,
            source_session_id=session.session_id,
            replay_group=session.replay_group,
            records=records,
            payload=payload,
            metadata=metadata,
            handler=handler,
        )

    def replay_group(
        self,
        replay_id: str,
        replay_group: str,
        payload: Any = None,
        metadata: Any = None,
        handler: Callable[[RuntimeReplayRecord], None] | None = None,
    ) -> RuntimeReplaySession:
        replay_id = self._validate_replay_id(replay_id)
        self._reject_duplicate_replay_id(replay_id)

        sessions = self._get_group_sessions(replay_group)
        records = self._build_records(replay_id, sessions)
        return self._store_replay(
            replay_id=replay_id,
            source_session_id=None,
            replay_group=replay_group,
            records=records,
            payload=payload,
            metadata=metadata,
            handler=handler,
        )

    def get_replay(self, replay_id: str) -> RuntimeReplaySession | None:
        replay = self._replays.get(replay_id)
        if replay is None:
            return None

        return self._copy_replay(replay)

    def get_replays(self) -> list[RuntimeReplaySession]:
        return [
            self._copy_replay(replay)
            for replay in self._replays.values()
        ]

    def record_execution_result_integrity(
        self,
        *,
        original_execution_id: str,
        replay_execution_id: str,
        original_result: Any,
        replay_result: Any,
    ) -> RuntimeReplayIntegrityRecord:
        original_hash = self._hash_result(original_result)
        replay_hash = self._hash_result(replay_result)
        verified = original_hash == replay_hash
        return RuntimeReplayIntegrityRecord(
            original_execution_id=str(original_execution_id),
            replay_execution_id=str(replay_execution_id),
            original_result_hash=original_hash,
            replay_result_hash=replay_hash,
            integrity_verified=verified,
            mismatch_reason=None if verified else "result_hash_mismatch",
        )

    def attach_integrity_record(
        self,
        replay_id: str,
        integrity_record: RuntimeReplayIntegrityRecord,
    ) -> RuntimeReplaySession:
        replay = self._replays.get(replay_id)
        if replay is None:
            raise RuntimeReplayRejected(
                "runtime replay target does not exist: "
                f"{replay_id!r}"
            )

        updated = replace(
            replay,
            integrity_records=[
                *replay.integrity_records,
                integrity_record,
            ],
            verified=replay.verified and integrity_record.integrity_verified,
        )
        self._replays[replay_id] = updated
        return self._copy_replay(updated)

    def clear(self) -> None:
        self._replays.clear()
        self._sequence = 0

    def _store_replay(
        self,
        replay_id: str,
        source_session_id: str | None,
        replay_group: str | None,
        records: list[RuntimeReplayRecord],
        payload: Any,
        metadata: Any,
        handler: Callable[[RuntimeReplayRecord], None] | None,
    ) -> RuntimeReplaySession:
        if handler is not None:
            for record in records:
                try:
                    handler(record)
                except Exception as exc:
                    raise RuntimeReplayRejected(
                        "runtime replay handler failed",
                        original_exception=exc,
                    ) from exc

        self._sequence += 1
        replay = RuntimeReplaySession(
            replay_id=replay_id,
            source_session_id=source_session_id,
            replay_group=replay_group,
            records=list(records),
            sequence=self._sequence,
            payload=payload,
            metadata=metadata,
            verified=True,
            integrity_records=[],
        )
        self._replays[replay_id] = replay
        return self._copy_replay(replay)

    def _build_records(
        self,
        replay_id: str,
        sessions: list[RuntimeExecutionSession],
    ) -> list[RuntimeReplayRecord]:
        replay_records = []
        replay_sequence = 0

        for session in sorted(sessions, key=lambda item: item.sequence):
            for lifecycle_record in sorted(
                session.lifecycle_records,
                key=lambda item: item.sequence,
            ):
                replay_sequence += 1
                replay_records.append(
                    RuntimeReplayRecord(
                        replay_id=replay_id,
                        source_session_id=session.session_id,
                        lifecycle_id=lifecycle_record.lifecycle_id,
                        phase=lifecycle_record.phase,
                        source=lifecycle_record.source,
                        payload=lifecycle_record.payload,
                        metadata=lifecycle_record.metadata,
                        original_sequence=lifecycle_record.sequence,
                        replay_sequence=replay_sequence,
                    )
                )

        return replay_records

    def _get_source_session(self, source_session_id: str) -> RuntimeExecutionSession:
        try:
            session = self.session_manager.get_session(source_session_id)
        except Exception as exc:
            raise RuntimeReplayRejected(
                "runtime replay source session lookup failed",
                original_exception=exc,
            ) from exc

        if session is None:
            raise RuntimeReplayRejected(
                "runtime replay source session does not exist: "
                f"{source_session_id!r}"
            )

        return session

    def _get_group_sessions(self, replay_group: str) -> list[RuntimeExecutionSession]:
        try:
            sessions = self.session_manager.get_sessions(replay_group=replay_group)
        except Exception as exc:
            raise RuntimeReplayRejected(
                "runtime replay group lookup failed",
                original_exception=exc,
            ) from exc

        if not sessions:
            raise RuntimeReplayRejected(
                "runtime replay group has no sessions: "
                f"{replay_group!r}"
            )

        return sessions

    def _validate_replay_id(self, replay_id: str) -> str:
        if not str(replay_id or "").strip():
            raise RuntimeReplayRejected("runtime replay_id is required")

        return replay_id

    def _reject_duplicate_replay_id(self, replay_id: str) -> None:
        if replay_id in self._replays:
            raise RuntimeReplayRejected(
                f"runtime replay already exists: {replay_id!r}"
            )

    def _copy_replay(self, replay: RuntimeReplaySession) -> RuntimeReplaySession:
        return replace(
            replay,
            records=list(replay.records),
            integrity_records=list(replay.integrity_records),
        )

    def _hash_result(self, result: Any) -> str:
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        payload = json.dumps(
            result,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
