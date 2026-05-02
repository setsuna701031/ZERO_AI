from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.persona.display_state_contract import DISPLAY_STATE_SCHEMA_VERSION, ensure_display_state_contract

APP_PATH = REPO_ROOT / "app.py"
MAIN_PATH = REPO_ROOT / "main.py"
SHARED = REPO_ROOT / "workspace" / "shared"
INPUT = SHARED / "input.txt"

PREFIX = "[l5-run-cli-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def run_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(REPO_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def require_ok(result: subprocess.CompletedProcess[str], label: str) -> bool:
    if result.returncode != 0:
        print(f"{PREFIX} {label} stdout:")
        print(result.stdout)
        print(f"{PREFIX} {label} stderr:")
        print(result.stderr)
        return False
    return True


def main() -> int:
    SHARED.mkdir(parents=True, exist_ok=True)
    INPUT.write_text("L5 run CLI smoke input.\n", encoding="utf-8")

    json_result = run_command(
        str(APP_PATH),
        "l5-run",
        "--json",
        "read workspace/shared/input.txt and write workspace/shared/summary.txt",
    )
    if not require_ok(json_result, "app l5-run --json"):
        return fail("app l5-run --json failed")

    try:
        display_state = json.loads(json_result.stdout)
    except Exception as exc:
        return fail(f"json output is not parseable: {exc}\n{json_result.stdout}")

    try:
        ensure_display_state_contract(display_state)
    except Exception as exc:
        return fail(f"json display_state violates contract: {exc}\n{display_state}")
    if display_state.get("display_state_schema_version") != DISPLAY_STATE_SCHEMA_VERSION:
        return fail(f"display_state schema version mismatch: {display_state}")
    if display_state.get("display_state_source") != "runtime_bridge":
        return fail(f"display_state source is wrong: {display_state}")
    if display_state.get("runtime_status") != "done":
        return fail(f"runtime did not finish: {display_state}")
    if display_state.get("controller_status") != "allowed":
        return fail(f"CLI must only read controller_status from display_state: {display_state}")
    if not isinstance(display_state.get("confirmation_required"), bool):
        return fail(f"confirmation flag missing: {display_state}")
    if not isinstance(display_state.get("persona_final_reply"), str) or not display_state.get("persona_final_reply").strip():
        return fail(f"persona_final_reply missing: {display_state}")
    pass_step("app l5-run --json returns display_state from runtime_bridge")

    tts_result = run_command(
        str(APP_PATH),
        "l5-run",
        "--tts",
        "read workspace/shared/input.txt and write workspace/shared/summary.txt",
    )
    if not require_ok(tts_result, "app l5-run --tts"):
        return fail("app l5-run --tts failed")

    stdout = tts_result.stdout or ""
    for needle in (
        "[L5]",
        "controller_status: allowed",
        "[PERSONA]",
        "[TTS]",
        "input_source: persona_final_reply",
        "runtime_safe: True",
    ):
        if needle not in stdout:
            return fail(f"tts formatted output missing {needle}: {stdout}")
    pass_step("app l5-run --tts exposes passive TTS hook only")

    main_result = run_command(
        str(MAIN_PATH),
        "l5-run",
        "--json",
        "read workspace/shared/input.txt and write workspace/shared/summary.txt",
    )
    if not require_ok(main_result, "main l5-run --json"):
        return fail("main l5-run --json failed")
    try:
        main_display = json.loads(main_result.stdout)
    except Exception as exc:
        return fail(f"main l5-run did not forward JSON display_state: {exc}\n{main_result.stdout}")
    try:
        ensure_display_state_contract(main_display)
    except Exception as exc:
        return fail(f"main l5-run forwarded invalid display_state: {exc}\n{main_display}")
    if main_display.get("display_state_source") != "runtime_bridge":
        return fail(f"main l5-run did not forward runtime_bridge display_state: {main_display}")
    pass_step("main l5-run forwards to app transport")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
