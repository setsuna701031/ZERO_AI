from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PersonaState(str, Enum):
    IDLE = "IDLE"
    THINKING = "THINKING"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


@dataclass
class PersonaStateSnapshot:
    state: PersonaState
    reason: str = ""
    source: str = ""
    detail: str = ""

    def to_display_text(self) -> str:
        parts: list[str] = [f"[ASSISTANT_STATE] {self.state.value}"]
        if self.reason:
            parts.append(f"reason={self.reason}")
        if self.source:
            parts.append(f"source={self.source}")
        if self.detail:
            parts.append(f"detail={self.detail}")
        return " | ".join(parts)


class PersonaStateManager:
    def __init__(self) -> None:
        self._current = PersonaStateSnapshot(
            state=PersonaState.IDLE,
            reason="startup",
            source="persona_state_manager",
            detail="initialized",
        )

    def get_state(self) -> PersonaStateSnapshot:
        return self._current

    def set_state(
        self,
        state: PersonaState,
        *,
        reason: str = "",
        source: str = "",
        detail: str = "",
    ) -> PersonaStateSnapshot:
        self._current = PersonaStateSnapshot(
            state=state,
            reason=reason.strip(),
            source=source.strip(),
            detail=detail.strip(),
        )
        return self._current

    def set_idle(self, *, reason: str = "", source: str = "", detail: str = "") -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.IDLE,
            reason=reason,
            source=source,
            detail=detail,
        )

    def set_thinking(self, *, reason: str = "", source: str = "", detail: str = "") -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.THINKING,
            reason=reason,
            source=source,
            detail=detail,
        )

    def set_executing(self, *, reason: str = "", source: str = "", detail: str = "") -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.EXECUTING,
            reason=reason,
            source=source,
            detail=detail,
        )

    def set_success(self, *, reason: str = "", source: str = "", detail: str = "") -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.SUCCESS,
            reason=reason,
            source=source,
            detail=detail,
        )

    def set_error(self, *, reason: str = "", source: str = "", detail: str = "") -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.ERROR,
            reason=reason,
            source=source,
            detail=detail,
        )


_global_persona_state_manager: Optional[PersonaStateManager] = None


def get_persona_state_manager() -> PersonaStateManager:
    global _global_persona_state_manager
    if _global_persona_state_manager is None:
        _global_persona_state_manager = PersonaStateManager()
    return _global_persona_state_manager