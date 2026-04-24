from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.persona.state_manager import PersonaState


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VISUAL_PROFILE_PATH = REPO_ROOT / "assets" / "persona" / "zero_v1" / "profile.json"


@dataclass(frozen=True)
class PersonaVisualProfile:
    persona_id: str
    display_name: str
    visual_id: str
    base_image: str
    visual_style: str
    render_mode: str
    state_expression_map: dict[str, str]
    notes: list[str]
    source_path: Path

    def resolve_image_for_state(self, state: PersonaState) -> Path:
        relative_name = self.state_expression_map.get(state.value) or self.base_image
        if "/" in relative_name or "\\" in relative_name:
            return REPO_ROOT / relative_name
        return self.source_path.parent / relative_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "display_name": self.display_name,
            "visual_id": self.visual_id,
            "base_image": self.base_image,
            "visual_style": self.visual_style,
            "render_mode": self.render_mode,
            "state_expression_map": self.state_expression_map,
            "notes": self.notes,
            "source_path": str(self.source_path),
        }


def _require_non_empty_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"visual profile field '{key}' must be a non-empty string")
    return value.strip()


def _require_dict(payload: dict[str, Any], key: str) -> dict[str, str]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"visual profile field '{key}' must be an object")
    cleaned: dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip():
            raise ValueError(f"visual profile field '{key}' must contain non-empty string pairs")
        cleaned[k.strip()] = v.strip()
    return cleaned


def _require_string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"visual profile field '{key}' must be a list of non-empty strings")
    return [item.strip() for item in value]


def load_visual_profile(profile_path: str | Path | None = None) -> PersonaVisualProfile:
    path = Path(profile_path) if profile_path else DEFAULT_VISUAL_PROFILE_PATH
    if not path.exists():
        raise FileNotFoundError(f"visual profile not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))

    profile = PersonaVisualProfile(
        persona_id=_require_non_empty_string(payload, "persona_id"),
        display_name=_require_non_empty_string(payload, "display_name"),
        visual_id=_require_non_empty_string(payload, "visual_id"),
        base_image=_require_non_empty_string(payload, "base_image"),
        visual_style=_require_non_empty_string(payload, "visual_style"),
        render_mode=_require_non_empty_string(payload, "render_mode"),
        state_expression_map=_require_dict(payload, "state_expression_map"),
        notes=_require_string_list(payload, "notes"),
        source_path=path.resolve(),
    )

    for state in PersonaState:
        resolved = profile.resolve_image_for_state(state)
        if not resolved.exists():
            raise FileNotFoundError(
                f"missing image for state '{state.value}': {resolved}"
            )

    return profile


def load_default_visual_profile() -> PersonaVisualProfile:
    return load_visual_profile(DEFAULT_VISUAL_PROFILE_PATH)