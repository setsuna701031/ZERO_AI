from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.persona.display_state_contract import ensure_display_state_contract
from core.persona.policy_layer import evaluate_persona_runtime_policy
from core.persona.runtime_bridge import PersonaRuntimeBridge


PREFIX = "[persona-policy-layer-smoke]"
APP_PATH = REPO_ROOT / "app.py"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def run_app(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(APP_PATH), *args],
        cwd=str(REPO_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def main() -> int:
    low = evaluate_persona_runtime_policy("read workspace/shared/input.txt and write summary")
    if low.get("risk_level") != "low" or low.get("allowed") is not True or low.get("confirmation_required") is not False:
        return fail(f"low-risk policy classification is wrong: {low}")

    high = evaluate_persona_runtime_policy("delete workspace/shared/input.txt")
    if high.get("risk_level") != "high" or high.get("allowed") is not False or high.get("confirmation_required") is not True:
        return fail(f"high-risk policy classification is wrong: {high}")
    pass_step("policy layer classifies low and high risk without executing tools")

    bridge = PersonaRuntimeBridge(workspace_dir=REPO_ROOT)
    display = bridge.submit_ui_task("delete workspace/shared/input.txt")
    try:
        ensure_display_state_contract(display)
    except Exception as exc:
        return fail(f"blocked display_state violates contract: {exc}\n{display}")

    if display.get("runtime_status") != "blocked":
        return fail(f"high-risk task should be blocked before runtime execution: {display}")
    if display.get("controller_status") != "blocked":
        return fail(f"controller status should reflect policy block: {display}")
    if display.get("risk_level") != "high":
        return fail(f"risk_level should be filled by policy: {display}")
    if display.get("confirmation_required") is not True:
        return fail(f"confirmation_required should be true for high risk: {display}")
    if not str(display.get("blocked_reason") or "").strip():
        return fail(f"blocked_reason missing: {display}")
    trace = display.get("persona_decision_trace")
    if not isinstance(trace, list) or not trace:
        return fail(f"persona_decision_trace missing: {display}")
    first = trace[0]
    if first.get("event_type") != "policy_decision" or first.get("affects_tool_execution") is not False:
        return fail(f"persona_decision_trace must be log-only: {trace}")
    if display.get("tool_calls"):
        return fail(f"blocked high-risk task must not create tool calls: {display.get('tool_calls')}")
    pass_step("bridge blocks high-risk task and writes log-only persona_decision_trace")

    json_result = run_app("l5-run", "--json", "delete workspace/shared/input.txt")
    if json_result.returncode == 0:
        return fail(f"blocked l5-run should return non-zero while preserving JSON output: {json_result.stdout}")
    try:
        cli_display = json.loads(json_result.stdout)
    except Exception as exc:
        return fail(f"blocked --json output should remain parseable display_state: {exc}\n{json_result.stdout}")
    if cli_display.get("runtime_status") != "blocked" or cli_display.get("risk_level") != "high":
        return fail(f"CLI JSON did not expose policy fields: {cli_display}")
    pass_step("CLI --json behavior remains display_state output for blocked policy")

    tts_result = run_app("l5-run", "--tts", "read workspace/shared/input.txt and write workspace/shared/summary.txt")
    if tts_result.returncode != 0:
        return fail(f"low-risk --tts should still succeed:\n{tts_result.stdout}\n{tts_result.stderr}")
    stdout = tts_result.stdout or ""
    if "[TTS]" not in stdout or "input_source: persona_final_reply" not in stdout:
        return fail(f"TTS output changed unexpectedly: {stdout}")
    pass_step("CLI / TTS behavior remains unchanged for allowed task")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
