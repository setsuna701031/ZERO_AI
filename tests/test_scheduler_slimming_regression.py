from __future__ import annotations

import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = REPO_ROOT / "core" / "tasks" / "scheduler.py"


def test_scheduler_py_line_count_was_slimmed() -> None:
    line_count = len(SCHEDULER_PATH.read_text(encoding="utf-8").splitlines())

    assert line_count < 11500


def test_scheduler_facade_keeps_public_entrypoints_importable(tmp_path: Path) -> None:
    from core.tasks.scheduler import Scheduler

    scheduler = Scheduler(workspace_dir=str(tmp_path), debug=False)

    for name in (
        "run_next",
        "enqueue",
        "enqueue_task",
        "dequeue",
        "run_one",
        "run_once",
        "tick",
        "run_one_step",
        "create_task",
    ):
        assert callable(getattr(scheduler, name, None))


def test_slimmed_helpers_live_in_scheduler_core_not_facade() -> None:
    import core.tasks.scheduler as scheduler_module
    import core.tasks.scheduler_core.public_snapshot_helpers as public_snapshot_helpers
    import core.tasks.scheduler_core.runtime_overlay_helpers as runtime_overlay_helpers

    scheduler_source = inspect.getsource(scheduler_module)

    assert "def _zero_v7338_is_autonomous_repair_chain_payload" not in scheduler_source
    assert "def _zero_boundary_scheduler_direct_step" not in scheduler_source
    assert "def _zero_safe_public_results_summary" not in scheduler_source
    assert "def _zero_safe_task_for_snapshot" not in scheduler_source
    assert "apply_autonomous_repair_chain_overlay(Scheduler)" in scheduler_source
    assert "apply_boundary_authority_overlay(Scheduler)" in scheduler_source
    assert callable(runtime_overlay_helpers.scheduler_direct_step)
    assert callable(runtime_overlay_helpers.attach_autonomous_repair_chain_summary)
    assert callable(public_snapshot_helpers.safe_task_for_snapshot)
    assert callable(public_snapshot_helpers.safe_public_results_summary)


def test_scheduler_snapshot_facade_alias_preserves_behavior() -> None:
    import core.tasks.scheduler as scheduler_module
    from core.tasks.scheduler_core.public_snapshot_helpers import safe_task_for_snapshot

    task = {
        "task_id": "task-slim",
        "status": "queued",
        "steps": [{"type": "write_file", "path": "shared/out.txt", "content": "kept"}],
        "results": [{"result": {"ok": False, "error_type": "blocked", "message": "blocked"}}],
    }

    assert scheduler_module._zero_safe_task_for_snapshot(task) == safe_task_for_snapshot(task)
    assert scheduler_module._zero_safe_task_for_snapshot(task)["steps"][0]["content"] == "kept"


def test_scheduler_responsibility_terms_are_classified() -> None:
    from core.tasks.scheduler_core.slimming_audit import classify_scheduler_responsibility_terms

    report = classify_scheduler_responsibility_terms(SCHEDULER_PATH)
    classifications = {
        item["classification"]
        for item in report["items"]
    }

    assert report["schema"] == "scheduler_responsibility_slimming_audit.v1"
    assert report["count"] > 0
    assert classifications <= {
        "facade_compatibility",
        "migrated_helper_reference",
        "helper_logic_to_move",
    }
    assert report["classification_counts"].get("migrated_helper_reference", 0) >= 1
