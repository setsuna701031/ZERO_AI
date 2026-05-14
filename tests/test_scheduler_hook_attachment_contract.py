from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RecordingSchedulerEvidenceAdapter:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str, str, str, Any]] = []

    def emit_enqueued(self, scheduler_id: str, task_id: str, queue_name: str, *args: Any, **kwargs: Any) -> None:
        self._record("enqueued", scheduler_id, task_id, queue_name, args)

    def emit_dequeued(self, scheduler_id: str, task_id: str, queue_name: str, *args: Any, **kwargs: Any) -> None:
        self._record("dequeued", scheduler_id, task_id, queue_name, args)

    def emit_dispatched(self, scheduler_id: str, task_id: str, queue_name: str, *args: Any, **kwargs: Any) -> None:
        self._record("dispatched", scheduler_id, task_id, queue_name, args)

    def emit_requeued(self, scheduler_id: str, task_id: str, queue_name: str, *args: Any, **kwargs: Any) -> None:
        self._record("requeued", scheduler_id, task_id, queue_name, args)

    def emit_cancelled(self, scheduler_id: str, task_id: str, queue_name: str, *args: Any, **kwargs: Any) -> None:
        self._record("cancelled", scheduler_id, task_id, queue_name, args)

    def _record(self, phase: str, scheduler_id: str, task_id: str, queue_name: str, args: Any) -> None:
        self.calls.append((phase, scheduler_id, task_id, queue_name, args))
        if self.fail:
            raise RuntimeError("scheduler evidence adapter failure")


class FakeRepo:
    def __init__(self, tasks: list[dict[str, Any]] | None = None) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}
        for task in tasks or []:
            task_id = str(task.get("task_id") or task.get("task_name") or "")
            self.tasks[task_id] = copy.deepcopy(task)

    def list_tasks(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(task) for task in self.tasks.values()]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        return copy.deepcopy(task) if isinstance(task, dict) else None

    def create_task(self, task: dict[str, Any]) -> bool:
        task_id = str(task.get("task_id") or task.get("task_name") or "")
        self.tasks[task_id] = copy.deepcopy(task)
        return True

    def add_task(self, task: dict[str, Any]) -> bool:
        return self.create_task(task)

    def replace_task(self, task_id: str, task: dict[str, Any]) -> bool:
        self.tasks[task_id] = copy.deepcopy(task)
        return True

    def upsert_task(self, task: dict[str, Any]) -> bool:
        return self.create_task(task)

    def set_task_status(self, task_id: str, status: str) -> bool:
        task = self.tasks.get(task_id)
        if not isinstance(task, dict):
            return False
        task["status"] = status
        return True


class FakeAgentLoop:
    def __init__(self, status: str = "running") -> None:
        self.status = status

    def run_task_loop(self, **kwargs: Any) -> dict[str, Any]:
        task = copy.deepcopy(kwargs.get("task") or {})
        task["status"] = self.status
        return {
            "ok": True,
            "action": "agent_loop_result",
            "status": self.status,
            "task_id": task.get("task_id"),
            "task": task,
            "final_answer": "ok",
        }


class SchedulerHookAttachmentContractTest(unittest.TestCase):
    def _task(self, task_id: str = "task-1", status: str = "queued") -> dict[str, Any]:
        return {
            "task_id": task_id,
            "task_name": task_id,
            "goal": "scheduler hook attachment probe",
            "status": status,
            "priority": 0,
            "current_step_index": 0,
            "steps": [{"type": "final_answer", "content": "done"}],
            "steps_total": 1,
            "history": [status],
        }

    def _scheduler(self, adapter: Any = None, repo: Any = None, agent_loop: Any = None):
        from core.tasks.scheduler import Scheduler

        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        return Scheduler(
            task_repo=repo if repo is not None else FakeRepo(),
            workspace_dir=str(Path(workspace.name) / "workspace"),
            evidence_adapter=adapter,
            agent_loop=agent_loop,
            scheduler_id="scheduler-1",
        )

    def test_no_adapter_keeps_existing_behavior(self) -> None:
        scheduler = self._scheduler()

        result = scheduler.enqueue("task-1")

        self.assertIsNone(scheduler.evidence_adapter)
        self.assertIs(result, True)
        self.assertEqual(scheduler.queue, ["task-1"])

    def test_adapter_enqueue_triggers_enqueued(self) -> None:
        adapter = RecordingSchedulerEvidenceAdapter()
        scheduler = self._scheduler(adapter=adapter)

        self.assertIs(scheduler.enqueue("task-1"), True)

        self.assertEqual(adapter.calls, [("enqueued", "scheduler-1", "task-1", "task_queue", ())])

    def test_run_next_pop_queue_triggers_dequeued(self) -> None:
        adapter = RecordingSchedulerEvidenceAdapter()
        scheduler = self._scheduler(adapter=adapter)
        scheduler.enqueue("task-1")

        self.assertEqual(scheduler.dequeue(), "task-1")

        self.assertEqual([call[0] for call in adapter.calls], ["enqueued", "dequeued"])

    def test_dispatch_to_runtime_triggers_dispatched(self) -> None:
        adapter = RecordingSchedulerEvidenceAdapter()
        repo = FakeRepo([self._task("task-1")])
        scheduler = self._scheduler(adapter=adapter, repo=repo, agent_loop=FakeAgentLoop())

        result = scheduler.run_one_step(self._task("task-1"), current_tick=1)

        self.assertEqual(result["task_id"], "task-1")
        self.assertIn("dispatched", [call[0] for call in adapter.calls])
        self.assertEqual(adapter.calls[0][:4], ("dispatched", "scheduler-1", "task-1", "runtime"))

    def test_requeue_retry_replanning_triggers_requeued(self) -> None:
        adapter = RecordingSchedulerEvidenceAdapter()
        repo = FakeRepo([self._task("task-1")])
        scheduler = self._scheduler(adapter=adapter, repo=repo)

        scheduler._sync_runner_result_and_requeue_if_ready(
            task=self._task("task-1"),
            runner_result={
                "ok": True,
                "status": "retry",
                "task_id": "task-1",
                "task": self._task("task-1", status="retry"),
            },
        )

        self.assertIn("requeued", [call[0] for call in adapter.calls])

    def test_cancel_remove_triggers_cancelled(self) -> None:
        adapter = RecordingSchedulerEvidenceAdapter()
        repo = FakeRepo([self._task("task-1")])
        scheduler = self._scheduler(adapter=adapter, repo=repo)

        result = scheduler.cancel_task("task-1")

        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(adapter.calls[-1][0], "cancelled")
        self.assertEqual(adapter.calls[-1][2], "task-1")

    def test_adapter_exception_does_not_change_scheduler_result_or_state(self) -> None:
        adapter = RecordingSchedulerEvidenceAdapter(fail=True)
        scheduler = self._scheduler(adapter=adapter)

        result = scheduler.enqueue("task-1")

        self.assertIs(result, True)
        self.assertEqual(scheduler.queue, ["task-1"])
        self.assertEqual([call[0] for call in adapter.calls], ["enqueued"])

    def test_hook_event_order_deterministic(self) -> None:
        adapter = RecordingSchedulerEvidenceAdapter()
        repo = FakeRepo([self._task("task-1")])
        scheduler = self._scheduler(adapter=adapter, repo=repo, agent_loop=FakeAgentLoop())

        scheduler.enqueue("task-1")
        scheduler.dequeue()
        scheduler.run_one_step(self._task("task-1"), current_tick=1)
        scheduler.cancel_task("task-1")

        self.assertEqual(
            [call[0] for call in adapter.calls],
            ["enqueued", "dequeued", "dispatched", "cancelled"],
        )

    def test_scheduler_does_not_expose_evidence_internals(self) -> None:
        adapter = RecordingSchedulerEvidenceAdapter()
        scheduler = self._scheduler(adapter=adapter)

        scheduler.enqueue("task-1")
        status = scheduler.status()

        forbidden = {
            "evidence_adapter",
            "evidence_events",
            "boundary",
            "boundary_fingerprint",
            "adapter_fingerprint",
        }
        self.assertTrue(forbidden.isdisjoint(status))
        self.assertTrue(forbidden.isdisjoint(status.get("ready_queue", [])))
        self.assertEqual(adapter.calls[0][0], "enqueued")


if __name__ == "__main__":
    unittest.main()
