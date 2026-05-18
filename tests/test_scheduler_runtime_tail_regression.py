from __future__ import annotations

import copy
import time
from typing import Any, Dict, List

import pytest

import core.tasks.scheduler as scheduler_module
from core.tasks.scheduler import Scheduler


# REPLAY_MATRIX
# | replay class | status |
# | --- | --- |
# | normal replay | covered |
# | stale replay | covered |
# | duplicate replay | covered |
# | failed replay | covered |
# | partial replay | partially covered |
# | retry replay | covered |
# | repair injection replay | covered |
# | pending lock replay | covered |
# | terminal task replay protection | covered |


class EmptyDispatcher:
    def list_queued(self) -> List[Dict[str, Any]]:
        return []


def test_v724_queue_hygiene_does_not_fail_successful_finished_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = Scheduler.__new__(Scheduler)
    finished_task = {
        "task_id": "repair-finished-1",
        "status": "finished",
        "created_at": int(time.time()) - 9999,
        "repair_context": {"enabled": True},
    }
    original_task = copy.deepcopy(finished_task)
    failed: List[Dict[str, Any]] = []
    cancelled: List[str] = []
    saved_indexes: List[Dict[str, Any]] = []

    monkeypatch.setattr(
        scheduler_module,
        "_ZERO_V724_ORIGINAL_CLEANUP_TASK_QUEUE_HYGIENE",
        lambda self, **kwargs: {"ok": True, "base": "called"},
    )

    scheduler.dispatcher = EmptyDispatcher()
    scheduler._load_repair_fingerprint_index = lambda: {}
    scheduler._save_repair_fingerprint_index = lambda data: None
    scheduler._list_repo_tasks = lambda: [finished_task]
    scheduler._get_task_from_repo = lambda task_id: finished_task
    scheduler._validate_repair_task_scope = lambda task: {"ok": True}
    scheduler._is_autonomous_repair_task = lambda task: True
    scheduler._repair_task_fingerprint_from_task = lambda task: "fingerprint-1"
    scheduler._is_legacy_self_edit_scheduler_task = lambda task: False
    scheduler._fail_task_for_queue_hygiene = lambda task, reason: failed.append(
        {"task_id": task.get("task_id"), "reason": reason}
    )
    scheduler._cancel_ready_queue_task = lambda task_id: cancelled.append(task_id)
    scheduler._save_repair_fingerprint_index = lambda data: saved_indexes.append(copy.deepcopy(data))

    result = scheduler.cleanup_task_queue_hygiene(max_queued_age_seconds=1)

    assert result["ok"] is True
    assert result["expired_repair"] == []
    assert result["invalid_repair"] == []
    assert result["duplicate_repair"] == []
    assert failed == []
    assert cancelled == []
    assert saved_indexes == []
    assert finished_task == original_task


def test_duplicate_repair_suppression_does_not_block_after_stale_queued_repair_expires() -> None:
    scheduler = Scheduler.__new__(Scheduler)
    fingerprint = "stale-repair-fingerprint"
    stale_task = {
        "task_id": "repair-stale-1",
        "status": "queued",
        "repair_fingerprint": fingerprint,
    }
    failed: List[Dict[str, Any]] = []
    cancelled: List[str] = []
    removed: List[str] = []

    scheduler._list_repo_tasks = lambda: [stale_task]
    scheduler._repair_task_fingerprint_from_task = lambda task: task.get("repair_fingerprint", "")
    scheduler._repair_task_age_seconds = lambda task: 999
    scheduler._fail_task_for_queue_hygiene = lambda task, reason: failed.append(
        {"task_id": task.get("task_id"), "reason": reason}
    )
    scheduler._cancel_ready_queue_task = lambda task_id: cancelled.append(task_id)
    scheduler._remove_repair_fingerprint_from_index = lambda value: removed.append(value)
    scheduler._load_repair_fingerprint_index = lambda: {}

    duplicate = scheduler._find_active_duplicate_repair_task(fingerprint)

    assert duplicate is None
    assert failed == [
        {
            "task_id": "repair-stale-1",
            "reason": (
                "expired stale queued autonomous repair duplicate; "
                "fingerprint=stale-repair-fingerprint; age_seconds=999"
            ),
        }
    ]
    assert cancelled == ["repair-stale-1"]
    assert removed == [fingerprint]


def test_v726_pending_repair_enqueue_lock_releases_on_failed_create_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = Scheduler.__new__(Scheduler)
    fingerprint = "repair-fingerprint-1"
    index = {
        fingerprint: {
            "task_id": "__pending_repair_enqueue__",
            "created_at": int(time.time()),
        }
    }
    saved: List[Dict[str, Any]] = []

    def failing_create_task(self: Any, **kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("create failed")

    monkeypatch.setattr(scheduler_module, "_ZERO_V726_ORIGINAL_CREATE_TASK", failing_create_task)

    scheduler._parse_goal_overrides = lambda goal: {"clean_goal": goal}
    scheduler._repair_task_fingerprint_from_goal = lambda goal: fingerprint
    scheduler._load_repair_fingerprint_index = lambda: index

    def save_index(data: Dict[str, Any]) -> None:
        index.clear()
        index.update(data)
        saved.append(copy.deepcopy(data))

    scheduler._save_repair_fingerprint_index = save_index
    scheduler._get_task_from_repo = lambda task_id: None

    with pytest.raises(RuntimeError, match="create failed"):
        scheduler.create_task(goal="repair workspace/shared/example.py")

    assert fingerprint not in index
    assert saved
    assert saved[-1] == {}


def test_v726_pending_repair_lock_lifecycle_releases_stale_pending_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = Scheduler.__new__(Scheduler)
    fingerprint = "stale-pending-fingerprint"
    index = {
        fingerprint: {
            "task_id": "__pending_repair_enqueue__",
            "created_at": int(time.time()) - 5,
        }
    }
    saved: List[Dict[str, Any]] = []

    monkeypatch.setattr(
        scheduler_module,
        "_ZERO_V726_ORIGINAL_FIND_ACTIVE_DUPLICATE_REPAIR_TASK",
        lambda self, value: {"task_id": "__pending_repair_enqueue__", "status": "queued"},
    )

    scheduler._load_repair_fingerprint_index = lambda: index

    def save_index(data: Dict[str, Any]) -> None:
        index.clear()
        index.update(data)
        saved.append(copy.deepcopy(data))

    scheduler._save_repair_fingerprint_index = save_index

    duplicate = scheduler._find_active_duplicate_repair_task(fingerprint)

    assert duplicate is None
    assert fingerprint not in index
    assert saved[-1] == {}


def test_replay_after_stale_pending_lock_release_can_create_valid_repair_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = Scheduler.__new__(Scheduler)
    fingerprint = "replay-stale-pending-fingerprint"
    index = {
        fingerprint: {
            "task_id": "__pending_repair_enqueue__",
            "created_at": int(time.time()) - 10,
        }
    }
    create_calls: List[Dict[str, Any]] = []
    saved: List[Dict[str, Any]] = []

    def create_after_cleanup(self: Any, **kwargs: Any) -> Dict[str, Any]:
        create_calls.append(copy.deepcopy(kwargs))
        assert fingerprint not in index
        return {"ok": True, "task_id": "repair-valid-1", "status": "queued"}

    monkeypatch.setattr(scheduler_module, "_ZERO_V726_ORIGINAL_CREATE_TASK", create_after_cleanup)

    scheduler._parse_goal_overrides = lambda goal: {"clean_goal": goal}
    scheduler._repair_task_fingerprint_from_goal = lambda goal: fingerprint
    scheduler._load_repair_fingerprint_index = lambda: index
    scheduler._get_task_from_repo = lambda task_id: None

    def save_index(data: Dict[str, Any]) -> None:
        index.clear()
        index.update(data)
        saved.append(copy.deepcopy(data))

    scheduler._save_repair_fingerprint_index = save_index

    result = scheduler.create_task(goal="repair workspace/shared/replay.py")

    assert result == {"ok": True, "task_id": "repair-valid-1", "status": "queued"}
    assert create_calls == [
        {
            "goal": "repair workspace/shared/replay.py",
            "priority": 0,
            "max_retries": 0,
            "retry_delay": 0,
            "timeout_ticks": 0,
            "depends_on": None,
        }
    ]
    assert saved[-1] == {}


class RecordingRunner:
    def __init__(self, result: Dict[str, Any]) -> None:
        self.result = result
        self.calls: List[Dict[str, Any]] = []

    def run_task_tick(self, *, task: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
        self.calls.append({"task": task, "current_tick": current_tick})
        return self.result


def test_v733_code_chain_simple_tick_syncs_runner_result_and_requeue() -> None:
    scheduler = Scheduler.__new__(Scheduler)
    task = {
        "task_id": "task-code-chain-1",
        "current_step_index": 0,
        "steps": [{"type": "code_chain_repair"}],
    }
    runner_result = {"ok": True, "status": "queued", "task": copy.deepcopy(task)}
    runner = RecordingRunner(runner_result)
    sync_calls: List[Dict[str, Any]] = []

    scheduler.task_runner = runner
    scheduler._sync_runner_result_and_requeue_if_ready = lambda **kwargs: sync_calls.append(kwargs)

    result = scheduler._run_simple_task_tick(task=task, current_tick=42)

    assert result is runner_result
    assert runner.calls == [{"task": task, "current_tick": 42}]
    assert sync_calls == [{"task": task, "runner_result": runner_result}]


def test_retry_enqueue_path_does_not_enqueue_failed_terminal_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = Scheduler.__new__(Scheduler)
    original_sync_calls: List[Dict[str, Any]] = []
    enqueued: List[Dict[str, Any]] = []
    task = {"task_id": "task-failed-1", "status": "retrying"}
    failed_task = {"task_id": "task-failed-1", "status": "failed"}

    monkeypatch.setattr(
        scheduler_module,
        "_ZERO_V734_ORIGINAL_SYNC_RUNNER_RESULT_AND_REQUEUE",
        lambda self, **kwargs: original_sync_calls.append(copy.deepcopy(kwargs)),
    )

    scheduler._extract_task_id = lambda value: value.get("task_id", "")
    scheduler._get_task_from_repo = lambda task_id: failed_task
    scheduler._enqueue_repo_task_if_ready = lambda task, overwrite=False: enqueued.append(
        {"task": copy.deepcopy(task), "overwrite": overwrite}
    ) or True

    scheduler._sync_runner_result_and_requeue_if_ready(
        task=task,
        runner_result={"ok": False, "status": "failed"},
    )

    assert original_sync_calls == [
        {"task": task, "runner_result": {"ok": False, "status": "failed"}}
    ]
    assert enqueued == []


def test_stale_repair_metadata_does_not_requeue_finished_terminal_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = Scheduler.__new__(Scheduler)
    original_sync_calls: List[Dict[str, Any]] = []
    enqueued: List[Dict[str, Any]] = []
    task = {
        "task_id": "task-finished-stale-retry-1",
        "status": "retrying",
        "repair_context": {"last_phase": "repair_steps_injected"},
    }
    finished_task = {
        "task_id": "task-finished-stale-retry-1",
        "status": "finished",
        "repair_context": {"last_phase": "repair_steps_injected"},
    }

    monkeypatch.setattr(
        scheduler_module,
        "_ZERO_V734_ORIGINAL_SYNC_RUNNER_RESULT_AND_REQUEUE",
        lambda self, **kwargs: original_sync_calls.append(copy.deepcopy(kwargs)),
    )

    scheduler._extract_task_id = lambda value: value.get("task_id", "")
    scheduler._get_task_from_repo = lambda task_id: finished_task
    scheduler._enqueue_repo_task_if_ready = lambda task, overwrite=False: enqueued.append(
        {"task": copy.deepcopy(task), "overwrite": overwrite}
    ) or True

    scheduler._sync_runner_result_and_requeue_if_ready(
        task=task,
        runner_result={"ok": True, "status": "finished"},
    )

    assert original_sync_calls == [
        {"task": task, "runner_result": {"ok": True, "status": "finished"}}
    ]
    assert enqueued == []


def test_v734_retrying_repair_bridge_does_not_duplicate_already_injected_steps() -> None:
    scheduler = Scheduler.__new__(Scheduler)
    original_steps = [
        {"id": "done", "type": "run_python"},
        {"id": "auto_repair_compile_syntax_write", "type": "write_file"},
        {"id": "auto_repair_compile_syntax_verify", "type": "run_python"},
    ]
    task = {
        "task_id": "task-retry-1",
        "status": "retrying",
        "steps": copy.deepcopy(original_steps),
        "current_step_index": 1,
        "auto_repair": True,
        "repair_context": {"repair_steps_injected": True},
    }
    persisted: List[Dict[str, Any]] = []
    enqueued: List[Dict[str, Any]] = []

    scheduler._hydrate_task_from_workspace = lambda value: copy.deepcopy(value)
    scheduler._extract_task_id = lambda value: value.get("task_id", "")
    scheduler._persist_task_payload = lambda **kwargs: persisted.append(copy.deepcopy(kwargs))
    scheduler._enqueue_repo_task_if_ready = lambda task, overwrite=False: enqueued.append(
        {"task": copy.deepcopy(task), "overwrite": overwrite}
    ) or True
    scheduler._compact_runner_result = lambda result: result

    result = scheduler.run_one_step(task=task, current_tick=7)

    assert result["ok"] is True
    assert result["action"] == "repair_steps_already_injected"
    assert result["status"] == "queued"
    assert result["task"]["steps"] == original_steps
    assert persisted[0]["task"]["steps"] == original_steps
    assert enqueued == [{"task": result["task"], "overwrite": True}]


def test_retry_repair_bridge_is_idempotent_across_repeated_replay_attempts() -> None:
    scheduler = Scheduler.__new__(Scheduler)
    original_steps = [
        {"id": "auto_repair_compile_syntax_write", "type": "write_file"},
        {"id": "auto_repair_compile_syntax_verify", "type": "run_python"},
    ]
    task = {
        "task_id": "task-replay-idempotent-1",
        "status": "retrying",
        "steps": copy.deepcopy(original_steps),
        "current_step_index": 0,
        "auto_repair": True,
        "repair_context": {"repair_steps_injected": True},
    }
    persisted: List[Dict[str, Any]] = []
    enqueued: List[Dict[str, Any]] = []

    scheduler._hydrate_task_from_workspace = lambda value: copy.deepcopy(value)
    scheduler._extract_task_id = lambda value: value.get("task_id", "")
    scheduler._persist_task_payload = lambda **kwargs: persisted.append(copy.deepcopy(kwargs))
    scheduler._enqueue_repo_task_if_ready = lambda task, overwrite=False: enqueued.append(
        {"task": copy.deepcopy(task), "overwrite": overwrite}
    ) or True
    scheduler._compact_runner_result = lambda result: result

    first = scheduler.run_one_step(task=task, current_tick=1)
    replay_task = copy.deepcopy(first["task"])
    replay_task["status"] = "retrying"
    second = scheduler.run_one_step(task=replay_task, current_tick=2)

    assert first["action"] == "repair_steps_already_injected"
    assert second["action"] == "repair_steps_already_injected"
    assert first["task"]["steps"] == original_steps
    assert second["task"]["steps"] == original_steps
    assert [call["task"]["steps"] for call in persisted] == [original_steps, original_steps]
    assert [call["overwrite"] for call in enqueued] == [True, True]


def test_repeated_retrying_state_does_not_duplicate_injected_repair_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = Scheduler.__new__(Scheduler)
    repair_steps = [
        {"id": "auto_repair_compile_syntax_write", "type": "write_file"},
        {"id": "auto_repair_compile_syntax_verify", "type": "run_python"},
    ]
    task = {
        "task_id": "task-repeated-retrying-1",
        "status": "retrying",
        "steps": [{"id": "verify_failed", "type": "run_python"}],
        "current_step_index": 0,
        "auto_repair": True,
        "last_step_result": {"step": {"id": "verify_failed", "type": "run_python"}},
        "repair_context": {},
    }
    persisted: List[Dict[str, Any]] = []
    enqueued: List[Dict[str, Any]] = []

    monkeypatch.setattr(
        scheduler_module,
        "_zero_v734_build_retry_repair_steps",
        lambda task, failed_step: (
            True,
            copy.deepcopy(repair_steps),
            {"reason": "test repair", "path": "demo.py", "relative_path": "demo.py", "cwd": "."},
        ),
    )

    scheduler._hydrate_task_from_workspace = lambda value: copy.deepcopy(value)
    scheduler._extract_task_id = lambda value: value.get("task_id", "")
    scheduler._persist_task_payload = lambda **kwargs: persisted.append(copy.deepcopy(kwargs))
    scheduler._enqueue_repo_task_if_ready = lambda task, overwrite=False: enqueued.append(
        {"task": copy.deepcopy(task), "overwrite": overwrite}
    ) or True
    scheduler._compact_runner_result = lambda result: result

    first = scheduler.run_one_step(task=task, current_tick=1)
    replay_task = copy.deepcopy(first["task"])
    replay_task["status"] = "retrying"
    second = scheduler.run_one_step(task=replay_task, current_tick=2)

    assert first["action"] == "repair_steps_injected"
    assert second["action"] == "repair_steps_already_injected"
    assert [step["id"] for step in first["task"]["steps"]] == [
        "auto_repair_compile_syntax_write",
        "auto_repair_compile_syntax_verify",
    ]
    assert second["task"]["steps"] == first["task"]["steps"]
    assert len([step for step in second["task"]["steps"] if step["id"] == "auto_repair_compile_syntax_write"]) == 1
    assert len(enqueued) == 2


def test_failed_repair_injection_preserves_failure_state_and_does_not_mark_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = Scheduler.__new__(Scheduler)
    task = {
        "task_id": "task-repair-fails-1",
        "status": "retrying",
        "steps": [{"id": "verify_failed", "type": "run_python"}],
        "current_step_index": 0,
        "auto_repair": True,
        "last_step_result": {"step": {"id": "verify_failed", "type": "run_python"}},
        "repair_context": {},
    }
    persisted: List[Dict[str, Any]] = []
    enqueued: List[Dict[str, Any]] = []

    monkeypatch.setattr(
        scheduler_module,
        "_zero_v734_build_retry_repair_steps",
        lambda task, failed_step: (False, [], {"reason": "unsupported replay repair"}),
    )

    scheduler._hydrate_task_from_workspace = lambda value: copy.deepcopy(value)
    scheduler._extract_task_id = lambda value: value.get("task_id", "")
    scheduler._persist_task_payload = lambda **kwargs: persisted.append(copy.deepcopy(kwargs))
    scheduler._enqueue_repo_task_if_ready = lambda task, overwrite=False: enqueued.append(
        {"task": copy.deepcopy(task), "overwrite": overwrite}
    ) or True
    scheduler._compact_runner_result = lambda result: result

    result = scheduler.run_one_step(task=task, current_tick=3)

    assert result["ok"] is False
    assert result["action"] == "retrying_repair_bridge_failed"
    assert result["status"] == "failed"
    assert result["task"]["status"] == "failed"
    assert result["task"]["last_error"] == "retrying repair bridge failed: unsupported replay repair"
    assert persisted == [{"task_id": "task-repair-fails-1", "task": result["task"]}]
    assert enqueued == []


def test_partial_replay_does_not_duplicate_completed_repair_steps() -> None:
    scheduler = Scheduler.__new__(Scheduler)
    original_steps = [
        {"id": "completed_prepare", "type": "run_python"},
        {"id": "auto_repair_compile_syntax_write", "type": "write_file"},
        {"id": "auto_repair_compile_syntax_verify", "type": "run_python"},
        {"id": "post_repair_check", "type": "run_python"},
    ]
    task = {
        "task_id": "task-partial-replay-1",
        "status": "retrying",
        "steps": copy.deepcopy(original_steps),
        "current_step_index": 2,
        "auto_repair": True,
        "repair_context": {
            "repair_steps_injected": True,
            "flow": [{"phase": "repair_steps_injected", "inserted_steps": [
                "auto_repair_compile_syntax_write",
                "auto_repair_compile_syntax_verify",
            ]}],
        },
    }
    persisted: List[Dict[str, Any]] = []
    enqueued: List[Dict[str, Any]] = []

    scheduler._hydrate_task_from_workspace = lambda value: copy.deepcopy(value)
    scheduler._extract_task_id = lambda value: value.get("task_id", "")
    scheduler._persist_task_payload = lambda **kwargs: persisted.append(copy.deepcopy(kwargs))
    scheduler._enqueue_repo_task_if_ready = lambda task, overwrite=False: enqueued.append(
        {"task": copy.deepcopy(task), "overwrite": overwrite}
    ) or True
    scheduler._compact_runner_result = lambda result: result

    result = scheduler.run_one_step(task=task, current_tick=13)

    assert result["ok"] is True
    assert result["action"] == "repair_steps_already_injected"
    assert result["task"]["steps"] == original_steps
    assert [step["id"] for step in result["task"]["steps"]].count("auto_repair_compile_syntax_write") == 1
    assert [step["id"] for step in result["task"]["steps"]].count("auto_repair_compile_syntax_verify") == 1
    assert persisted[0]["task"]["steps"] == original_steps
    assert enqueued == [{"task": result["task"], "overwrite": True}]


def test_terminal_finished_task_replay_cannot_move_back_to_queued_or_retrying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = Scheduler.__new__(Scheduler)
    task = {
        "task_id": "task-terminal-replay-1",
        "status": "finished",
        "steps": [{"id": "done", "type": "run_python"}],
        "repair_context": {"repair_steps_injected": True},
    }
    original_calls: List[Dict[str, Any]] = []
    persisted: List[Dict[str, Any]] = []
    enqueued: List[Dict[str, Any]] = []

    monkeypatch.setattr(
        scheduler_module,
        "_ZERO_V734_ORIGINAL_RUN_ONE_STEP",
        lambda self, **kwargs: {"ok": True, "status": "finished", "task": copy.deepcopy(kwargs["task"])},
    )

    monkeypatch.setattr(
        scheduler_module,
        "_ZERO_V352_ORIGINAL_SCHEDULER_RUN_ONE_STEP",
        lambda self, **kwargs: original_calls.append(copy.deepcopy(kwargs))
        or {"ok": True, "status": "finished", "task": copy.deepcopy(kwargs["task"])},
    )

    scheduler._hydrate_task_from_workspace = lambda value: copy.deepcopy(value)
    scheduler._extract_task_id = lambda value: value.get("task_id", "")
    scheduler._persist_task_payload = lambda **kwargs: persisted.append(copy.deepcopy(kwargs))
    scheduler._enqueue_repo_task_if_ready = lambda task, overwrite=False: enqueued.append(
        {"task": copy.deepcopy(task), "overwrite": overwrite}
    ) or True
    scheduler._compact_runner_result = lambda result: result
    scheduler._attach_repair_chain_orchestration_summary_to_task = lambda task: copy.deepcopy(task)

    result = scheduler.run_one_step(task=task, current_tick=17)

    assert result["status"] == "finished"
    assert result["task"]["status"] == "finished"
    assert original_calls == [{"task": task, "current_tick": 17}]
    assert persisted == []
    assert enqueued == []


def test_repair_injection_is_idempotent_when_task_marks_repair_steps_already_existing() -> None:
    scheduler = Scheduler.__new__(Scheduler)
    original_steps = [
        {"id": "verify_before", "type": "run_python"},
        {"id": "auto_repair_compile_syntax_write", "type": "write_file"},
        {"id": "auto_repair_compile_syntax_verify", "type": "run_python"},
    ]
    task = {
        "task_id": "task-repair-existing-1",
        "status": "retrying",
        "steps": copy.deepcopy(original_steps),
        "current_step_index": 1,
        "auto_repair": True,
        "repair_steps_injected": True,
        "repair_context": {},
    }
    persisted: List[Dict[str, Any]] = []
    enqueued: List[Dict[str, Any]] = []

    scheduler._hydrate_task_from_workspace = lambda value: copy.deepcopy(value)
    scheduler._extract_task_id = lambda value: value.get("task_id", "")
    scheduler._persist_task_payload = lambda **kwargs: persisted.append(copy.deepcopy(kwargs))
    scheduler._enqueue_repo_task_if_ready = lambda task, overwrite=False: enqueued.append(
        {"task": copy.deepcopy(task), "overwrite": overwrite}
    ) or True
    scheduler._compact_runner_result = lambda result: result

    result = scheduler.run_one_step(task=task, current_tick=11)

    assert result["ok"] is True
    assert result["action"] == "repair_steps_already_injected"
    assert result["task"]["steps"] == original_steps
    assert persisted[0]["task"]["steps"] == original_steps
    assert enqueued == [{"task": result["task"], "overwrite": True}]
