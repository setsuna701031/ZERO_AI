from __future__ import annotations

from pathlib import Path


def test_scheduler_sync_blocked_state_wrapper_is_terminal_persistence() -> None:
    source = Path("core/tasks/scheduler.py").read_text(encoding="utf-8")

    marker = "def _sync_blocked_state(self, task_id: str, blocked_reason: str) -> None:"
    start = source.index(marker)
    next_marker = "\n    # Repository persistence ownership boundary:"
    end = source.index(next_marker, start)
    body = source[start:end]

    assert "return sync_blocked_state(scheduler=self" not in body
    assert "Calling sync_blocked_state(...) from here re-enters the helper" in body
    assert (
        'task["status"] = STATUS_BLOCKED' in body
        or 'task["status"] = normalize_status(STATUS_BLOCKED)' in body
        or 'task["status"] = canonical_runtime_status(STATUS_BLOCKED)' in body
        or 'project_runtime_status(task, STATUS_BLOCKED' in body
    )
    assert "self._persist_task_payload(clean_task_id, task)" in body


def test_scheduler_sync_blocked_state_still_imports_helper_for_external_callers() -> None:
    source = Path("core/tasks/scheduler.py").read_text(encoding="utf-8")

    assert "from core.tasks.scheduler_core.repo_blocked_state import (" in source
    assert "sync_blocked_state," in source
