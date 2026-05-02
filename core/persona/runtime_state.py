from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict

from core.persona.loader import PersonaProfile, load_default_persona


def new_runtime_session_id() -> str:
    return f"persona_runtime_{uuid.uuid4().hex[:16]}"


@dataclass
class PersonaRuntimeState:
    """
    Internal per-bridge persona runtime state.

    This is not display_state and must not become part of the public
    display_state schema. It is an internal snapshot for bridge/policy/display
    continuity within a runtime session.
    """

    persona_id: str
    persona_profile: Dict[str, Any]
    persona_mode: str = "runtime_bridge"
    current_task_goal: str = ""
    runtime_session_id: str = field(default_factory=new_runtime_session_id)
    last_policy_decision: Dict[str, Any] = field(default_factory=dict)
    last_display_state: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def set_task_goal(self, goal: str) -> None:
        self.current_task_goal = str(goal or "").strip()
        self._touch()

    def update_policy_decision(self, policy_decision: Dict[str, Any]) -> None:
        self.last_policy_decision = copy.deepcopy(policy_decision) if isinstance(policy_decision, dict) else {}
        self._touch()

    def update_display_state(self, display_state: Dict[str, Any]) -> None:
        self.last_display_state = copy.deepcopy(display_state) if isinstance(display_state, dict) else {}
        self._touch()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "persona_profile": copy.deepcopy(self.persona_profile),
            "persona_mode": self.persona_mode,
            "current_task_goal": self.current_task_goal,
            "runtime_session_id": self.runtime_session_id,
            "last_policy_decision": copy.deepcopy(self.last_policy_decision),
            "last_display_state": copy.deepcopy(self.last_display_state),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()


def create_persona_runtime_state(persona: PersonaProfile | None = None) -> PersonaRuntimeState:
    profile = persona or load_default_persona()
    return PersonaRuntimeState(
        persona_id=profile.persona_id,
        persona_profile=_compact_persona_profile(profile),
    )


def _compact_persona_profile(profile: PersonaProfile) -> Dict[str, Any]:
    return {
        "persona_id": profile.persona_id,
        "name": profile.name,
        "role": profile.role,
        "style": copy.deepcopy(profile.style),
        "capability_scope": copy.deepcopy(profile.capability_scope),
    }
