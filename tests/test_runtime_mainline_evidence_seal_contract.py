from __future__ import annotations

import copy
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FakeRepo:
    def __init__(self, tasks: list[dict[str, Any]] | None = None) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}
        for task in tasks or []:
            self.upsert_task(task)

    def list_tasks(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(task) for task in self.tasks.values()]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        return copy.deepcopy(task) if isinstance(task, dict) else None

    def create_task(self, task: dict[str, Any]) -> bool:
        return self.upsert_task(task)

    def add_task(self, task: dict[str, Any]) -> bool:
        return self.upsert_task(task)

    def replace_task(self, task_id: str, task: dict[str, Any]) -> bool:
        self.tasks[task_id] = copy.deepcopy(task)
        return True

    def upsert_task(self, task: dict[str, Any]) -> bool:
        task_id = str(task.get("task_id") or task.get("task_name") or "")
        self.tasks[task_id] = copy.deepcopy(task)
        return True

    def set_task_status(self, task_id: str, status: str) -> bool:
        task = self.tasks.get(task_id)
        if not isinstance(task, dict):
            return False
        task["status"] = status
        return True


class FakeAgentLoop:
    def run_task_loop(self, **kwargs: Any) -> dict[str, Any]:
        task = copy.deepcopy(kwargs.get("task") or {})
        task["status"] = "running"
        return {
            "ok": True,
            "action": "agent_loop_result",
            "status": "running",
            "task_id": task.get("task_id"),
            "task": task,
            "final_answer": "seal scheduler dispatch ok",
        }


class FailingSchedulerAdapter:
    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def emit_enqueued(self, *args: Any, **kwargs: Any) -> Any:
        event = self.inner.emit_enqueued(*args, **kwargs)
        raise RuntimeError("scheduler evidence adapter failure")


class FailingTaskRuntimeAdapter:
    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def emit_created(self, *args: Any, **kwargs: Any) -> Any:
        event = self.inner.emit_created(*args, **kwargs)
        raise RuntimeError("task runtime evidence adapter failure")

    def emit_started(self, *args: Any, **kwargs: Any) -> Any:
        event = self.inner.emit_started(*args, **kwargs)
        raise RuntimeError("task runtime evidence adapter failure")


class FailingStepExecutorAdapter:
    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def emit_before_step(self, **kwargs: Any) -> Any:
        event = self.inner.emit_before_step(**kwargs)
        raise RuntimeError("step executor evidence adapter failure")

    def emit_after_step(self, **kwargs: Any) -> Any:
        event = self.inner.emit_after_step(**kwargs)
        raise RuntimeError("step executor evidence adapter failure")


class RuntimeMainlineEvidenceSealContractTest(unittest.TestCase):
    def _task(self, root: Path, task_id: str = "mainline-task") -> dict[str, Any]:
        task_dir = root / "tasks" / task_id
        return {
            "task_id": task_id,
            "task_name": task_id,
            "goal": "mainline evidence seal probe",
            "status": "queued",
            "task_dir": str(task_dir),
            "runtime_state_file": str(task_dir / "runtime_state.json"),
            "current_step_index": 0,
            "steps": [{"id": "step-1", "type": "seal_probe"}],
            "metadata": {"task_meta": {"items": ["stable-task"]}},
        }

    def _scheduler(self, tmp: Path, task: dict[str, Any], adapter: Any = None) -> Any:
        from core.tasks.scheduler import Scheduler

        return Scheduler(
            task_repo=FakeRepo([task]),
            workspace_dir=str(tmp / "workspace"),
            evidence_adapter=adapter,
            agent_loop=FakeAgentLoop(),
            scheduler_id="scheduler-mainline",
        )

    def _step_executor(self, tmp: Path, adapter: Any = None) -> Any:
        from core.runtime.step_executor import StepExecutor

        signature = inspect.signature(StepExecutor)
        kwargs: dict[str, Any] = {}
        if "workspace_root" in signature.parameters:
            kwargs["workspace_root"] = tmp / "workspace"
        if "runtime_store" in signature.parameters:
            kwargs["runtime_store"] = None
        if "tool_registry" in signature.parameters:
            kwargs["tool_registry"] = None
        if "llm_client" in signature.parameters:
            kwargs["llm_client"] = None
        if "debug" in signature.parameters:
            kwargs["debug"] = False
        kwargs["evidence_adapter"] = adapter
        executor = StepExecutor(**kwargs)
        executor.register_handler(
            "seal_probe",
            lambda step, task, context, previous: {
                "ok": True,
                "status": "success",
                "message": "sealed",
                "bundle_id": "bundle-mainline",
                "evidence_refs": {"artifact": "seal"},
            },
        )
        return executor

    def _adapters(self) -> dict[str, Any]:
        from core.runtime.scheduler_evidence_adapter import SchedulerEvidenceAdapter
        from core.runtime.scheduler_evidence_boundary import SchedulerEvidenceBoundary
        from core.runtime.step_executor_evidence_adapter import StepExecutorEvidenceAdapter
        from core.runtime.step_executor_evidence_hook import StepExecutorEvidenceHook
        from core.runtime.task_runtime_evidence_adapter import TaskRuntimeEvidenceAdapter
        from core.runtime.task_runtime_evidence_boundary import TaskRuntimeEvidenceBoundary

        scheduler_boundary = SchedulerEvidenceBoundary("scheduler-boundary")
        task_boundary = TaskRuntimeEvidenceBoundary("task-boundary")
        step_hook = StepExecutorEvidenceHook("step-hook")
        return {
            "scheduler_boundary": scheduler_boundary,
            "task_boundary": task_boundary,
            "step_hook": step_hook,
            "scheduler_adapter": SchedulerEvidenceAdapter("scheduler-adapter", scheduler_boundary),
            "task_adapter": TaskRuntimeEvidenceAdapter("task-adapter", task_boundary),
            "step_adapter": StepExecutorEvidenceAdapter("step-adapter", step_hook),
        }

    def _run_cross_layer_flow(self) -> dict[str, Any]:
        from core.runtime.task_runtime import TaskRuntime

        adapters = self._adapters()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            task = self._task(tmp)
            scheduler = self._scheduler(tmp, task, adapters["scheduler_adapter"])
            runtime = TaskRuntime(
                workspace_root=str(tmp / "workspace"),
                evidence_adapter=adapters["task_adapter"],
            )
            executor = self._step_executor(tmp, adapters["step_adapter"])

            enqueue_result = scheduler.enqueue(task["task_id"])
            dequeued_task_id = scheduler.dequeue()
            dispatch_result = scheduler.run_one_step(task, current_tick=1)
            running_result = runtime.mark_running(task, current_tick=2)
            step = {
                "id": "step-1",
                "type": "seal_probe",
                "attempt": 1,
                "max_attempts": 1,
                "metadata": {"step_meta": {"items": ["stable-step"]}},
            }
            step_result = executor.execute_step(step, task=task)
            step["metadata"]["step_meta"]["items"].append("external-mutation")
            task["metadata"]["task_meta"]["items"].append("external-mutation")
            finished_result = runtime.mark_finished(
                task,
                current_tick=3,
                final_answer="sealed",
            )
            scheduler_status = scheduler.status()

        scheduler_events = adapters["scheduler_boundary"].list_events()
        task_events = adapters["task_boundary"].list_events()
        step_events = adapters["step_hook"].list_events()
        return {
            **adapters,
            "results": {
                "enqueue": enqueue_result,
                "dequeue": dequeued_task_id,
                "dispatch": dispatch_result,
                "running": running_result,
                "step": step_result,
                "finished": finished_result,
                "scheduler_status": scheduler_status,
            },
            "transcript": (
                [("scheduler", event.orchestration_phase) for event in scheduler_events]
                + [("task_runtime", event.phase) for event in task_events]
                + [("step_executor", event.phase) for event in step_events]
            ),
            "fingerprints": (
                [event.fingerprint for event in scheduler_events]
                + [event.fingerprint for event in task_events]
                + [event.fingerprint for event in step_events]
            ),
            "adapter_fingerprints": (
                adapters["scheduler_adapter"].fingerprint,
                adapters["task_adapter"].fingerprint,
                adapters["step_adapter"].fingerprint,
            ),
        }

    def test_cross_layer_evidence_flow_success(self) -> None:
        flow = self._run_cross_layer_flow()

        self.assertIs(flow["results"]["enqueue"], True)
        self.assertEqual(flow["results"]["dequeue"], "mainline-task")
        self.assertTrue(flow["results"]["dispatch"].get("ok"))
        self.assertEqual(flow["results"]["running"]["status"], "running")
        self.assertTrue(flow["results"]["step"].get("ok"))
        self.assertEqual(flow["results"]["finished"]["status"], "finished")

    def test_deterministic_cross_layer_ordering(self) -> None:
        flow = self._run_cross_layer_flow()

        self.assertEqual(
            flow["transcript"],
            [
                ("scheduler", "task_enqueued"),
                ("scheduler", "task_dequeued"),
                ("scheduler", "task_dispatched"),
                ("task_runtime", "task_created"),
                ("task_runtime", "task_started"),
                ("task_runtime", "task_completed"),
                ("step_executor", "before_step"),
                ("step_executor", "after_step"),
            ],
        )

    def test_deterministic_cross_layer_fingerprints_repeat(self) -> None:
        first = self._run_cross_layer_flow()
        second = self._run_cross_layer_flow()

        self.assertEqual(first["fingerprints"], second["fingerprints"])
        self.assertEqual(first["adapter_fingerprints"], second["adapter_fingerprints"])

    def test_evidence_copy_on_read_and_after_mutation_isolation(self) -> None:
        flow = self._run_cross_layer_flow()
        step_events = flow["step_hook"].list_events()
        after_step = step_events[-1]
        metadata = after_step.metadata
        runtime_args = after_step.runtime_args
        evidence_refs = after_step.evidence_refs

        metadata["step_metadata"]["step_meta"]["items"].append("polluted")
        metadata["task_metadata"]["task_meta"]["items"].append("polluted")
        runtime_args["attempt"] = 999
        evidence_refs["evidence_refs"]["artifact"] = "polluted"

        self.assertEqual(
            after_step.metadata,
            {
                "step_metadata": {"step_meta": {"items": ["stable-step"]}},
                "task_metadata": {"task_meta": {"items": ["stable-task"]}},
            },
        )
        self.assertEqual(
            after_step.runtime_args,
            {"attempt": 1, "max_attempts": 1},
        )
        self.assertEqual(
            after_step.evidence_refs,
            {
                "bundle_id": "bundle-mainline",
                "evidence_refs": {"artifact": "seal"},
            },
        )

    def test_adapter_exception_does_not_affect_runtime_result(self) -> None:
        from core.runtime.scheduler_evidence_adapter import SchedulerEvidenceAdapter
        from core.runtime.scheduler_evidence_boundary import SchedulerEvidenceBoundary
        from core.runtime.step_executor_evidence_adapter import StepExecutorEvidenceAdapter
        from core.runtime.step_executor_evidence_hook import StepExecutorEvidenceHook
        from core.runtime.task_runtime import TaskRuntime
        from core.runtime.task_runtime_evidence_adapter import TaskRuntimeEvidenceAdapter
        from core.runtime.task_runtime_evidence_boundary import TaskRuntimeEvidenceBoundary

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            task = self._task(tmp, "failure-is-observed")
            scheduler = self._scheduler(
                tmp,
                task,
                FailingSchedulerAdapter(
                    SchedulerEvidenceAdapter(
                        "scheduler-adapter",
                        SchedulerEvidenceBoundary("scheduler-boundary"),
                    )
                ),
            )
            runtime = TaskRuntime(
                workspace_root=str(tmp / "workspace"),
                evidence_adapter=FailingTaskRuntimeAdapter(
                    TaskRuntimeEvidenceAdapter(
                        "task-adapter",
                        TaskRuntimeEvidenceBoundary("task-boundary"),
                    )
                ),
            )
            executor = self._step_executor(
                tmp,
                FailingStepExecutorAdapter(
                    StepExecutorEvidenceAdapter(
                        "step-adapter",
                        StepExecutorEvidenceHook("step-hook"),
                    )
                ),
            )

            self.assertIs(scheduler.enqueue(task["task_id"]), True)
            running = runtime.mark_running(task, current_tick=1)
            step_result = executor.execute_step(
                {"id": "step-1", "type": "seal_probe"},
                task=task,
            )

        self.assertEqual(running["status"], "running")
        self.assertTrue(step_result.get("ok"))
        self.assertEqual(step_result.get("message"), "sealed")

    def test_no_evidence_internals_leak_to_runtime_outputs(self) -> None:
        flow = self._run_cross_layer_flow()
        forbidden = {
            "evidence",
            "evidence_adapter",
            "evidence_events",
            "boundary",
            "boundary_fingerprint",
            "adapter_fingerprint",
            "hook",
            "hook_fingerprint",
        }

        self.assertTrue(forbidden.isdisjoint(flow["results"]["scheduler_status"]))
        self.assertTrue(forbidden.isdisjoint(flow["results"]["running"]))
        self.assertTrue(forbidden.isdisjoint(flow["results"]["running"]["runtime_state"]))
        self.assertTrue(forbidden.isdisjoint(flow["results"]["step"]))
        self.assertTrue(forbidden.isdisjoint(flow["results"]["finished"]))

    def test_hooks_and_adapters_are_observational_only(self) -> None:
        from core.runtime.task_runtime import TaskRuntime

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            task = self._task(tmp, "observational")
            baseline_scheduler = self._scheduler(tmp, task)
            baseline_enqueue = baseline_scheduler.enqueue(task["task_id"])
            baseline_step = self._step_executor(tmp).execute_step(
                {"id": "step-1", "type": "seal_probe"},
                task=task,
            )
            baseline_running = TaskRuntime(
                workspace_root=str(tmp / "baseline-workspace"),
            ).mark_running(task, current_tick=1)

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            task = self._task(tmp, "observational")
            adapters = self._adapters()
            observed_scheduler = self._scheduler(tmp, task, adapters["scheduler_adapter"])
            observed_enqueue = observed_scheduler.enqueue(task["task_id"])
            observed_step = self._step_executor(tmp, adapters["step_adapter"]).execute_step(
                {"id": "step-1", "type": "seal_probe"},
                task=task,
            )
            observed_running = TaskRuntime(
                workspace_root=str(tmp / "observed-workspace"),
                evidence_adapter=adapters["task_adapter"],
            ).mark_running(task, current_tick=1)

        self.assertEqual(observed_enqueue, baseline_enqueue)
        self.assertEqual(observed_step.get("ok"), baseline_step.get("ok"))
        self.assertEqual(observed_step.get("message"), baseline_step.get("message"))
        self.assertEqual(observed_running["status"], baseline_running["status"])
        self.assertEqual(
            observed_running["runtime_state"]["status"],
            baseline_running["runtime_state"]["status"],
        )

    def test_zero_system_boot_wires_mainline_evidence_contracts(self) -> None:
        from services.system_boot import ZeroSystem

        with tempfile.TemporaryDirectory() as tmp_name:
            system = ZeroSystem(workspace=str(Path(tmp_name) / "workspace"))
            system.step_executor.register_handler(
                "seal_probe",
                lambda step, task, context, previous: {
                    "ok": True,
                    "status": "success",
                    "message": "sealed",
                    "bundle_id": system.runtime_evidence_seal.evidence_refs["bundle_id"],
                },
            )
            result = system.step_executor.execute_step(
                {"id": "step-1", "type": "seal_probe"},
                task=self._task(Path(tmp_name), "boot-mainline"),
            )

        seal = system.runtime_evidence_seal

        self.assertIsNotNone(seal)
        self.assertIs(system.scheduler.evidence_adapter, seal.scheduler_adapter)
        self.assertIs(system.task_runtime.evidence_adapter, seal.task_adapter)
        self.assertIs(system.step_executor.evidence_adapter, seal.step_adapter)
        self.assertTrue(result.get("ok"))
        self.assertEqual(
            [event.phase for event in seal.step_hook.list_events()],
            ["before_step", "after_step"],
        )
        self.assertEqual(
            [item["type"] for item in seal.emitter.emission_order],
            ["snapshot", "replay", "audit", "rollback", "bundle"],
        )
        self.assertEqual(
            seal.evidence_records["bundle"].aggregate_status,
            "succeeded",
        )


if __name__ == "__main__":
    unittest.main()
