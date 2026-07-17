from __future__ import annotations

"""Operator completion/failure registry service.

This module is the Phase 1 deglobalization seam for the historical ZERO
operator readback registries.  Older code used ``builtins`` directly as a
process-wide bus.  The service keeps the same backing store for compatibility,
but all runtime callers should use this module instead of touching ``builtins``
from scattered locations.

Phase 1 invariant:
- Preserve existing behavior and tests.
- Centralize all direct access to the legacy registry names here.

Later phases can replace the backing store with a session-local/runtime store
without changing scheduler, task runner, replay, recovery, or operator bridge
call sites again.
"""

import builtins
from threading import RLock
from typing import Any

OPERATOR_COMPLETION_REGISTRY_KEY = "_zero_operator_completion_registry_v13"
OPERATOR_FAILURE_REGISTRY_KEY = "_zero_operator_failure_registry_v14"


class OperatorRegistryService:
    """Compatibility facade for operator step completion/failure readback."""

    def __init__(self) -> None:
        self._lock = RLock()

    def completion_registry(self) -> dict[str, set[str]]:
        with self._lock:
            registry = getattr(builtins, OPERATOR_COMPLETION_REGISTRY_KEY, None)
            if not isinstance(registry, dict):
                registry = {}
                setattr(builtins, OPERATOR_COMPLETION_REGISTRY_KEY, registry)
            return registry

    def failure_registry(self) -> dict[str, str]:
        with self._lock:
            registry = getattr(builtins, OPERATOR_FAILURE_REGISTRY_KEY, None)
            if not isinstance(registry, dict):
                registry = {}
                setattr(builtins, OPERATOR_FAILURE_REGISTRY_KEY, registry)
            return registry

    def completed_steps(self, session_id: Any) -> set[str]:
        sid = self._sid(session_id)
        if not sid:
            return set()
        registry = self.completion_registry()
        values = registry.get(sid, set())
        if isinstance(values, set):
            return set(str(item) for item in values)
        if isinstance(values, (list, tuple)):
            return set(str(item) for item in values)
        if values:
            return {str(values)}
        return set()

    def failed_step(self, session_id: Any) -> str | None:
        sid = self._sid(session_id)
        if not sid:
            return None
        value = self.failure_registry().get(sid)
        return str(value) if value else None

    def mark_complete(self, session_id: Any, step_id: Any) -> str | None:
        sid = self._sid(session_id)
        step = self._step(step_id)
        if not sid or not step:
            return None
        with self._lock:
            self.completion_registry().setdefault(sid, set()).add(step)
            # A successful completion supersedes any stale failure readback for
            # the same operator session.  This keeps the compatibility backing
            # store from poisoning later resume/replay reads when tests or
            # runtimes reuse explicit session identifiers.
            self.failure_registry().pop(sid, None)
        return step

    def mark_failed(self, session_id: Any, step_id: Any) -> str | None:
        sid = self._sid(session_id)
        step = self._step(step_id)
        if not sid or not step:
            return None
        with self._lock:
            self.failure_registry()[sid] = step
        return step

    def has_completion(self, session_id: Any) -> bool:
        return bool(self.completed_steps(session_id))

    def clear_failure(self, session_id: Any) -> None:
        sid = self._sid(session_id)
        if not sid:
            return
        with self._lock:
            self.failure_registry().pop(sid, None)

    def clear_session(self, session_id: Any) -> None:
        sid = self._sid(session_id)
        if not sid:
            return
        with self._lock:
            self.completion_registry().pop(sid, None)
            self.failure_registry().pop(sid, None)

    def snapshot(self, session_id: Any) -> dict[str, Any]:
        sid = self._sid(session_id)
        return {
            "session_id": sid,
            "completed_steps": sorted(self.completed_steps(sid)),
            "failed_step": self.failed_step(sid),
        }

    @staticmethod
    def _sid(session_id: Any) -> str:
        return str(session_id or "").strip()

    @staticmethod
    def _step(step_id: Any) -> str:
        return str(step_id or "").strip()


_OPERATOR_REGISTRY_SERVICE = OperatorRegistryService()


def get_operator_registry_service() -> OperatorRegistryService:
    return _OPERATOR_REGISTRY_SERVICE


def get_completion_registry() -> dict[str, set[str]]:
    return get_operator_registry_service().completion_registry()


def get_failure_registry() -> dict[str, str]:
    return get_operator_registry_service().failure_registry()


def mark_operator_step_complete(session_id: Any, step_id: Any) -> str | None:
    return get_operator_registry_service().mark_complete(session_id, step_id)


def mark_operator_step_failed(session_id: Any, step_id: Any) -> str | None:
    return get_operator_registry_service().mark_failed(session_id, step_id)


def operator_completed_steps(session_id: Any) -> set[str]:
    return get_operator_registry_service().completed_steps(session_id)


def operator_failed_step(session_id: Any) -> str | None:
    return get_operator_registry_service().failed_step(session_id)
