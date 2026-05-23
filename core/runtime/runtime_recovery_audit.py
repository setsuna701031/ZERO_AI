from dataclasses import dataclass, field
from typing import Any

@dataclass
class RuntimeRecoveryAuditRecord:
    recovery_id: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))
