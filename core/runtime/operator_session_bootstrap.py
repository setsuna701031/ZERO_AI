from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.operator_integration_bridge import OperatorIntegrationBridge
from core.runtime.persistent_operator import PersistentOperatorRuntime


class OperatorSessionBootstrap:
    """Orchestration-level bootstrap for persistent operator sessions.

    The bootstrap only creates or attaches an operator_session_id to existing
    task/context payloads. It does not execute steps, own scheduler state, or
    change runtime semantics when no bridge/runtime has been injected.
    """

    def __init__(
        self,
        *,
        operator_bridge: OperatorIntegrationBridge | None = None,
        operator_runtime: PersistentOperatorRuntime | None = None,
        enabled: bool = True,
    ) -> None:
        if operator_bridge is None and operator_runtime is not None:
            operator_bridge = OperatorIntegrationBridge(operator_runtime)
        self.operator_bridge = operator_bridge
        self.enabled = bool(enabled)

    def ensure_session_for_task(
        self,
        task: Any,
        context: dict[str, Any] | None = None,
        goal: str | None = None,
        pending_steps: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing_session_id = self.extract_session_id(task=task, context=context)
        if existing_session_id:
            self.attach_session_id(task=task, context=context, session_id=existing_session_id)
            return {
                "ok": True,
                "created": False,
                "operator_session_id": existing_session_id,
                "task": task,
                "context": context,
            }

        if not self.should_bootstrap(task=task, context=context):
            return {
                "ok": True,
                "created": False,
                "operator_session_id": "",
                "task": task,
                "context": context,
            }

        bridge = self.operator_bridge
        if bridge is None:
            return {
                "ok": True,
                "created": False,
                "operator_session_id": "",
                "task": task,
                "context": context,
            }

        resolved_goal = str(goal or self._goal_from_task(task) or "").strip()
        resolved_pending_steps = (
            list(pending_steps)
            if isinstance(pending_steps, (list, tuple))
            else self._pending_steps_from_task(task)
        )
        resolved_metadata = self._metadata_from_task(task)
        if isinstance(metadata, dict):
            resolved_metadata.update(copy.deepcopy(metadata))
        if isinstance(context, dict):
            resolved_metadata.setdefault("context_keys", sorted(str(key) for key in context.keys()))

        task_id = self._task_id(task)
        session = bridge.on_session_start(
            task_id=task_id,
            goal=resolved_goal,
            pending_steps=resolved_pending_steps,
            metadata=resolved_metadata,
        )
        self.attach_session_id(task=task, context=context, session_id=session.session_id)
        return {
            "ok": True,
            "created": True,
            "operator_session_id": session.session_id,
            "session": session,
            "task": task,
            "context": context,
        }

    def extract_session_id(
        self,
        task: Any = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        context_id = _mapping_session_id(context)
        if context_id:
            return context_id

        task_id = _value_session_id(task)
        if task_id:
            return task_id

        metadata = _metadata(task)
        return _mapping_session_id(metadata)

    def attach_session_id(
        self,
        task: Any = None,
        context: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        resolved = str(session_id or "").strip()
        if not resolved:
            return {"ok": False, "operator_session_id": ""}

        if isinstance(context, dict):
            context["operator_session_id"] = resolved

        if isinstance(task, dict):
            task["operator_session_id"] = resolved
            metadata = task.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["operator_session_id"] = resolved
            operator_state = task.setdefault("operator", {})
            if isinstance(operator_state, dict):
                operator_state["session_id"] = resolved
        elif task is not None:
            try:
                setattr(task, "operator_session_id", resolved)
            except Exception:
                pass
            try:
                current_metadata = getattr(task, "metadata", None)
                if not isinstance(current_metadata, dict):
                    current_metadata = {}
                    setattr(task, "metadata", current_metadata)
                current_metadata["operator_session_id"] = resolved
            except Exception:
                pass

        return {"ok": True, "operator_session_id": resolved}

    def should_bootstrap(
        self,
        task: Any = None,
        context: dict[str, Any] | None = None,
    ) -> bool:
        if not self.enabled or self.operator_bridge is None:
            return False
        if _truthy_flag(context, "disable_operator_session", "operator_session_disabled"):
            return False
        if _truthy_flag(task, "disable_operator_session", "operator_session_disabled"):
            return False
        if _truthy_flag(context, "enable_operator_session", "operator_session_enabled", "persistent_operator"):
            return True
        if _truthy_flag(task, "enable_operator_session", "operator_session_enabled", "persistent_operator"):
            return True
        return bool(self._pending_steps_from_task(task))

    def _task_id(self, task: Any) -> str:
        for key in ("task_id", "id", "task_name", "name"):
            value = _value(task, key)
            text = str(value or "").strip()
            if text:
                return text
        payload = _task_payload(task)
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"operator-task:{digest[:16]}"

    def _goal_from_task(self, task: Any) -> str:
        for key in ("goal", "description", "title", "name"):
            value = _value(task, key)
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _pending_steps_from_task(self, task: Any) -> list[Any]:
        for key in ("pending_steps", "steps"):
            value = _value(task, key)
            if isinstance(value, (list, tuple)):
                return list(value)
        return []

    def _metadata_from_task(self, task: Any) -> dict[str, Any]:
        metadata = _metadata(task)
        return copy.deepcopy(metadata if isinstance(metadata, dict) else {})


def _mapping_session_id(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("operator_session_id", "persistent_operator_session_id"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    operator_state = value.get("operator")
    if isinstance(operator_state, dict):
        text = str(operator_state.get("session_id") or "").strip()
        if text:
            return text
    return ""


def _value_session_id(value: Any) -> str:
    if isinstance(value, dict):
        return _mapping_session_id(value)
    for key in ("operator_session_id", "persistent_operator_session_id"):
        text = str(getattr(value, key, "") or "").strip()
        if text:
            return text
    return ""


def _metadata(task: Any) -> dict[str, Any]:
    if isinstance(task, dict):
        metadata = task.get("metadata")
    else:
        metadata = getattr(task, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _value(task: Any, key: str) -> Any:
    if isinstance(task, dict):
        return task.get(key)
    return getattr(task, key, None)


def _truthy_flag(source: Any, *keys: str) -> bool:
    metadata = _metadata(source)
    for key in keys:
        value = _value(source, key)
        if value is None and isinstance(metadata, dict):
            value = metadata.get(key)
        if str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}:
            return True
        if value is True:
            return True
    return False


def _task_payload(task: Any) -> dict[str, Any]:
    if isinstance(task, dict):
        return copy.deepcopy(task)
    payload: dict[str, Any] = {}
    for key in ("task_id", "id", "task_name", "name", "goal", "description", "steps", "pending_steps"):
        value = getattr(task, key, None)
        if value is not None:
            payload[key] = value
    return payload or {"repr": repr(task)}


__all__ = ["OperatorSessionBootstrap"]
