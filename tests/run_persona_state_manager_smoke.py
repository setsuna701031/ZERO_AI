from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.persona.state_manager import (
    PersonaState,
    get_persona_state_manager,
)


def require_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    manager = get_persona_state_manager()

    snapshot = manager.set_idle(
        reason="smoke_start",
        source="run_persona_state_manager_smoke",
        detail="reset to idle",
    )
    require_true(snapshot.state == PersonaState.IDLE, "idle state mismatch")

    snapshot = manager.set_thinking(
        reason="planning",
        source="run_persona_state_manager_smoke",
        detail="planner entered",
    )
    require_true(snapshot.state == PersonaState.THINKING, "thinking state mismatch")

    snapshot = manager.set_executing(
        reason="tool_task",
        source="run_persona_state_manager_smoke",
        detail="execution started",
    )
    require_true(snapshot.state == PersonaState.EXECUTING, "executing state mismatch")

    snapshot = manager.set_success(
        reason="done",
        source="run_persona_state_manager_smoke",
        detail="execution finished",
    )
    require_true(snapshot.state == PersonaState.SUCCESS, "success state mismatch")

    text = snapshot.to_display_text()
    require_true("[ASSISTANT_STATE] SUCCESS" in text, "display text missing success")
    require_true("reason=done" in text, "display text missing reason")

    snapshot = manager.set_error(
        reason="demo_error",
        source="run_persona_state_manager_smoke",
        detail="simulated failure",
    )
    require_true(snapshot.state == PersonaState.ERROR, "error state mismatch")

    print("[PASS] persona state manager smoke")
    print(manager.get_state().to_display_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())