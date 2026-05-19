"""Canonical runtime execution request contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = ["RuntimeExecutionRequest"]


@dataclass(frozen=True)
class RuntimeExecutionRequest:
    execution_type: str
    command: str | tuple[str, ...]
    working_directory: str | None = None
    environment: dict[str, str] | None = None
    timeout: float | None = 60.0
    metadata: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    replay_id: str | None = None
    repair_session_id: str | None = None
    dry_run: bool = False
