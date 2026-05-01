from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ToolRequest:
    tool: str
    input: Dict[str, Any]
    source: str = "runtime"
    risk_level: str = "low"
    request_id: str | None = None


@dataclass
class ToolResult:
    ok: bool
    tool: str
    output: Dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    side_effect_level: str = "none"
    request_id: str | None = None
