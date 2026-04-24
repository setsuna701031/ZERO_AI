from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.persona.state_manager import PersonaState
from core.persona.visual_profile import load_default_visual_profile


def require_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    profile = load_default_visual_profile()

    require_true(profile.persona_id == "zero_virtual_persona_v1", "persona_id mismatch")
    require_true(profile.display_name == "ZERO", "display_name mismatch")
    require_true(profile.render_mode == "static_base", "render_mode mismatch")

    idle_image = profile.resolve_image_for_state(PersonaState.IDLE)
    exec_image = profile.resolve_image_for_state(PersonaState.EXECUTING)
    error_image = profile.resolve_image_for_state(PersonaState.ERROR)

    require_true(idle_image.exists(), "idle image missing")
    require_true(exec_image.exists(), "executing image missing")
    require_true(error_image.exists(), "error image missing")

    print("[PASS] persona visual profile smoke")
    print(f"[visual] persona_id={profile.persona_id}")
    print(f"[visual] visual_id={profile.visual_id}")
    print(f"[visual] idle_image={idle_image}")
    print(f"[visual] executing_image={exec_image}")
    print(f"[visual] error_image={error_image}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())