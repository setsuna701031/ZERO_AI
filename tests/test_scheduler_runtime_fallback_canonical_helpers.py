from __future__ import annotations

from core.runtime.scheduler_runtime_fallback import (
    canonical_select_step,
    canonical_soft_gate_failure,
)


def test_canonical_soft_gate_failure_matches_scheduler_fallback_signals() -> None:
    assert canonical_soft_gate_failure({"ok": False, "reason": "authority missing"})
    assert canonical_soft_gate_failure({"ok": False, "error": "capability required"})
    assert not canonical_soft_gate_failure({"ok": True, "status": "completed"})


def test_canonical_select_step_uses_current_step_index() -> None:
    task = {
        "current_step_index": 1,
        "steps": [{"type": "first"}, {"type": "second"}],
    }

    assert canonical_select_step(task) == {"type": "second"}
    assert canonical_select_step({"current_step_index": 99, "steps": task["steps"]}) == {"type": "first"}
