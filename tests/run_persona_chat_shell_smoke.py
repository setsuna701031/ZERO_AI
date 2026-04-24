from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.persona.chat_shell import (
    build_persona_system_prompt,
    generate_rule_based_response,
)
from core.persona.loader import load_default_persona
from core.persona.state_manager import get_persona_state_manager


def require_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    persona = load_default_persona()
    manager = get_persona_state_manager()
    manager.set_idle(
        reason="smoke_reset",
        source="run_persona_chat_shell_smoke",
        detail="reset before shell smoke",
        last_result="smoke_reset",
    )

    prompt = build_persona_system_prompt(persona)
    require_true(persona.name in prompt, "persona name missing in prompt")
    require_true(persona.role in prompt, "persona role missing in prompt")

    help_result = generate_rule_based_response(persona, "help")
    require_true("run doc-demo" in help_result.response, "help text missing doc-demo command")
    require_true("panel" in help_result.response, "help text missing panel command")
    require_true(help_result.should_exit is False, "help should not exit")

    status_result = generate_rule_based_response(persona, "status")
    require_true("current_state:" in status_result.response, "status missing current_state")
    require_true("state_image:" in status_result.response, "status missing state_image")
    require_true("visual_id:" in status_result.response, "status missing visual_id")
    require_true("last_user_command:" in status_result.response, "status missing last_user_command")
    require_true("last_result:" in status_result.response, "status missing last_result")

    panel_result = generate_rule_based_response(persona, "panel")
    require_true("[ZERO_PERSONA]" in panel_result.response, "panel missing header")
    require_true("[ZERO_RUNTIME]" in panel_result.response, "panel missing runtime header")
    require_true("state=" in panel_result.response, "panel missing state")
    require_true("image=E:\\zero_ai\\assets\\persona\\zero_v1\\base.png" in panel_result.response, "panel missing image")

    who_result = generate_rule_based_response(persona, "who are you")
    require_true(persona.intro in who_result.response, "intro not returned for identity question")
    require_true(who_result.should_exit is False, "who are you should not exit")

    cap_result = generate_rule_based_response(persona, "what can you do")
    require_true("not connected yet" in cap_result.response.lower(), "capability response mismatch")

    unknown_result = generate_rule_based_response(persona, "random unsupported message")
    require_true("Use 'help' to see supported commands." in unknown_result.response, "unknown routing mismatch")

    exit_result = generate_rule_based_response(persona, "exit")
    require_true(exit_result.should_exit is True, "exit command should exit")

    print("[PASS] persona chat shell smoke")
    print(f"[persona-shell] greeting={persona.greeting}")
    print(f"[persona-shell] exit_response={exit_result.response}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())