"""Runtime execution grant contract.

RuntimeExecutionGrant v0 is an execution authority object only. It must not
import scheduler, enqueue work, execute steps, mutate state, recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = ["RuntimeExecutionGrant"]


@dataclass(frozen=True)
class RuntimeExecutionGrant:
    grant_id: str
    request_id: str
    trace_id: str
    lease_id: str
    granted: bool = False
    status: str = "grant_not_issued"
    reason: str = "execution_not_granted"
    authority_scope: str = "none"
    risk_level: str = "unknown"
    granted_by: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
