from __future__ import annotations

from dataclasses import dataclass, replace
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
    last_user_command: str = ""
    last_capability: str = ""
    last_result: str = ""
    last_output_hint: str = ""

    def to_display_text(self) -> str:
        parts: list[str] = [f"[ASSISTANT_STATE] {self.state.value}"]
        if self.reason:
            parts.append(f"reason={self.reason}")
        if self.source:
            parts.append(f"source={self.source}")
        if self.detail:
            parts.append(f"detail={self.detail}")
        if self.last_user_command:
            parts.append(f"last_user_command={self.last_user_command}")
        if self.last_capability:
            parts.append(f"last_capability={self.last_capability}")
        if self.last_result:
            parts.append(f"last_result={self.last_result}")
        if self.last_output_hint:
            parts.append(f"last_output_hint={self.last_output_hint}")
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
        last_user_command: str | None = None,
        last_capability: str | None = None,
        last_result: str | None = None,
        last_output_hint: str | None = None,
    ) -> PersonaStateSnapshot:
        current = self._current
        self._current = PersonaStateSnapshot(
            state=state,
            reason=reason.strip(),
            source=source.strip(),
            detail=detail.strip(),
            last_user_command=current.last_user_command if last_user_command is None else last_user_command.strip(),
            last_capability=current.last_capability if last_capability is None else last_capability.strip(),
            last_result=current.last_result if last_result is None else last_result.strip(),
            last_output_hint=current.last_output_hint if last_output_hint is None else last_output_hint.strip(),
        )
        return self._current

    def set_idle(
        self,
        *,
        reason: str = "",
        source: str = "",
        detail: str = "",
        last_user_command: str | None = None,
        last_capability: str | None = None,
        last_result: str | None = None,
        last_output_hint: str | None = None,
    ) -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.IDLE,
            reason=reason,
            source=source,
            detail=detail,
            last_user_command=last_user_command,
            last_capability=last_capability,
            last_result=last_result,
            last_output_hint=last_output_hint,
        )

    def set_thinking(
        self,
        *,
        reason: str = "",
        source: str = "",
        detail: str = "",
        last_user_command: str | None = None,
        last_capability: str | None = None,
        last_result: str | None = None,
        last_output_hint: str | None = None,
    ) -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.THINKING,
            reason=reason,
            source=source,
            detail=detail,
            last_user_command=last_user_command,
            last_capability=last_capability,
            last_result=last_result,
            last_output_hint=last_output_hint,
        )

    def set_executing(
        self,
        *,
        reason: str = "",
        source: str = "",
        detail: str = "",
        last_user_command: str | None = None,
        last_capability: str | None = None,
        last_result: str | None = None,
        last_output_hint: str | None = None,
    ) -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.EXECUTING,
            reason=reason,
            source=source,
            detail=detail,
            last_user_command=last_user_command,
            last_capability=last_capability,
            last_result=last_result,
            last_output_hint=last_output_hint,
        )

    def set_success(
        self,
        *,
        reason: str = "",
        source: str = "",
        detail: str = "",
        last_user_command: str | None = None,
        last_capability: str | None = None,
        last_result: str | None = None,
        last_output_hint: str | None = None,
    ) -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.SUCCESS,
            reason=reason,
            source=source,
            detail=detail,
            last_user_command=last_user_command,
            last_capability=last_capability,
            last_result=last_result,
            last_output_hint=last_output_hint,
        )

    def set_error(
        self,
        *,
        reason: str = "",
        source: str = "",
        detail: str = "",
        last_user_command: str | None = None,
        last_capability: str | None = None,
        last_result: str | None = None,
        last_output_hint: str | None = None,
    ) -> PersonaStateSnapshot:
        return self.set_state(
            PersonaState.ERROR,
            reason=reason,
            source=source,
            detail=detail,
            last_user_command=last_user_command,
            last_capability=last_capability,
            last_result=last_result,
            last_output_hint=last_output_hint,
        )

    def update_runtime_summary(
        self,
        *,
        last_user_command: str | None = None,
        last_capability: str | None = None,
        last_result: str | None = None,
        last_output_hint: str | None = None,
    ) -> PersonaStateSnapshot:
        self._current = replace(
            self._current,
            last_user_command=self._current.last_user_command if last_user_command is None else last_user_command.strip(),
            last_capability=self._current.last_capability if last_capability is None else last_capability.strip(),
            last_result=self._current.last_result if last_result is None else last_result.strip(),
            last_output_hint=self._current.last_output_hint if last_output_hint is None else last_output_hint.strip(),
        )
        return self._current


_global_persona_state_manager: Optional[PersonaStateManager] = None


def get_persona_state_manager() -> PersonaStateManager:
    global _global_persona_state_manager
    if _global_persona_state_manager is None:
        _global_persona_state_manager = PersonaStateManager()
    return _global_persona_state_manager