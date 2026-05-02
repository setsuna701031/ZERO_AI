from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.persona.display_state_contract import ensure_display_state_contract
from core.persona.runtime_bridge import get_persona_runtime_bridge
from ui.digital_human_shell import get_digital_human_shell_state, run_digital_human_shell_command


PREFIX = "[digital-human-ui-shell-smoke]"
HTML_PATH = REPO_ROOT / "ui" / "digital_human.html"
SERVER_PATH = REPO_ROOT / "ui" / "server.py"
STANDALONE_SERVER_PATH = REPO_ROOT / "ui" / "digital_human_server.py"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    bridge = get_persona_runtime_bridge()
    display_state = bridge.get_display_state()
    try:
        ensure_display_state_contract(display_state)
    except Exception as exc:
        return fail(f"source display_state contract failed: {exc}\n{display_state}")

    shell = get_digital_human_shell_state(display_state)
    if shell.get("shell") != "digital_human_ui_shell":
        return fail(f"shell marker missing: {shell}")
    if shell.get("read_only") is not True:
        return fail(f"shell must be read-only: {shell}")
    if shell.get("display_state") is display_state:
        return fail("shell should defensively copy display_state")
    try:
        ensure_display_state_contract(shell.get("display_state"))
    except Exception as exc:
        return fail(f"projected display_state contract changed: {exc}\n{shell}")
    pass_step("shell projects display_state without changing schema")

    command_shell = run_digital_human_shell_command("status")
    if command_shell.get("shell") != "digital_human_ui_shell":
        return fail(f"status command did not return shell state: {command_shell}")
    if "persona_final_reply" not in command_shell.get("result", {}):
        return fail(f"shell result missing persona_final_reply: {command_shell}")
    avatar = command_shell.get("avatar")
    if not isinstance(avatar, dict) or avatar.get("persona_locked") is not True:
        return fail(f"shell must keep persona fixed: {command_shell}")
    tts = command_shell.get("tts")
    if not isinstance(tts, dict) or tts.get("placeholder") is not True or tts.get("voice_enabled") is not False:
        return fail(f"shell must expose placeholder-only TTS state: {command_shell}")
    pass_step("shell command returns persona reply and status surface")

    if not HTML_PATH.exists():
        return fail(f"digital human html missing: {HTML_PATH}")
    html = HTML_PATH.read_text(encoding="utf-8")
    required_html = [
        "Digital Human UI Shell",
        "avatarState",
        "taskInput",
        "replyBox",
        "statusBox",
        "traceBox",
        "rawBox",
        "streamBox",
        "RUN_BLOCK_SIZE = 15",
        "speaking...",
        "state-thinking",
        "state-running",
        "state-blocked",
        "/api/digital-human/status",
        "/api/digital-human/command",
    ]
    missing = [needle for needle in required_html if needle not in html]
    if missing:
        return fail(f"digital human html missing markers: {missing}")
    pass_step("html exposes avatar, task input, result, status, and trace summary")

    server_text = SERVER_PATH.read_text(encoding="utf-8")
    required_server = [
        '"/digital-human"',
        '"/api/digital-human/status"',
        '"/api/digital-human/command"',
        "get_digital_human_shell_state",
        "run_digital_human_shell_command",
    ]
    missing_server = [needle for needle in required_server if needle not in server_text]
    if missing_server:
        return fail(f"server missing digital human routes: {missing_server}")
    pass_step("server exposes digital human shell routes")

    standalone_text = STANDALONE_SERVER_PATH.read_text(encoding="utf-8")
    required_standalone = [
        "ThreadingHTTPServer",
        "/digital-human",
        "/api/digital-human/status",
        "/api/digital-human/command",
        "run_digital_human_shell_command",
    ]
    missing_standalone = [needle for needle in required_standalone if needle not in standalone_text]
    if missing_standalone:
        return fail(f"standalone server missing markers: {missing_standalone}")
    pass_step("standalone server can serve shell without Flask")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
