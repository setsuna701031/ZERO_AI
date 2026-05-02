from __future__ import annotations

import copy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.persona.display_state_contract import DISPLAY_STATE_SCHEMA_VERSION, ensure_display_state_contract
from core.persona.runtime_bridge import PersonaRuntimeBridge
from core.persona.runtime_state import PersonaRuntimeState, create_persona_runtime_state


PREFIX = "[persona-runtime-state-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    state = create_persona_runtime_state()
    if not isinstance(state, PersonaRuntimeState):
        return fail(f"create_persona_runtime_state returned wrong type: {state}")
    if not state.runtime_session_id or not state.persona_id or not isinstance(state.persona_profile, dict):
        return fail(f"runtime state missing stable identity fields: {state.snapshot()}")
    pass_step("runtime_state can be created without long-term memory")

    bridge = PersonaRuntimeBridge(workspace_dir=REPO_ROOT)
    initial_session_id = bridge.runtime_state.runtime_session_id
    initial_schema_version = bridge.get_display_state().get("display_state_schema_version")
    if initial_schema_version != DISPLAY_STATE_SCHEMA_VERSION:
        return fail("display_state schema version changed unexpectedly")

    display = bridge.submit_ui_task("read workspace/shared/input.txt and write workspace/shared/summary.txt")
    try:
        ensure_display_state_contract(display)
    except Exception as exc:
        return fail(f"display_state contract failed after runtime_state update: {exc}\n{display}")

    after_submit_session_id = bridge.runtime_state.runtime_session_id
    replay_display = bridge.get_display_state()
    after_replay_session_id = bridge.runtime_state.runtime_session_id
    if initial_session_id != after_submit_session_id or after_submit_session_id != after_replay_session_id:
        return fail(
            "runtime_session_id should remain stable inside one bridge instance: "
            f"{initial_session_id}, {after_submit_session_id}, {after_replay_session_id}"
        )
    pass_step("same bridge instance preserves runtime_session_id")

    snapshot = bridge.runtime_state.snapshot()
    if snapshot.get("current_task_goal") != "read workspace/shared/input.txt and write workspace/shared/summary.txt":
        return fail(f"runtime_state did not retain current_task_goal: {snapshot}")
    policy = snapshot.get("last_policy_decision")
    if not isinstance(policy, dict) or policy.get("risk_level") != display.get("risk_level"):
        return fail(f"runtime_state last_policy_decision does not match display policy fields: {snapshot}\n{display}")
    last_display = snapshot.get("last_display_state")
    if not isinstance(last_display, dict) or last_display.get("persona_final_reply") != replay_display.get("persona_final_reply"):
        return fail(f"runtime_state last_display_state did not snapshot latest display: {snapshot}")
    pass_step("runtime_state retains task, policy, and latest display snapshots")

    forbidden_public_keys = {
        "runtime_session_id",
        "persona_state",
        "persona_profile",
        "persona_mode",
        "last_policy_decision",
        "last_display_state",
    }
    leaked = sorted(key for key in forbidden_public_keys if key in display)
    if leaked:
        return fail(f"internal runtime_state leaked into display_state: {leaked}\n{display}")
    if display.get("display_state_schema_version") != DISPLAY_STATE_SCHEMA_VERSION:
        return fail(f"display_state schema version changed: {display}")
    pass_step("runtime_state remains internal and does not change display_state schema")

    before_mutation = copy.deepcopy(bridge.runtime_state.last_display_state)
    display["persona_final_reply"] = "external mutation should not affect runtime_state"
    if bridge.runtime_state.last_display_state != before_mutation:
        return fail("runtime_state last_display_state should be a defensive copy")
    pass_step("runtime_state snapshots are defensive copies")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
