from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.persona.loader import load_default_persona


def require_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    persona = load_default_persona()

    require_true(persona.persona_id == "zero_virtual_persona_v1", "unexpected persona_id")
    require_true(persona.name == "ZERO", "unexpected persona name")
    require_true(persona.capability_scope.get("can_chat") is True, "can_chat should be true")
    require_true(persona.capability_scope.get("can_use_live2d") is False, "can_use_live2d should be false")
    require_true("role drift" in persona.style.get("avoid", []), "missing style avoidance rule")
    require_true(persona.greeting.strip() != "", "greeting should not be empty")

    print("[PASS] persona loader smoke")
    print(f"[persona] id={persona.persona_id}")
    print(f"[persona] name={persona.name}")
    print(f"[persona] source={persona.source_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())