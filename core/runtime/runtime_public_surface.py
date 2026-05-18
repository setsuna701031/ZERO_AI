"""Stable public runtime surface for future governed runtime access.

This module is the intended public entry point for plugins, capability packs,
UI, remote orchestration, and future agents. It is currently contract-only:
functions define future access points and intentionally raise
NotImplementedError until governed runtime wrappers are implemented.

Implementations must route through governed authority paths. They must not call
scheduler internals, scheduler_core helpers, direct mutation pipeline internals,
repair transaction internals, recovery execution internals, or evidence emitters
directly.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_connector import RuntimeConnector


__all__ = [
    "submit_runtime_task",
    "request_runtime_repair",
    "request_runtime_mutation",
    "query_runtime_status",
    "request_runtime_replay",
    "request_runtime_recovery",
]


def submit_runtime_task(task: Any, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Accept a task request envelope without enqueueing or executing it.

    This request-only hook is intentionally not connected to scheduler yet.
    Future connected implementations must route task submission through the
    governed scheduler facade, never scheduler internals.
    """
    connector = RuntimeConnector()
    return connector.submit_request(
        surface="runtime_public_surface",
        operation="submit_runtime_task",
        request={
            "task": task,
            "metadata": dict(metadata or {}),
        },
        details={
            "message": (
                "Runtime public surface accepted the request envelope but is not "
                "connected to execution runtime."
            ),
        },
    )


def request_runtime_repair(*args: Any, **kwargs: Any) -> Any:
    """Future governed repair request entry point."""
    raise NotImplementedError("request_runtime_repair is a future public runtime API")


def request_runtime_mutation(*args: Any, **kwargs: Any) -> Any:
    """Future governed mutation request entry point."""
    raise NotImplementedError("request_runtime_mutation is a future public runtime API")


def query_runtime_status(*args: Any, **kwargs: Any) -> Any:
    """Return the current read-only public surface status.

    This hook is intentionally not wired to scheduler or runtime internals yet.
    Future connected implementations must remain read-only for status queries.
    """
    return {
        "status": "not_connected",
        "surface": "runtime_public_surface",
        "operation": "query_runtime_status",
        "runtime_connected": False,
        "details": {},
    }


def request_runtime_replay(*args: Any, **kwargs: Any) -> Any:
    """Future read-only replay request entry point."""
    raise NotImplementedError("request_runtime_replay is a future public runtime API")


def request_runtime_recovery(*args: Any, **kwargs: Any) -> Any:
    """Future governed recovery request entry point."""
    raise NotImplementedError("request_runtime_recovery is a future public runtime API")
