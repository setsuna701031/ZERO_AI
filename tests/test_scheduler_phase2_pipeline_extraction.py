from __future__ import annotations

from types import SimpleNamespace

from core.tasks.scheduler_core.runtime_dispatch_gate import runtime_dispatch_gate_decision
from core.tasks.scheduler_core.scheduler_execution_pipeline import build_terminal_skip_runner_result
from core.tasks.scheduler_core.scheduler_replan_pipeline import apply_replan_task, preview_replan_task
from core.tasks.scheduler_core.status_write_pipeline import emit_scheduler_evidence


class _SchedulerLike:
    def _safe_int_for_runtime_gate(self, value, default=0):
        try:
            return int(value)
        except Exception:
            return default

    def _active_runtime_gate_blockers(self, blockers):
        return [item for item in blockers or [] if item.get("status") != "resolved"]

    def _extract_task_id(self, task):
        return str(task.get("task_id") or task.get("id") or "")


def test_runtime_dispatch_gate_blocks_pending_review_without_scheduler_import() -> None:
    scheduler = _SchedulerLike()

    decision = runtime_dispatch_gate_decision(
        scheduler,
        {"task_id": "t1", "requires_review": True},
        terminal_statuses={"finished", "failed"},
        status_review_required="review_required",
    )

    assert decision["allow"] is False
    assert decision["reason"] == "review_required"
    assert decision["status"] == "review_required"
    assert decision["next_action"] == "wait_for_external_event"


def test_status_write_evidence_preserves_legacy_adapter_shape() -> None:
    calls = []

    class Adapter:
        def emit_requeued(self, scheduler_id, task_id, queue_name, reason):
            calls.append((scheduler_id, task_id, queue_name, reason))

    scheduler = SimpleNamespace(scheduler_id="sched-a", evidence_adapter=Adapter())

    emit_scheduler_evidence(
        scheduler,
        "requeued",
        task_id="task-a",
        queue_name="ready",
        reason="retry",
    )

    assert calls == [("sched-a", "task-a", "ready", "retry")]


def test_execution_pipeline_terminal_skip_result_loads_runtime_state() -> None:
    class Runtime:
        def load_runtime_state(self, task):
            return {"task_id": task["task_id"], "status": "finished"}

    scheduler = _SchedulerLike()
    scheduler.task_runtime = Runtime()

    result = build_terminal_skip_runner_result(
        scheduler,
        task={"task_id": "task-a", "status": "finished", "final_answer": "done"},
    )

    assert result["ok"] is True
    assert result["action"] == "terminal_skip"
    assert result["runtime_state"] == {"task_id": "task-a", "status": "finished"}


def test_replan_pipeline_apply_and_preview_preserve_result_shape() -> None:
    class SchedulerLike:
        def _try_replan_task(self, task, apply=False):
            if apply:
                task["status"] = "queued"
                return {"ok": True, "replanned": True}
            return {
                "ok": True,
                "would_replan": True,
                "decision": "suggested",
                "raw_replan_result": {"plan": {"steps": [{"type": "read_file"}]}},
            }

        def _fingerprint_steps(self, steps):
            return f"fp:{len(steps)}"

        def _replan_budget_payload(self, task):
            return {"replan_count": 0, "max_replans": 3, "remaining": 3}

        def _get_failed_step_type(self, task):
            return "verify"

    scheduler = SchedulerLike()
    task = {"task_id": "task-a", "status": "failed", "steps": [{"type": "verify"}]}

    applied = apply_replan_task(scheduler, task)
    preview = preview_replan_task(scheduler, task)

    assert applied["mode"] == "replan_apply"
    assert applied["approved"] is True
    assert preview["mode"] == "replan_preview"
    assert preview["would_replan"] is True
    assert preview["preview_step_count"] == 1
