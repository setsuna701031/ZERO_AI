from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List

from core.worker.worker_contracts import (
    WorkerResult,
    WorkerTask,
    create_worker_result,
    create_worker_state_snapshot,
    create_worker_task,
    ensure_worker_result_contract,
    ensure_worker_task_contract,
)


RunnerFn = Callable[[Dict[str, Any]], Dict[str, Any]]


class WorkerRuntime:
    """
    Minimal orchestration layer for worker tasks.

    This runtime does not choose strategy and does not execute tools directly.
    It only creates contracted worker tasks, delegates them to an injected ZERO
    runtime callable, collects worker_result payloads, and snapshots state.
    """

    def __init__(self, *, runner: RunnerFn | None = None) -> None:
        self.runner = runner
        self._active_tasks: Dict[str, Dict[str, Any]] = {}
        self._completed_results: Dict[str, Dict[str, Any]] = {}
        self._blocked_results: Dict[str, Dict[str, Any]] = {}
        self._artifacts_index: Dict[str, List[Dict[str, Any]]] = {}
        self._last_decision = ""
        self._handoff_notes = ""

    def create_task(
        self,
        *,
        task_id: str,
        parent_task_id: str = "",
        role: str = "worker",
        objective: str = "",
        input_context: Dict[str, Any] | None = None,
        **strategy_fields: Any,
    ) -> Dict[str, Any]:
        task = create_worker_task(
            task_id=task_id,
            parent_task_id=parent_task_id,
            role=role,
            objective=objective,
            input_context=input_context,
            **strategy_fields,
        )
        payload = task.to_dict()
        self._active_tasks[payload["task_id"]] = copy.deepcopy(payload)
        self._last_decision = "created_worker_task"
        return copy.deepcopy(payload)

    def run_task(self, worker_task: WorkerTask | Dict[str, Any]) -> Dict[str, Any]:
        task_payload = self._coerce_task(worker_task)
        if self.runner is None:
            return {
                "ok": False,
                "status": "blocked",
                "worker_task": copy.deepcopy(task_payload),
                "error": "worker runtime has no delegated ZERO runner",
            }

        result = self.runner(copy.deepcopy(task_payload))
        if not isinstance(result, dict):
            result = {
                "ok": False,
                "status": "failed",
                "error": "delegated ZERO runner returned invalid result",
                "raw_result": result,
            }

        result.setdefault("worker_task", copy.deepcopy(task_payload))
        return copy.deepcopy(result)

    def collect_result(
        self,
        worker_task: WorkerTask | Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        task_payload = self._coerce_task(worker_task)
        source = runner_result if isinstance(runner_result, dict) else {}

        explicit = source.get("worker_result")
        if isinstance(explicit, WorkerResult):
            result_payload = explicit.to_dict()
        elif isinstance(explicit, dict):
            result_payload = ensure_worker_result_contract(explicit)
        else:
            result_payload = create_worker_result(
                task_id=task_payload["task_id"],
                status=self._derive_status(source),
                summary=self._derive_summary(source),
                result=self._derive_result(source),
                artifacts=self._derive_artifacts(source),
                trace=self._derive_trace(source),
                open_questions=self._derive_open_questions(source),
                confidence=self._derive_confidence(source),
            ).to_dict()

        ensure_worker_result_contract(result_payload)
        return copy.deepcopy(result_payload)

    def merge_result(self, worker_result: WorkerResult | Dict[str, Any]) -> Dict[str, Any]:
        result_payload = self._coerce_result(worker_result)
        task_id = result_payload["task_id"]
        status = result_payload["status"]

        self._active_tasks.pop(task_id, None)
        if status in {"success", "partial"}:
            self._completed_results[task_id] = copy.deepcopy(result_payload)
            self._blocked_results.pop(task_id, None)
        else:
            self._blocked_results[task_id] = copy.deepcopy(result_payload)
            self._completed_results.pop(task_id, None)

        artifacts = result_payload.get("artifacts")
        if isinstance(artifacts, list):
            self._artifacts_index[task_id] = [copy.deepcopy(item) for item in artifacts if isinstance(item, dict)]

        self._last_decision = "merged_worker_result"
        return self.snapshot_state()

    def snapshot_state(self, *, handoff_notes: str = "") -> Dict[str, Any]:
        if handoff_notes:
            self._handoff_notes = str(handoff_notes).strip()

        snapshot = create_worker_state_snapshot(
            active_tasks=list(self._active_tasks.values()),
            completed_tasks=list(self._completed_results.values()),
            blocked_tasks=list(self._blocked_results.values()),
            artifacts_index=self._artifacts_index,
            last_decision=self._last_decision,
            handoff_notes=self._handoff_notes,
        )
        return snapshot.to_dict()

    def _coerce_task(self, worker_task: WorkerTask | Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(worker_task, WorkerTask):
            payload = worker_task.to_dict()
        else:
            payload = copy.deepcopy(worker_task)
        return ensure_worker_task_contract(payload)

    def _coerce_result(self, worker_result: WorkerResult | Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(worker_result, WorkerResult):
            payload = worker_result.to_dict()
        else:
            payload = copy.deepcopy(worker_result)
        return ensure_worker_result_contract(payload)

    def _derive_status(self, source: Dict[str, Any]) -> str:
        status = str(source.get("status") or "").strip().lower()
        if status in {"success", "partial", "failed", "blocked"}:
            return status
        if source.get("ok") is True:
            return "success"
        if source.get("ok") is False:
            return "failed"
        return "partial"

    def _derive_summary(self, source: Dict[str, Any]) -> str:
        for key in ("summary", "final_answer", "result_summary", "error"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        display_state = source.get("display_state")
        if isinstance(display_state, dict):
            for key in ("result_summary", "persona_final_reply", "blocked_reason"):
                value = display_state.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    def _derive_result(self, source: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("result", "last_result", "display_state", "runtime_state"):
            value = source.get(key)
            if isinstance(value, dict):
                return copy.deepcopy(value)
        return copy.deepcopy(source)

    def _derive_artifacts(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        artifacts = source.get("artifacts")
        if isinstance(artifacts, list):
            return [copy.deepcopy(item) for item in artifacts if isinstance(item, dict)]

        display_state = source.get("display_state")
        if isinstance(display_state, dict):
            artifacts = display_state.get("artifacts")
            if isinstance(artifacts, list):
                return [copy.deepcopy(item) for item in artifacts if isinstance(item, dict)]

        return []

    def _derive_trace(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        for key in ("trace", "execution_trace", "execution_log"):
            value = source.get(key)
            if isinstance(value, list):
                return [copy.deepcopy(item) for item in value if isinstance(item, dict)]

        display_state = source.get("display_state")
        if isinstance(display_state, dict):
            value = display_state.get("trace")
            if isinstance(value, list):
                return [copy.deepcopy(item) for item in value if isinstance(item, dict)]

        return []

    def _derive_open_questions(self, source: Dict[str, Any]) -> List[str]:
        value = source.get("open_questions")
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _derive_confidence(self, source: Dict[str, Any]) -> float:
        try:
            return float(source.get("confidence", 1.0))
        except Exception:
            return 0.0
