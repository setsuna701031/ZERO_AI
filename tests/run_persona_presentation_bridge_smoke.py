from __future__ import annotations

import copy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.persona.runtime_bridge import PersonaRuntimeBridge


PREFIX = "[persona-presentation-bridge-smoke]"
SHARED = REPO_ROOT / "workspace" / "shared"
INPUT = SHARED / "input.txt"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    SHARED.mkdir(parents=True, exist_ok=True)
    INPUT.write_text("Persona presentation bridge input.\n", encoding="utf-8")

    bridge = PersonaRuntimeBridge(workspace_dir=REPO_ROOT)
    display = bridge.submit_ui_task("persona presentation bridge smoke")
    execution_before = copy.deepcopy(bridge._last_record.execution)

    contract = display.get("persona_runtime_contract")
    if not isinstance(contract, dict) or contract.get("role") != "human_presentation_layer":
        return fail(f"persona contract missing or wrong: {contract}")
    if contract.get("no_reverse_path") is not True:
        return fail(f"persona contract allows a reverse path: {contract}")
    forbidden = {"call_tool", "choose_tool_policy", "execute", "change_controller_decision", "invent_missing_runtime_state"}
    if not forbidden.issubset(set(contract.get("cannot") or [])):
        return fail(f"persona contract does not forbid unsafe actions: {contract}")
    pass_step("persona is declared as a one-way presentation layer")

    audit_records = display.get("audit_records")
    if not isinstance(audit_records, list) or not audit_records:
        return fail(f"audit records missing from persona display: {display}")
    if display.get("audit_record") != audit_records:
        return fail("audit_record alias should match audit_records")
    pass_step("persona receives real audit records")

    for key in (
        "persona_status_update",
        "persona_intent_explanation",
        "persona_reasoning_summary",
        "persona_final_reply",
    ):
        if not isinstance(display.get(key), str) or not display.get(key).strip():
            return fail(f"{key} missing from display: {display}")
    pass_step("persona renders status, intent, audit summary, and final reply")

    final_reply = display.get("persona_final_reply")
    result_summary = display.get("result_summary")
    if final_reply != result_summary:
        return fail(f"persona final reply should render controller/runtime result only: {display}")
    pass_step("persona final reply does not invent missing runtime information")

    tts_pipeline = display.get("tts_pipeline")
    if not isinstance(tts_pipeline, dict):
        return fail(f"tts pipeline missing: {display}")
    if tts_pipeline.get("input_source") != "persona_final_reply":
        return fail(f"tts input source is wrong: {tts_pipeline}")
    if tts_pipeline.get("controller_writeback") is not False or tts_pipeline.get("audit_writeback") is not False:
        return fail(f"tts must not write back to controller or audit: {tts_pipeline}")
    if "MOSS-TTS-Nano" not in str(tts_pipeline.get("tts_model_path") or ""):
        return fail(f"MOSS TTS path missing: {tts_pipeline}")
    pass_step("TTS is attached after persona_final_reply only")

    if bridge._last_record.execution != execution_before:
        return fail("persona presentation mutated runtime execution")
    pass_step("persona presentation does not mutate runtime execution")

    formatted = bridge.format_display_text()
    for needle in ("[PERSONA REPLY]", "[TTS PIPELINE]", "Input Source : persona_final_reply"):
        if needle not in formatted:
            return fail(f"formatted display missing {needle}: {formatted}")
    pass_step("formatted display exposes persona reply and TTS pipeline")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
