"""Runtime admission trace contract.

RuntimeAdmissionTrace v0 records an admission decision only. It must not import
scheduler, enqueue work, execute steps, mutate state, recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = ["RuntimeAdmissionTrace"]


@dataclass(frozen=True)
class RuntimeAdmissionTrace:
    trace_id: str
    request_id: str
    stage: str
    decision: str
    status: str
    reason: str
    policy_rule: str
    risk_level: str
    authority_scope: str
    lease_id: str | None = None
    grant_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
