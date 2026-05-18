"""Runtime execution token contract.

RuntimeExecutionToken v0 records pending execution authority only. It has no
executor import, scheduler import, execution, mutation, recovery, or replay
behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = ["RuntimeExecutionToken"]


@dataclass(frozen=True)
class RuntimeExecutionToken:
    execution_token_id: str
    request_id: str
    trace_id: str
    lease_id: str
    grant_id: str
    queue_admission_id: str
    enqueue_id: str
    authority_scope: str
    risk_level: str
    execution_pending: bool
    executed: bool
    revoked: bool
    metadata: dict[str, Any] = field(default_factory=dict)
