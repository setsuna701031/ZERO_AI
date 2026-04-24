from __future__ import annotations

from dataclasses import dataclass

from core.persona.loader import PersonaProfile
from core.persona.state_manager import PersonaStateSnapshot
from core.persona.visual_profile import PersonaVisualProfile


@dataclass(frozen=True)
class PersonaPanelData:
    persona_name: str
    persona_role: str
    current_state: str
    reason: str
    source: str
    detail: str
    visual_id: str
    state_image: str
    capability_routing: bool
    voice_connected: bool
    avatar_control_connected: bool
    live2d_connected: bool
    last_user_command: str
    last_capability: str
    last_result: str
    last_output_hint: str
    last_task_id: str

    def to_lines(self) -> list[str]:
        return [
            "[ZERO_PERSONA]",
            f"name={self.persona_name}",
            f"role={self.persona_role}",
            f"state={self.current_state}",
            f"reason={self.reason or '-'}",
            f"source={self.source or '-'}",
            f"detail={self.detail or '-'}",
            f"visual_id={self.visual_id}",
            f"image={self.state_image}",
            f"capability_routing={self.capability_routing}",
            f"voice={self.voice_connected}",
            f"avatar_control={self.avatar_control_connected}",
            f"live2d={self.live2d_connected}",
            "[ZERO_RUNTIME]",
            f"last_user_command={self.last_user_command or '-'}",
            f"last_capability={self.last_capability or '-'}",
            f"last_result={self.last_result or '-'}",
            f"last_output_hint={self.last_output_hint or '-'}",
            f"last_task_id={self.last_task_id or '-'}",
        ]

    def to_text(self) -> str:
        return "\n".join(self.to_lines())


def build_persona_panel_data(
    persona: PersonaProfile,
    snapshot: PersonaStateSnapshot,
    visual_profile: PersonaVisualProfile,
) -> PersonaPanelData:
    image_path = visual_profile.resolve_image_for_state(snapshot.state)
    capability_scope = persona.capability_scope

    return PersonaPanelData(
        persona_name=persona.name,
        persona_role=persona.role,
        current_state=snapshot.state.value,
        reason=snapshot.reason,
        source=snapshot.source,
        detail=snapshot.detail,
        visual_id=visual_profile.visual_id,
        state_image=str(image_path),
        capability_routing=bool(capability_scope.get("can_use_zero_capabilities")),
        voice_connected=bool(capability_scope.get("can_use_voice")),
        avatar_control_connected=bool(capability_scope.get("can_control_avatar")),
        live2d_connected=bool(capability_scope.get("can_use_live2d")),
        last_user_command=snapshot.last_user_command,
        last_capability=snapshot.last_capability,
        last_result=snapshot.last_result,
        last_output_hint=snapshot.last_output_hint,
        last_task_id=snapshot.last_task_id,
    )


def render_persona_panel(
    persona: PersonaProfile,
    snapshot: PersonaStateSnapshot,
    visual_profile: PersonaVisualProfile,
) -> str:
    panel = build_persona_panel_data(persona, snapshot, visual_profile)
    return panel.to_text()