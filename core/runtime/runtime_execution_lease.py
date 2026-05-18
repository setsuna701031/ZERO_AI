"""Runtime execution lease contract.

RuntimeExecutionLease v0 only represents whether execution ownership has been
leased. It must not import scheduler, enqueue work, execute steps, mutate
state, recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = ["RuntimeExecutionLease"]


@dataclass(frozen=True)
class RuntimeExecutionLease:
    lease_id: str
    request_id: str
    granted: bool
    trace_id: str
    status: str = "lease_not_granted"
    reason: str = "execution_not_granted"
    owner: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
