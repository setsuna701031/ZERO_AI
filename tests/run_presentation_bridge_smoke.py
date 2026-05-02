from __future__ import annotations

import copy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.persona.presentation_bridge import extract_tts_input, render_cli_view, render_json_view
from core.persona.runtime_bridge import PersonaRuntimeBridge


PREFIX = "[presentation-bridge-smoke]"
PRESENTATION_BRIDGE_PATH = REPO_ROOT / "core" / "persona" / "presentation_bridge.py"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    bridge = PersonaRuntimeBridge(workspace_dir=REPO_ROOT)
    display_state = bridge.submit_ui_task("read workspace/shared/input.txt and write workspace/shared/summary.txt")
    original = copy.deepcopy(display_state)

    json_view = render_json_view(display_state)
    if json_view != display_state:
        return fail("JSON view must be an exact display_state copy")
    if json_view is display_state:
        return fail("JSON view must not return the original mutable object")
    if display_state != original:
        return fail("render_json_view mutated display_state")
    pass_step("JSON view validates and returns a defensive display_state copy")

    cli_view = render_cli_view(display_state, include_tts=True)
    for needle in ("[L5]", "runtime_status:", "controller_status:", "[PERSONA]", "[TTS]", "input_source: persona_final_reply"):
        if needle not in cli_view:
            return fail(f"CLI view missing {needle}: {cli_view}")
    if display_state != original:
        return fail("render_cli_view mutated display_state")
    pass_step("CLI view renders from display_state without mutation")

    tts_input = extract_tts_input(display_state)
    if tts_input.get("text") != display_state.get("persona_final_reply"):
        return fail(f"TTS input must use persona_final_reply text: {tts_input}")
    if tts_input.get("input_source") != "persona_final_reply":
        return fail(f"TTS input source is wrong: {tts_input}")
    if tts_input.get("controller_writeback") is not False or tts_input.get("audit_writeback") is not False:
        return fail(f"TTS input must remain passive: {tts_input}")
    if display_state != original:
        return fail("extract_tts_input mutated display_state")
    pass_step("TTS input is passive and sourced only from persona_final_reply")

    source = PRESENTATION_BRIDGE_PATH.read_text(encoding="utf-8", errors="replace")
    forbidden_imports = (
        "runtime_state",
        "policy_layer",
        "scheduler",
        "tool_call",
        "tool_registry",
        "tool_executor",
    )
    for token in forbidden_imports:
        if token in source:
            return fail(f"presentation_bridge must not depend on {token}")
    pass_step("presentation_bridge avoids runtime_state, policy, scheduler, and tool dependencies")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
