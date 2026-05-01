from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class EventRecord:
    event_id: str
    event_type: str
    source: str
    path: str
    timestamp: str
    payload: Dict[str, Any] = field(default_factory=dict)
