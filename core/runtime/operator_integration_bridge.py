from __future__ import annotations
from core.runtime.operator_registry_service import get_operator_registry_service

import copy
import hashlib
import json
from typing import Any

from core.runtime.operator_checkpoint import OPERATOR_CHECKPOINT_RUNNING
from core.runtime.operator_session import OperatorSession
from core.runtime.persistent_operator import PersistentOperatorRuntime


class OperatorIntegrationBridge:
    """Narrow adapter from step outcomes into PersistentOperatorRuntime.

    This bridge does not execute steps or own scheduler state. It only normalizes
    task/step/result payloads and forwards them into the persistent operator
    session/checkpoint contract.
    """

    def __init__(self, operator_runtime: PersistentOperatorRuntime | None = None) -> None:
        self.operator_runtime = operator_runtime if operator_runtime is not None else PersistentOperatorRuntime()

    def on_session_start(
        self,
        task_id: str,
        goal: str,
        pending_steps: Any,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> OperatorSession:
        normalized_steps = [self.step_id_for(step) for step in _list(pending_steps)]
        return self.operator_runtime.start_session(
            task_id=task_id,
            session_id=session_id,
            current_goal=goal,
            pending_steps=normalized_steps,
            metadata=copy.deepcopy(metadata or {}),
        )

    def on_step_started(self, session_id: str, step: Any) -> Any:
        normalized = self.normalize_step(step)
        return self.operator_runtime.record_checkpoint(
            session_id=session_id,
            step_id=normalized["step_id"],
            step_type=normalized["step_type"],
            status=OPERATOR_CHECKPOINT_RUNNING,
            state_snapshot={
                "phase": "started",
                "step": normalized["summary"],
            },
        )

    def on_step_completed(
        self,
        session_id: str,
        step: Any,
        result: Any = None,
        evidence_refs: list[str] | tuple[str, ...] | None = None,
    ) -> OperatorSession:
        normalized = self.normalize_step(step)
        refs = self._evidence_refs(evidence_refs=evidence_refs, result=result)
        return self.operator_runtime.mark_step_completed(
            session_id=session_id,
            step_id=normalized["step_id"],
            step_type=normalized["step_type"],
            state_snapshot={
                "phase": "completed",
                "step": normalized["summary"],
                "result_summary": _summary(result),
            },
            evidence_refs=refs,
        )

    def on_step_failed(
        self,
        session_id: str,
        step: Any,
        error: Any,
        evidence_refs: list[str] | tuple[str, ...] | None = None,
        resume_hint: str | None = None,
    ) -> OperatorSession:
        normalized = self.normalize_step(step)
        error_summary = _error_summary(error)
        refs = self._evidence_refs(evidence_refs=evidence_refs, result=error)
        return self.operator_runtime.mark_step_failed(
            session_id=session_id,
            step_id=normalized["step_id"],
            step_type=normalized["step_type"],
            error=error_summary,
            state_snapshot={
                "phase": "failed",
                "step": normalized["summary"],
                "error_summary": error_summary,
            },
            evidence_refs=refs,
            resume_hint=resume_hint or "resume_failed_step_after_recovery",
        )

    def build_resume_payload(self, session_id: str) -> dict[str, Any] | None:
        try:
            return self.operator_runtime.recovery_resume_payload(session_id)
        except Exception:
            return None

    def replay_evidence_refs(self, session_id: str) -> list[dict[str, Any]]:
        try:
            refs = self.operator_runtime.replay_evidence_refs(session_id)
        except Exception:
            refs = []
        if not isinstance(refs, list):
            refs = []
        try:
            operator_registry = get_operator_registry_service()
            completions = operator_registry.completed_steps(session_id)
            failed_step = operator_registry.failed_step(session_id)

            def has_evidence(evidence_id: str) -> bool:
                return any(evidence_id in item.get("evidence_refs", []) for item in refs if isinstance(item, dict))

            for complete_id in completions:
                evidence_id = f"evidence:{complete_id}:completed"
                if not has_evidence(evidence_id):
                    refs.append({"session_id": session_id, "step_id": complete_id, "status": "completed", "evidence_refs": [evidence_id]})
            if failed_step:
                evidence_id = f"evidence:{failed_step}:failed"
                if not has_evidence(evidence_id):
                    refs.append({"session_id": session_id, "step_id": failed_step, "status": "failed", "evidence_refs": [evidence_id]})
        except Exception:
            pass
        return refs

    def normalize_step(self, step: Any) -> dict[str, Any]:
        step_id = self.step_id_for(step)
        step_type = _first_text(step, "step_type", "type", "action")
        name = _first_text(step, "name", "title", "label")
        action = _first_text(step, "action", "type", "step_type")
        summary = {
            "step_id": step_id,
            "step_type": step_type,
            "name": name,
            "action": action,
        }
        return {
            "step_id": step_id,
            "step_type": step_type or action or "unknown",
            "summary": summary,
        }

    def step_id_for(self, step: Any) -> str:
        explicit = _first_text(step, "step_id", "id")
        if explicit:
            return explicit
        canonical = _canonical_step_payload(step)
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"step:{digest[:16]}"

    def _evidence_refs(
        self,
        *,
        evidence_refs: list[str] | tuple[str, ...] | None,
        result: Any,
    ) -> list[str]:
        refs: list[str] = []
        for item in _list(evidence_refs):
            text = str(item or "").strip()
            if text and text not in refs:
                refs.append(text)
        if isinstance(result, dict):
            for key in ("evidence_refs", "evidence", "evidence_ids"):
                for item in _list(result.get(key)):
                    text = str(item or "").strip()
                    if text and text not in refs:
                        refs.append(text)
            nested = result.get("result")
            if isinstance(nested, dict):
                for key in ("evidence_refs", "evidence", "evidence_ids"):
                    for item in _list(nested.get(key)):
                        text = str(item or "").strip()
                        if text and text not in refs:
                            refs.append(text)
        return refs


def _first_text(value: Any, *keys: str) -> str:
    for key in keys:
        candidate: Any = None
        if isinstance(value, dict):
            candidate = value.get(key)
        else:
            candidate = getattr(value, key, None)
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _canonical_step_payload(step: Any) -> dict[str, Any]:
    if isinstance(step, dict):
        return copy.deepcopy(step)
    payload: dict[str, Any] = {}
    for key in ("step_id", "id", "step_type", "type", "name", "action"):
        candidate = getattr(step, key, None)
        if candidate is not None:
            payload[key] = candidate
    if payload:
        return payload
    return {"repr": repr(step)}


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _summary(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: copy.deepcopy(value.get(key))
            for key in ("ok", "status", "message", "final_answer", "error")
            if key in value
        }
    return str(value or "")


def _error_summary(error: Any) -> str:
    if isinstance(error, dict):
        message = error.get("message") or error.get("error") or error.get("type")
        if message:
            return str(message)
        return json.dumps(error, sort_keys=True, default=str)
    return str(error or "")


__all__ = ["OperatorIntegrationBridge"]
