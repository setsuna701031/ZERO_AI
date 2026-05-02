from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


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


@dataclass(frozen=True)
class ToolParameter:
    name: str
    type: str = "string"
    required: bool = False
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
        }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)
    tool_class: str = "read_only"
    side_effect_level: str = "read_only"
    risk_level: str = "low"
    scope: str = "workspace"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [item.to_dict() for item in self.parameters],
            "tool_class": self.tool_class,
            "side_effect_level": self.side_effect_level,
            "risk_level": self.risk_level,
            "scope": self.scope,
        }

    @property
    def required_parameters(self) -> List[str]:
        return [item.name for item in self.parameters if item.required]


@dataclass(frozen=True)
class ToolObservation:
    type: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "summary": self.summary,
            "data": dict(self.data),
        }
