from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PERSONA_DIR = Path(__file__).resolve().parent
DEFAULT_PERSONA_PATH = PERSONA_DIR / "default_persona.json"


@dataclass(frozen=True)
class PersonaProfile:
    persona_id: str
    name: str
    role: str
    identity: str
    style: dict[str, Any]
    behavior_rules: list[str]
    capability_scope: dict[str, Any]
    memory_policy: dict[str, Any]
    intro: str
    greeting: str
    source_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "role": self.role,
            "identity": self.identity,
            "style": self.style,
            "behavior_rules": self.behavior_rules,
            "capability_scope": self.capability_scope,
            "memory_policy": self.memory_policy,
            "intro": self.intro,
            "greeting": self.greeting,
            "source_path": str(self.source_path),
        }


def _require_non_empty_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"persona field '{key}' must be a non-empty string")
    return value.strip()


def _require_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"persona field '{key}' must be an object")
    return value


def _require_string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"persona field '{key}' must be a list of non-empty strings")
    return [item.strip() for item in value]


def load_persona(persona_path: str | Path | None = None) -> PersonaProfile:
    path = Path(persona_path) if persona_path else DEFAULT_PERSONA_PATH
    if not path.exists():
        raise FileNotFoundError(f"persona file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))

    return PersonaProfile(
        persona_id=_require_non_empty_string(payload, "persona_id"),
        name=_require_non_empty_string(payload, "name"),
        role=_require_non_empty_string(payload, "role"),
        identity=_require_non_empty_string(payload, "identity"),
        style=_require_dict(payload, "style"),
        behavior_rules=_require_string_list(payload, "behavior_rules"),
        capability_scope=_require_dict(payload, "capability_scope"),
        memory_policy=_require_dict(payload, "memory_policy"),
        intro=_require_non_empty_string(payload, "intro"),
        greeting=_require_non_empty_string(payload, "greeting"),
        source_path=path.resolve(),
    )


def load_default_persona() -> PersonaProfile:
    return load_persona(DEFAULT_PERSONA_PATH)