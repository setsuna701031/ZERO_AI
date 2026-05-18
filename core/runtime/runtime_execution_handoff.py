"""Runtime execution handoff record contract.

RuntimeExecutionHandoffRecord v0 records bridge and adapter admission lineage.
It must not import scheduler, enqueue work, execute steps, mutate state,
recover, or replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = ["RuntimeExecutionHandoffRecord"]


@dataclass(frozen=True)
class RuntimeExecutionHandoffRecord:
    request_id: str
    trace_id: str
    lease_id: str
    grant_id: str
    bridge_status: str
    adapter_status: str
    authority_scope: str
    risk_level: str
    queue_admission_id: str | None = None
    queue_admission_status: str | None = None
    enqueue_id: str | None = None
    enqueue_status: str | None = None
    executed: bool = False
    enqueued: bool = False
    scheduler_touched: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
