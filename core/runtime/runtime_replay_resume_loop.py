from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    from core.runtime.runtime_replay_recovery import (
        REPLAY_RECOVERY_STATUS_BLOCKED,
        REPLAY_RECOVERY_STATUS_CONTINUABLE,
        REPLAY_RECOVERY_STATUS_FAILED,
        reconstruct_runtime_failure_from_replay,
    )
except Exception:
    REPLAY_RECOVERY_STATUS_CONTINUABLE = "continuable"
    REPLAY_RECOVERY_STATUS_BLOCKED = "blocked"
    REPLAY_RECOVERY_STATUS_FAILED = "failed"

    def reconstruct_runtime_failure_from_replay(**kwargs):
        raise RuntimeError("runtime_replay_recovery_unavailable")


RESUME_LOOP_STATUS_RESUMED = "resumed"
RESUME_LOOP_STATUS_BLOCKED = "blocked"
RESUME_LOOP_STATUS_FAILED = "failed"
RESUME_LOOP_STATUS_REPLAY_INVALID = "replay_invalid"


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _extract_resume_cursor(events: list[dict[str, Any]]) -> int:
    failed_index = 0

    for event in events:
        if not isinstance(event, dict):
            continue

        event_type = str(event.get("event_type") or "").strip().lower()

        if event_type in {
            "step_failed",
            "mutation_failed",
            "tool_failed",
        }:
            failed_index = _safe_int(event.get("step_index"), failed_index)

    return failed_index


@dataclass(frozen=True)
class RuntimeReplayResumeLoopResult:
    resume_id: str
    recovery_id: str
    source_session_id: str
    status: str
    resumed: bool
    resume_cursor: int
    replay_recovery: dict[str, Any]
    replay_cursor_patch: dict[str, Any]
    resumed_runtime_state: dict[str, Any]
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
            "artifact_type": "runtime_replay_resume_loop_result",
            "resume_id": self.resume_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "status": self.status,
            "resumed": self.resumed,
            "resume_cursor": self.resume_cursor,
            "replay_recovery": copy.deepcopy(self.replay_recovery),
            "replay_cursor_patch": copy.deepcopy(self.replay_cursor_patch),
            "resumed_runtime_state": copy.deepcopy(self.resumed_runtime_state),
            "audit_events": copy.deepcopy(self.audit_events),
            "created_at": self.created_at,
        }

        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()

        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(
            self.to_dict(include_fingerprint=False)
        )


def build_resume_loop_id(
    recovery_id: str,
    source_session_id: str = "",
) -> str:
    seed = {
        "kind": "runtime_replay_resume_loop",
        "recovery_id": str(recovery_id or ""),
        "source_session_id": str(source_session_id or ""),
    }
    return "runtime-replay-resume-loop-" + _stable_fingerprint(seed)[:16]


class RuntimeReplayResumeLoop:
    """
    Replay cursor reconstruction + loop resume bridge.

    This layer rebuilds the execution cursor from replay evidence before
    the execution loop resumes.
    """

    def rebuild_and_resume_loop(
        self,
        *,
        recovery_id: str,
        source_session_id: str,
        runtime_state: dict[str, Any],
        failure: dict[str, Any],
        replay_reference: dict[str, Any],
        replay_events: list[dict[str, Any]],
    ) -> RuntimeReplayResumeLoopResult:
        replay_result = reconstruct_runtime_failure_from_replay(
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            failure=failure,
            replay_reference=replay_reference,
            replay_events=replay_events,
        )

        replay_payload = _as_dict(replay_result)

        replay_status = str(replay_payload.get("status") or "").strip().lower()

        if replay_status == REPLAY_RECOVERY_STATUS_BLOCKED:
            return self._build_result(
                recovery_id=recovery_id,
                source_session_id=source_session_id,
                status=RESUME_LOOP_STATUS_BLOCKED,
                resumed=False,
                resume_cursor=_extract_resume_cursor(replay_events),
                replay_recovery=replay_payload,
                replay_cursor_patch={},
                resumed_runtime_state=copy.deepcopy(runtime_state),
            )

        if replay_status == REPLAY_RECOVERY_STATUS_FAILED:
            return self._build_result(
                recovery_id=recovery_id,
                source_session_id=source_session_id,
                status=RESUME_LOOP_STATUS_REPLAY_INVALID,
                resumed=False,
                resume_cursor=_extract_resume_cursor(replay_events),
                replay_recovery=replay_payload,
                replay_cursor_patch={},
                resumed_runtime_state=copy.deepcopy(runtime_state),
            )

        if replay_status != REPLAY_RECOVERY_STATUS_CONTINUABLE:
            return self._build_result(
                recovery_id=recovery_id,
                source_session_id=source_session_id,
                status=RESUME_LOOP_STATUS_FAILED,
                resumed=False,
                resume_cursor=_extract_resume_cursor(replay_events),
                replay_recovery=replay_payload,
                replay_cursor_patch={},
                resumed_runtime_state=copy.deepcopy(runtime_state),
            )

        resume_cursor = _extract_resume_cursor(replay_events)

        cursor_patch = {
            "status": "running",
            "current_step_index": resume_cursor,
            "next_action": "resume_from_replay_cursor",
            "replay_resume": {
                "resume_cursor": resume_cursor,
                "resume_reason": "replay_reconstruction_verified",
                "resumed_at": utc_timestamp(),
            },
        }

        resumed_state = copy.deepcopy(runtime_state)
        resumed_state.update(cursor_patch)

        return self._build_result(
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            status=RESUME_LOOP_STATUS_RESUMED,
            resumed=True,
            resume_cursor=resume_cursor,
            replay_recovery=replay_payload,
            replay_cursor_patch=cursor_patch,
            resumed_runtime_state=resumed_state,
        )

    def _build_result(
        self,
        *,
        recovery_id: str,
        source_session_id: str,
        status: str,
        resumed: bool,
        resume_cursor: int,
        replay_recovery: dict[str, Any],
        replay_cursor_patch: dict[str, Any],
        resumed_runtime_state: dict[str, Any],
    ) -> RuntimeReplayResumeLoopResult:
        return RuntimeReplayResumeLoopResult(
            resume_id=build_resume_loop_id(
                recovery_id,
                source_session_id,
            ),
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            status=status,
            resumed=resumed,
            resume_cursor=resume_cursor,
            replay_recovery=copy.deepcopy(replay_recovery),
            replay_cursor_patch=copy.deepcopy(replay_cursor_patch),
            resumed_runtime_state=copy.deepcopy(resumed_runtime_state),
            audit_events=[
                {
                    "event_type": "runtime_replay_resume_loop",
                    "recovery_id": recovery_id,
                    "status": status,
                    "resume_cursor": resume_cursor,
                    "resumed": resumed,
                }
            ],
        )


def rebuild_runtime_loop_from_replay(
    *,
    recovery_id: str,
    source_session_id: str,
    runtime_state: dict[str, Any],
    failure: dict[str, Any],
    replay_reference: dict[str, Any],
    replay_events: list[dict[str, Any]],
) -> RuntimeReplayResumeLoopResult:
    runtime = RuntimeReplayResumeLoop()

    return runtime.rebuild_and_resume_loop(
        recovery_id=recovery_id,
        source_session_id=source_session_id,
        runtime_state=runtime_state,
        failure=failure,
        replay_reference=replay_reference,
        replay_events=replay_events,
    )


__all__ = [
    "RESUME_LOOP_STATUS_RESUMED",
    "RESUME_LOOP_STATUS_BLOCKED",
    "RESUME_LOOP_STATUS_FAILED",
    "RESUME_LOOP_STATUS_REPLAY_INVALID",
    "RuntimeReplayResumeLoop",
    "RuntimeReplayResumeLoopResult",
    "build_resume_loop_id",
    "rebuild_runtime_loop_from_replay",
]
