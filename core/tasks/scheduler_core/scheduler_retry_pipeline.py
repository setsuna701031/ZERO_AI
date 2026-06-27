from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from core.tasks.scheduler_core.repair_injection_execution import execute_repair_injection_transaction
from core.tasks.scheduler_core.repair_replay_continuation import (
    build_already_injected_replay_continuation,
    build_injected_replay_continuation,
)
from core.tasks.scheduler_core.retrying_repair_replay_state import prepare_retrying_repair_replay_state
from core.tasks.scheduler_core.retry_repair_helpers import (
    _zero_v734_build_retry_repair_steps,
    _zero_v734_read_runtime_state,
    _zero_v734_safe_now,
    _zero_v734_task_allows_auto_repair,
    _zero_v734_write_runtime_state,
)
from core.tasks.scheduler_core.task_scheduler_queue import STATUS_FAILED


def _zero_v734_land_repair_steps(
    scheduler: Any,
    task: Dict[str, Any],
    *,
    current_tick: Optional[int] = None,
    original_run_one_step: Any,
    build_retry_repair_steps: Any = _zero_v734_build_retry_repair_steps,
    read_runtime_state: Any = _zero_v734_read_runtime_state,
    write_runtime_state: Any = _zero_v734_write_runtime_state,
    allows_auto_repair: Any = _zero_v734_task_allows_auto_repair,
    now_provider: Any = _zero_v734_safe_now,
) -> Dict[str, Any]:
    replay_state = prepare_retrying_repair_replay_state(
        scheduler,
        task,
        read_runtime_state=read_runtime_state,
        allows_auto_repair=allows_auto_repair,
    )
    if replay_state.get("return_result") is not None:
        return replay_state["return_result"]

    task = replay_state["task"]
    task_id = replay_state["task_id"]
    if replay_state.get("delegate_original"):
        return original_run_one_step(scheduler, task=task, current_tick=current_tick)

    already_injected = replay_state["already_injected"]
    if already_injected["already_injected"]:
        continuation = build_already_injected_replay_continuation(
            task=task,
            task_id=task_id,
            already_injected=already_injected,
            persist_task_payload=scheduler._persist_task_payload,
        )
        _enqueue_replay_continuation_if_ready(scheduler, continuation)
        return continuation["result"]

    transaction = execute_repair_injection_transaction(
        task=task,
        task_id=task_id,
        runtime_state=replay_state.get("runtime_state"),
        repair_context=replay_state["repair_context"],
        steps=replay_state["steps"],
        step_index=replay_state["current_step_index"],
        failed_step=replay_state["failed_step"],
        current_tick=current_tick,
        build_retry_repair_steps=build_retry_repair_steps,
        write_runtime_state=write_runtime_state,
        persist_task_payload=scheduler._persist_task_payload,
        status_failed=STATUS_FAILED,
        now_provider=now_provider,
    )
    continuation = build_injected_replay_continuation(transaction)
    _enqueue_replay_continuation_if_ready(scheduler, continuation)
    return continuation["result"]


def _enqueue_replay_continuation_if_ready(scheduler: Any, continuation: Dict[str, Any]) -> None:
    enqueue_decision = continuation["enqueue_decision"]
    if not enqueue_decision["enqueue_ready"]:
        return
    enqueue_task = continuation["enqueue_task"]
    if isinstance(enqueue_task, dict):
        scheduler._enqueue_repo_task_if_ready(enqueue_task, overwrite=enqueue_decision["overwrite"])


def install_retrying_repair_bridge(
    scheduler_cls: Any,
    *,
    ready_statuses: Any,
    original_run_one_step_provider: Any = None,
    original_sync_runner_result_and_requeue_provider: Any = None,
    build_retry_repair_steps_provider: Any = None,
    read_runtime_state_provider: Any = None,
    write_runtime_state_provider: Any = None,
    allows_auto_repair_provider: Any = None,
    now_provider_provider: Any = None,
) -> Dict[str, Any]:
    try:
        ready_statuses.add("retrying")
    except Exception:
        pass

    original_run_one_step = scheduler_cls.run_one_step
    original_sync_runner_result_and_requeue = scheduler_cls._sync_runner_result_and_requeue_if_ready

    def _resolve(provider: Any, default: Any) -> Any:
        return provider() if callable(provider) else default

    def _zero_v734_run_one_step(self, task: Dict[str, Any], current_tick: Optional[int] = None) -> Dict[str, Any]:
        try:
            hydrated = self._hydrate_task_from_workspace(copy.deepcopy(task)) if isinstance(task, dict) else task
        except Exception:
            hydrated = task

        status = str(hydrated.get("status") or "").strip().lower() if isinstance(hydrated, dict) else ""
        if status in {"retrying", "retry"}:
            return self._compact_runner_result(
                _zero_v734_land_repair_steps(
                    self,
                    hydrated,
                    current_tick=current_tick,
                    original_run_one_step=_resolve(original_run_one_step_provider, original_run_one_step),
                    build_retry_repair_steps=_resolve(
                        build_retry_repair_steps_provider,
                        _zero_v734_build_retry_repair_steps,
                    ),
                    read_runtime_state=_resolve(read_runtime_state_provider, _zero_v734_read_runtime_state),
                    write_runtime_state=_resolve(write_runtime_state_provider, _zero_v734_write_runtime_state),
                    allows_auto_repair=_resolve(allows_auto_repair_provider, _zero_v734_task_allows_auto_repair),
                    now_provider=_resolve(now_provider_provider, _zero_v734_safe_now),
                )
            )

        return original_run_one_step(self, task=task, current_tick=current_tick)

    def _zero_v734_sync_runner_result_and_requeue_if_ready(
        self,
        task: Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> None:
        original_sync = _resolve(
            original_sync_runner_result_and_requeue_provider,
            original_sync_runner_result_and_requeue,
        )
        original_sync(self, task=task, runner_result=runner_result)
        try:
            task_id = self._extract_task_id(task)
            refreshed_task = self._get_task_from_repo(task_id)
            if isinstance(refreshed_task, dict):
                status = str(refreshed_task.get("status") or "").strip().lower()
                if status in {"retrying", "retry"}:
                    self._enqueue_repo_task_if_ready(refreshed_task, overwrite=True)
        except Exception:
            pass

    scheduler_cls.run_one_step = _zero_v734_run_one_step
    scheduler_cls._sync_runner_result_and_requeue_if_ready = _zero_v734_sync_runner_result_and_requeue_if_ready
    scheduler_cls.RETRYING_REPAIR_BRIDGE_VERSION = "v7.3.4"

    return {
        "_ZERO_V734_ORIGINAL_RUN_ONE_STEP": original_run_one_step,
        "_ZERO_V734_ORIGINAL_SYNC_RUNNER_RESULT_AND_REQUEUE": original_sync_runner_result_and_requeue,
        "_zero_v734_run_one_step": _zero_v734_run_one_step,
        "_zero_v734_sync_runner_result_and_requeue_if_ready": _zero_v734_sync_runner_result_and_requeue_if_ready,
    }
