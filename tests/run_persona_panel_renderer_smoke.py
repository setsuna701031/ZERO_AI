from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.persona.loader import load_default_persona
from core.persona.panel_renderer import render_persona_panel
from core.persona.state_manager import get_persona_state_manager
from core.persona.visual_profile import load_default_visual_profile


def require_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    persona = load_default_persona()
    visual_profile = load_default_visual_profile()
    manager = get_persona_state_manager()

    snapshot = manager.set_thinking(
        reason="panel_smoke",
        source="run_persona_panel_renderer_smoke",
        detail="render panel test",
    )

    text = render_persona_panel(persona, snapshot, visual_profile)

    require_true("[ZERO_PERSONA]" in text, "missing panel header")
    require_true("name=ZERO" in text, "missing persona name")
    require_true("state=THINKING" in text, "missing thinking state")
    require_true("visual_id=zero_v1" in text, "missing visual_id")
    require_true("image=E:\\zero_ai\\assets\\persona\\zero_v1\\base.png" in text, "missing image path")
    require_true("capability_routing=True" in text, "missing capability_routing flag")
    require_true("live2d=False" in text, "missing live2d flag")

    print("[PASS] persona panel renderer smoke")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())