from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RecordingEvidenceAdapter:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str, str, Any]] = []

    def emit_created(self, task_id: str, runtime_status: str, *args: Any, **kwargs: Any) -> None:
        self._record("created", task_id, runtime_status, args)

    def emit_started(self, task_id: str, runtime_status: str, *args: Any, **kwargs: Any) -> None:
        self._record("started", task_id, runtime_status, args)

    def emit_completed(self, task_id: str, runtime_status: str, *args: Any, **kwargs: Any) -> None:
        self._record("completed", task_id, runtime_status, args)

    def emit_failed(self, task_id: str, runtime_status: str, *args: Any, **kwargs: Any) -> None:
        self._record("failed", task_id, runtime_status, args)

    def emit_blocked(self, task_id: str, runtime_status: str, *args: Any, **kwargs: Any) -> None:
        self._record("blocked", task_id, runtime_status, args)

    def _record(self, phase: str, task_id: str, runtime_status: str, args: Any) -> None:
        self.calls.append((phase, task_id, runtime_status, args))
        if self.fail:
            raise RuntimeError("evidence adapter failure")


class TaskRuntimeHookAttachmentContractTest(unittest.TestCase):
    def _task(self, root: Path, task_id: str = "task-1", steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        task_dir = root / "tasks" / task_id
        return {
            "task_id": task_id,
            "task_name": task_id,
            "goal": "task runtime hook attachment probe",
            "status": "queued",
            "task_dir": str(task_dir),
            "runtime_state_file": str(task_dir / "runtime_state.json"),
            "steps": steps if steps is not None else [{"type": "final_answer", "content": "done"}],
            "current_step_index": 0,
        }

    def test_no_adapter_keeps_existing_behavior_shape(self) -> None:
        from core.runtime.task_runtime import TaskRuntime

        with tempfile.TemporaryDirectory() as tmp:
            runtime = TaskRuntime(workspace_root=str(Path(tmp) / "workspace"))
            task = self._task(Path(tmp), "no-adapter")
            result = runtime.mark_running(task, current_tick=1)

        self.assertIsNone(runtime.evidence_adapter)
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["status"], "running")
        self.assertEqual(
            set(result),
            {
                "ok",
                "status",
                "task",
                "runtime_state",
                "runtime_owner",
                "transition_owner",
                "transition_action",
            },
        )

    def test_adapter_created_event_called(self) -> None:
        from core.runtime.task_runtime import TaskRuntime

        adapter = RecordingEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TaskRuntime(workspace_root=str(Path(tmp) / "workspace"), evidence_adapter=adapter)
            runtime.ensure_runtime_state(self._task(Path(tmp), "created"))

        self.assertEqual(adapter.calls, [("created", "created", "queued", ())])

    def test_started_running_triggers_started(self) -> None:
        from core.runtime.task_runtime import TaskRuntime

        adapter = RecordingEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TaskRuntime(workspace_root=str(Path(tmp) / "workspace"), evidence_adapter=adapter)
            runtime.mark_running(self._task(Path(tmp), "started"), current_tick=1)

        self.assertEqual([call[0] for call in adapter.calls], ["created", "started"])
        self.assertEqual(adapter.calls[-1][2], "running")

    def test_completed_finished_triggers_completed(self) -> None:
        from core.runtime.task_runtime import TaskRuntime

        adapter = RecordingEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TaskRuntime(workspace_root=str(Path(tmp) / "workspace"), evidence_adapter=adapter)
            runtime.mark_finished(self._task(Path(tmp), "completed"), current_tick=2, final_answer="done")

        self.assertEqual([call[0] for call in adapter.calls], ["created", "completed"])
        self.assertEqual(adapter.calls[-1][2], "finished")

    def test_failed_error_triggers_failed(self) -> None:
        from core.runtime.task_runtime import TaskRuntime

        adapter = RecordingEvidenceAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TaskRuntime(workspace_root=str(Path(tmp) / "workspace"), evidence_adapter=adapter)
            runtime.mark_failed(
                self._task(Path(tmp), "failed"),
                current_tick=3,
                failure_type="internal_error",
                failure_message="boom",
            )

        self.assertEqual([call[0] for call in adapter.calls], ["created", "failed"])
        self.assertEqual(adapter.calls[-1][2], "failed")
        self.assertEqual(adapter.calls[-1][3][0], {"failure_type": "internal_error", "message": "boom"})

    def test_blocked_denied_replanning_trigger_blocked(self) -> None:
        from core.runtime.task_runtime import TaskRuntime

        observed: list[tuple[str, str, str, Any]] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for status in ("blocked", "denied", "replanning"):
                adapter = RecordingEvidenceAdapter()
                runtime = TaskRuntime(workspace_root=str(root / f"workspace-{status}"), evidence_adapter=adapter)
                runtime.mark_waiting_blocker(
                    self._task(root, f"blocked-{status}"),
                    current_tick=4,
                    blocker={"id": f"b-{status}", "type": "generic", "reason": status},
                    status=status,
                    reason=status,
                )
                observed.append(adapter.calls[-1])

        self.assertEqual([call[0] for call in observed], ["blocked", "blocked", "blocked"])
        self.assertEqual([call[1] for call in observed], ["blocked-blocked", "blocked-denied", "blocked-replanning"])

    def test_adapter_exception_does_not_change_result_or_state(self) -> None:
        from core.runtime.task_runtime import TaskRuntime

        adapter = RecordingEvidenceAdapter(fail=True)
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TaskRuntime(workspace_root=str(Path(tmp) / "workspace"), evidence_adapter=adapter)
            task = self._task(Path(tmp), "adapter-error")
            result = runtime.mark_running(task, current_tick=5)

        self.assertEqual(result["ok"], True)
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["runtime_state"]["status"], "running")
        self.assertEqual([call[0] for call in adapter.calls], ["created", "started"])

    def test_hook_event_order_deterministic(self) -> None:
        from core.runtime.task_runtime import TaskRuntime
        from core.runtime.task_runtime_evidence_adapter import TaskRuntimeEvidenceAdapter
        from core.runtime.task_runtime_evidence_boundary import TaskRuntimeEvidenceBoundary

        boundary = TaskRuntimeEvidenceBoundary("boundary-1")
        adapter = TaskRuntimeEvidenceAdapter("adapter-1", boundary)
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TaskRuntime(workspace_root=str(Path(tmp) / "workspace"), evidence_adapter=adapter)
            task = self._task(Path(tmp), "ordered")
            runtime.mark_running(task, current_tick=1)
            runtime.mark_finished(task, current_tick=2, final_answer="done")

        self.assertEqual(
            [event.phase for event in boundary.list_events()],
            ["task_created", "task_started", "task_completed"],
        )

    def test_task_runtime_does_not_expose_evidence_internals(self) -> None:
        from core.runtime.task_runtime import TaskRuntime
        from core.runtime.task_runtime_evidence_adapter import TaskRuntimeEvidenceAdapter
        from core.runtime.task_runtime_evidence_boundary import TaskRuntimeEvidenceBoundary

        boundary = TaskRuntimeEvidenceBoundary("boundary-1")
        adapter = TaskRuntimeEvidenceAdapter("adapter-1", boundary)
        with tempfile.TemporaryDirectory() as tmp:
            runtime = TaskRuntime(workspace_root=str(Path(tmp) / "workspace"), evidence_adapter=adapter)
            result = runtime.mark_running(self._task(Path(tmp), "no-internals"), current_tick=1)

        forbidden = {"evidence_adapter", "evidence_events", "boundary", "boundary_fingerprint", "adapter_fingerprint"}
        self.assertTrue(forbidden.isdisjoint(result))
        self.assertTrue(forbidden.isdisjoint(result["runtime_state"]))
        self.assertTrue(boundary.list_events())


if __name__ == "__main__":
    unittest.main()
