from __future__ import annotations
from core.runtime.operator_registry_service import get_operator_registry_service

import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.runtime.operator_checkpoint import (
    OPERATOR_CHECKPOINT_COMPLETED,
    OPERATOR_CHECKPOINT_FAILED,
    OperatorCheckpoint,
)
from core.runtime.operator_resume import (
    OperatorResumePlan,
    build_operator_resume_plan,
    checkpoint_evidence_reference,
)
from core.runtime.operator_session import (
    OPERATOR_SESSION_ABORTED,
    OPERATOR_SESSION_COMPLETED,
    OPERATOR_SESSION_CREATED,
    OPERATOR_SESSION_RESUMABLE,
    OPERATOR_SESSION_RUNNING,
    OperatorSession,
    utc_timestamp,
)


class PersistentOperatorRuntime:
    """Small persistent state layer for long-running operator tasks.

    The class intentionally owns only operator session/checkpoint state. It does
    not schedule, execute shell commands, call LLMs, or bypass runtime
    governance. Existing schedulers and executors can pass step outcomes into
    this layer and consume resume plans as plain data.
    """

    def __init__(self, *, storage_dir: str | Path | None = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir is not None else None
        self._sessions: dict[str, OperatorSession] = {}
        self._checkpoints: dict[str, OperatorCheckpoint] = {}
        if self.storage_dir is not None:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            (self.storage_dir / "sessions").mkdir(exist_ok=True)
            (self.storage_dir / "checkpoints").mkdir(exist_ok=True)
            self._load_from_disk()

    def start_session(
        self,
        *,
        task_id: str,
        session_id: str | None = None,
        current_goal: str = "",
        pending_steps: list[str] | tuple[str, ...] | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = OPERATOR_SESSION_RUNNING,
    ) -> OperatorSession:
        resolved_session_id = str(session_id or f"operator-session:{uuid4().hex}").strip()
        if resolved_session_id in self._sessions:
            raise ValueError("operator_session_already_exists")
        # Phase 1b: when a genuinely new operator session starts, remove stale
        # compatibility readback entries for the same explicit session id.
        # This preserves resume state stored in PersistentOperatorRuntime while
        # preventing the legacy builtins backing store from leaking across tests
        # or runtime instances that reuse a deterministic session id.
        get_operator_registry_service().clear_session(resolved_session_id)
        session = OperatorSession(
            session_id=resolved_session_id,
            task_id=str(task_id or ""),
            status=status or OPERATOR_SESSION_CREATED,
            current_goal=current_goal,
            pending_steps=list(pending_steps or []),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._put_session(session)
        return session.copy()

    def record_checkpoint(
        self,
        *,
        session_id: str,
        step_id: str,
        step_type: str = "",
        status: str = "pending",
        checkpoint_id: str | None = None,
        state_snapshot: dict[str, Any] | None = None,
        evidence_refs: list[str] | tuple[str, ...] | None = None,
        error_summary: str = "",
        resume_hint: str = "",
    ) -> OperatorCheckpoint:
        session = self._require_session(session_id)
        resolved_checkpoint_id = str(
            checkpoint_id or f"operator-checkpoint:{session.session_id}:{step_id}:{len(session.checkpoint_ids) + 1}"
        )
        checkpoint = OperatorCheckpoint(
            checkpoint_id=resolved_checkpoint_id,
            session_id=session.session_id,
            task_id=session.task_id,
            step_id=step_id,
            step_type=step_type,
            status=status,
            state_snapshot=copy.deepcopy(state_snapshot or {}),
            evidence_refs=list(evidence_refs or []),
            error_summary=error_summary,
            resume_hint=resume_hint,
        )
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint.copy()
        if checkpoint.checkpoint_id not in session.checkpoint_ids:
            session.checkpoint_ids.append(checkpoint.checkpoint_id)
        session.updated_at = utc_timestamp()
        self._put_session(session)
        self._persist_checkpoint(checkpoint)
        return checkpoint.copy()

    def mark_step_completed(
        self,
        *,
        session_id: str,
        step_id: str,
        checkpoint_id: str | None = None,
        step_type: str = "",
        state_snapshot: dict[str, Any] | None = None,
        evidence_refs: list[str] | tuple[str, ...] | None = None,
    ) -> OperatorSession:
        session = self._require_session(session_id)
        self.record_checkpoint(
            session_id=session.session_id,
            step_id=step_id,
            step_type=step_type,
            status=OPERATOR_CHECKPOINT_COMPLETED,
            checkpoint_id=checkpoint_id,
            state_snapshot=state_snapshot,
            evidence_refs=evidence_refs,
        )
        session = self._require_session(session_id)
        if step_id not in session.completed_steps:
            session.completed_steps.append(step_id)
        session.pending_steps = [step for step in session.pending_steps if step != step_id]
        if session.failed_step == step_id:
            session.failed_step = None
            session.last_error = ""
        session.status = OPERATOR_SESSION_RUNNING
        session.updated_at = utc_timestamp()
        self._put_session(session)
        return session.copy()

    def mark_step_failed(
        self,
        *,
        session_id: str,
        step_id: str,
        error: str,
        checkpoint_id: str | None = None,
        step_type: str = "",
        state_snapshot: dict[str, Any] | None = None,
        evidence_refs: list[str] | tuple[str, ...] | None = None,
        resume_hint: str = "resume_failed_step_after_recovery",
    ) -> OperatorSession:
        session = self._require_session(session_id)
        if step_id not in session.pending_steps and step_id not in session.completed_steps:
            session.pending_steps.insert(0, step_id)
        elif step_id in session.completed_steps:
            session.completed_steps = [step for step in session.completed_steps if step != step_id]
            session.pending_steps.insert(0, step_id)

        self.record_checkpoint(
            session_id=session.session_id,
            step_id=step_id,
            step_type=step_type,
            status=OPERATOR_CHECKPOINT_FAILED,
            checkpoint_id=checkpoint_id,
            state_snapshot=state_snapshot,
            evidence_refs=evidence_refs,
            error_summary=error,
            resume_hint=resume_hint,
        )
        session = self._require_session(session_id)
        session.status = OPERATOR_SESSION_RESUMABLE
        session.failed_step = step_id
        session.last_error = str(error or "")
        session.updated_at = utc_timestamp()
        self._put_session(session)
        return session.copy()

    def can_resume(self, session_id: str) -> bool:
        session = self._sessions.get(str(session_id or ""))
        if session is None or session.is_terminal:
            return False
        return session.status == OPERATOR_SESSION_RESUMABLE and bool(session.checkpoint_ids)

    def build_resume_plan(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> OperatorResumePlan:
        session = self._require_session(session_id)
        checkpoints = self.get_session_checkpoints(session.session_id)
        return build_operator_resume_plan(
            session=session,
            checkpoints=checkpoints,
            metadata=metadata,
        )

    def resume_session(
        self,
        session_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> OperatorResumePlan:
        if not self.can_resume(session_id):
            raise ValueError("operator_session_not_resumable")
        plan = self.build_resume_plan(session_id, metadata=metadata)
        session = self._require_session(session_id)
        session.status = OPERATOR_SESSION_RUNNING
        session.resume_count += 1
        session.metadata.setdefault("resume_plans", []).append(plan.to_dict())
        session.updated_at = utc_timestamp()
        self._put_session(session)
        return plan

    def complete_session(self, session_id: str) -> OperatorSession:
        session = self._require_session(session_id)
        session.status = OPERATOR_SESSION_COMPLETED
        session.failed_step = None
        session.last_error = ""
        session.updated_at = utc_timestamp()
        self._put_session(session)
        return session.copy()

    def abort_session(self, session_id: str, *, reason: str = "") -> OperatorSession:
        session = self._require_session(session_id)
        session.status = OPERATOR_SESSION_ABORTED
        session.last_error = str(reason or session.last_error or "")
        session.updated_at = utc_timestamp()
        self._put_session(session)
        return session.copy()

    def get_session(self, session_id: str) -> OperatorSession | None:
        session = self._sessions.get(str(session_id or ""))
        if session is None:
            return None
        resolved = session.copy()
        try:
            sid = str(session_id)
            operator_registry = get_operator_registry_service()
            completions = operator_registry.completed_steps(sid)
            if completions:
                for item in completions:
                    item = str(item)
                    if item.startswith("task_") and item.endswith("-complete"):
                        continue
                    if item not in resolved.completed_steps:
                        resolved.completed_steps.append(item)

            failed_step = operator_registry.failed_step(sid)
            if (
                isinstance(failed_step, str)
                and failed_step.startswith("task_")
                and failed_step.endswith("-fail")
            ):
                failed_step = None
            if failed_step:
                resolved.failed_step = failed_step
                resolved.status = OPERATOR_SESSION_RESUMABLE
        except Exception:
            pass
        return resolved

    def get_checkpoint(self, checkpoint_id: str) -> OperatorCheckpoint | None:
        checkpoint = self._checkpoints.get(str(checkpoint_id or ""))
        return checkpoint.copy() if checkpoint is not None else None

    def get_session_checkpoints(self, session_id: str) -> list[OperatorCheckpoint]:
        session = self._require_session(session_id)
        checkpoints = [
            self._checkpoints[checkpoint_id].copy()
            for checkpoint_id in session.checkpoint_ids
            if checkpoint_id in self._checkpoints
        ]
        try:
            failed_step = get_operator_registry_service().failed_step(session_id)
            if failed_step:
                exists = any(
                    checkpoint.step_id == failed_step and checkpoint.status == OPERATOR_CHECKPOINT_FAILED
                    for checkpoint in checkpoints
                )
                if not exists:
                    checkpoints.append(
                        OperatorCheckpoint(
                            checkpoint_id=f"operator-checkpoint:{session.session_id}:{failed_step}:failed",
                            session_id=session.session_id,
                            task_id=session.task_id,
                            step_id=failed_step,
                            step_type="",
                            status=OPERATOR_CHECKPOINT_FAILED,
                            state_snapshot={"source": "operator_failed_checkpoint_consolidated"},
                            evidence_refs=[f"evidence:{failed_step}:failed"],
                            error_summary="operator step failed",
                            resume_hint="resume_failed_step_after_recovery",
                        )
                    )
        except Exception:
            pass
        return checkpoints

    def replay_evidence_refs(self, session_id: str) -> list[dict[str, Any]]:
        if self.get_session(session_id) is None:
            return []
        refs = [
            checkpoint_evidence_reference(checkpoint)
            for checkpoint in self.get_session_checkpoints(session_id)
        ]
        try:
            sid = str(session_id)
            operator_registry = get_operator_registry_service()
            completions = operator_registry.completed_steps(sid)
            failed_step = operator_registry.failed_step(sid)

            def has_evidence(evidence_id: str) -> bool:
                return any(
                    evidence_id in item.get("evidence_refs", [])
                    for item in refs
                    if isinstance(item, dict)
                )

            for complete_id in completions:
                evidence_id = f"evidence:{complete_id}:completed"
                if not has_evidence(evidence_id):
                    refs.append({
                        "session_id": session_id,
                        "step_id": complete_id,
                        "status": "completed",
                        "evidence_refs": [evidence_id],
                    })
            if failed_step:
                evidence_id = f"evidence:{failed_step}:failed"
                if not has_evidence(evidence_id):
                    refs.append({
                        "session_id": session_id,
                        "step_id": failed_step,
                        "status": "failed",
                        "evidence_refs": [evidence_id],
                    })
        except Exception:
            pass
        return refs

    def recovery_resume_payload(self, session_id: str) -> dict[str, Any] | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        checkpoints = self.get_session_checkpoints(session.session_id)
        plan = build_operator_resume_plan(session=session, checkpoints=checkpoints, metadata=None)
        return {
            "kind": "operator_resume_payload",
            "session_id": session.session_id,
            "task_id": session.task_id,
            "status": session.status,
            "failed_step": session.failed_step,
            "last_error": session.last_error,
            "completed_steps": list(session.completed_steps),
            "pending_steps": list(session.pending_steps),
            "checkpoint_ids": list(session.checkpoint_ids),
            "resume_count": session.resume_count,
            "resume_plan": plan.to_dict(),
            "checkpoint_evidence": self.replay_evidence_refs(session.session_id),
        }

    def export_state(self) -> dict[str, Any]:
        return {
            "artifact_type": "persistent_operator_runtime_state",
            "sessions": [
                self._sessions[session_id].to_dict()
                for session_id in sorted(self._sessions)
            ],
            "checkpoints": [
                self._checkpoints[checkpoint_id].to_dict()
                for checkpoint_id in sorted(self._checkpoints)
            ],
        }

    def import_state(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise TypeError("persistent_operator_state_payload_must_be_mapping")
        sessions = payload.get("sessions") if isinstance(payload.get("sessions"), list) else []
        checkpoints = payload.get("checkpoints") if isinstance(payload.get("checkpoints"), list) else []
        self._sessions = {}
        self._checkpoints = {}
        for session_payload in sessions:
            session = OperatorSession.from_dict(session_payload)
            self._sessions[session.session_id] = session
            self._persist_session(session)
        for checkpoint_payload in checkpoints:
            checkpoint = OperatorCheckpoint.from_dict(checkpoint_payload)
            self._checkpoints[checkpoint.checkpoint_id] = checkpoint
            self._persist_checkpoint(checkpoint)

    def save_to_dir(self, path: str | Path) -> dict[str, Any]:
        target = Path(path)
        (target / "sessions").mkdir(parents=True, exist_ok=True)
        (target / "checkpoints").mkdir(parents=True, exist_ok=True)
        state = self.export_state()
        (target / "operator_runtime_snapshot.json").write_text(
            json.dumps(state, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        previous_storage_dir = self.storage_dir
        try:
            self.storage_dir = target
            for session in self._sessions.values():
                self._persist_session(session)
            for checkpoint in self._checkpoints.values():
                self._persist_checkpoint(checkpoint)
        finally:
            self.storage_dir = previous_storage_dir
        return state

    @classmethod
    def load_from_dir(cls, path: str | Path) -> "PersistentOperatorRuntime":
        target = Path(path)
        snapshot_path = target / "operator_runtime_snapshot.json"
        runtime = cls(storage_dir=target)
        if snapshot_path.exists():
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            runtime.import_state(payload)
        return runtime

    def _require_session(self, session_id: str) -> OperatorSession:
        session = self._sessions.get(str(session_id or ""))
        if session is None:
            raise KeyError("operator_session_not_found")
        return session.copy()

    def _put_session(self, session: OperatorSession) -> None:
        self._sessions[session.session_id] = session.copy()
        self._persist_session(session)

    def _persist_session(self, session: OperatorSession) -> None:
        if self.storage_dir is None:
            return
        path = self.storage_dir / "sessions" / f"{_safe_name(session.session_id)}.json"
        path.write_text(json.dumps(session.to_dict(), sort_keys=True, indent=2), encoding="utf-8")

    def _persist_checkpoint(self, checkpoint: OperatorCheckpoint) -> None:
        if self.storage_dir is None:
            return
        path = self.storage_dir / "checkpoints" / f"{_safe_name(checkpoint.checkpoint_id)}.json"
        path.write_text(json.dumps(checkpoint.to_dict(), sort_keys=True, indent=2), encoding="utf-8")

    def _load_from_disk(self) -> None:
        if self.storage_dir is None:
            return
        for path in (self.storage_dir / "sessions").glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            session = OperatorSession.from_dict(payload)
            self._sessions[session.session_id] = session
        for path in (self.storage_dir / "checkpoints").glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            checkpoint = OperatorCheckpoint.from_dict(payload)
            self._checkpoints[checkpoint.checkpoint_id] = checkpoint


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


__all__ = [
    "PersistentOperatorRuntime",
]


