from __future__ import annotations


def test_v7337_create_task_compat_uses_late_bound_originals(monkeypatch) -> None:
    import core.tasks.scheduler as scheduler_module

    class FakeScheduler:
        def _build_scheduler_authority_context(self, task):
            return {"task_id": task.get("task_id")}

    original_try = scheduler_module._ZERO_V7337_ORIGINAL_SCHEDULER_TRY_FORCE_REPO_EDIT_AT_CREATE_TASK
    original_create = scheduler_module._ZERO_V7337_ORIGINAL_SCHEDULER_CREATE_TASK_RECORD
    try:
        monkeypatch.setattr(
            scheduler_module,
            "_ZERO_V7337_ORIGINAL_SCHEDULER_TRY_FORCE_REPO_EDIT_AT_CREATE_TASK",
            lambda self, goal: {"ok": True, "source": "patched-try", "goal": goal},
        )
        monkeypatch.setattr(
            scheduler_module,
            "_ZERO_V7337_ORIGINAL_SCHEDULER_CREATE_TASK_RECORD",
            lambda self, *args, **kwargs: {
                "task_id": "patched-create",
                "planner_result": {
                    "forced_repo_edit": {
                        "execution_intent_only": True,
                    },
                },
                "last_step_result": {"stale": True},
                "results": [{"stale": True}],
                "step_results": [{"stale": True}],
            },
        )

        scheduler = FakeScheduler()
        assert scheduler_module._zero_v7337_scheduler_try_force_repo_edit_at_create_task(
            scheduler,
            "ordinary goal",
        ) == {"ok": True, "source": "patched-try", "goal": "ordinary goal"}

        task = scheduler_module._zero_v7337_scheduler_create_task_record(scheduler, "goal")
        assert task["status"] == "queued"
        assert task["execution_intent_only"] is True
        assert task["mutation_executed"] is False
        assert task["last_step_result"] is None
        assert task["results"] == []
        assert task["authority_context"] == {"task_id": "patched-create"}
    finally:
        monkeypatch.setattr(
            scheduler_module,
            "_ZERO_V7337_ORIGINAL_SCHEDULER_TRY_FORCE_REPO_EDIT_AT_CREATE_TASK",
            original_try,
        )
        monkeypatch.setattr(
            scheduler_module,
            "_ZERO_V7337_ORIGINAL_SCHEDULER_CREATE_TASK_RECORD",
            original_create,
        )
