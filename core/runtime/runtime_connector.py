"""Runtime connector contract for public-surface handoff envelopes.

RuntimeConnector v0 is intentionally not connected to scheduler or execution
runtime. It only builds stable request envelopes for future governed handoff.
It must not enqueue, execute, mutate, recover, or replay runtime work.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_ownership_gate import RuntimeOwnershipGate


__all__ = ["RuntimeConnector"]


class RuntimeConnector:
    """Contract-only connector for future runtime handoff."""

    runtime_connected = False

    def __init__(self, ownership_gate: RuntimeOwnershipGate | None = None) -> None:
        self.ownership_gate = ownership_gate or RuntimeOwnershipGate()

    def submit_request(
        self,
        *,
        surface: str,
        operation: str,
        request: Mapping[str, Any],
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a stable not-connected handoff envelope."""
        envelope = {
            "status": "accepted_not_connected",
            "surface": surface,
            "operation": operation,
            "runtime_connected": self.runtime_connected,
            "request": dict(request),
            "details": dict(details or {}),
        }
        self.ownership_gate.evaluate_request(envelope)
        return envelope
