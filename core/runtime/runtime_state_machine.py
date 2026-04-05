from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class TransitionResult:
    ok: bool
    old_status: str
    new_status: str
    reason: str
    message: str


class RuntimeStateMachine:
    """
    ZERO Runtime State Machine

    這一層是給 scheduler / runner / runtime 用的短期執行狀態機，
    不取代 task_state_machine.py 那種 lifecycle / timeline 狀態紀錄。

    目標：
    1. 集中定義 runtime status 與合法 transition
    2. 提供 can_transition / transition / force_set
    3. 可直接作用在 runtime_state dict
    4. 自動維護 runtime_status_history 與各種 timestamp
    """

    STATUS_QUEUED = "queued"
    STATUS_PLANNING = "planning"
    STATUS_READY = "ready"
    STATUS_RUNNING = "running"
    STATUS_RETRYING = "retrying"
    STATUS_WAITING = "waiting"
    STATUS_BLOCKED = "blocked"
    STATUS_REPLANNING = "replanning"
    STATUS_PAUSED = "paused"
    STATUS_FINISHED = "finished"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_TIMEOUT = "timeout"

    TERMINAL_STATUSES: Set[str] = {
        STATUS_FINISHED,
        STATUS_FAILED,
        STATUS_CANCELLED,
        STATUS_TIMEOUT,
    }

    ACTIVE_STATUSES: Set[str] = {
        STATUS_QUEUED,
        STATUS_PLANNING,
        STATUS_READY,
        STATUS_RUNNING,
        STATUS_RETRYING,
        STATUS_WAITING,
        STATUS_BLOCKED,
        STATUS_REPLANNING,
        STATUS_PAUSED,
    }

    ALL_STATUSES: Set[str] = TERMINAL_STATUSES | ACTIVE_STATUSES

    ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
        STATUS_QUEUED: {
            STATUS_PLANNING,
            STATUS_READY,
            STATUS_RUNNING,
            STATUS_PAUSED,
            STATUS_CANCELLED,
            STATUS_FAILED,
        },
        STATUS_PLANNING: {
            STATUS_READY,
            STATUS_FAILED,
            STATUS_CANCELLED,
            STATUS_TIMEOUT,
        },
        STATUS_READY: {
            STATUS_RUNNING,
            STATUS_PAUSED,
            STATUS_BLOCKED,
            STATUS_WAITING,
            STATUS_CANCELLED,
            STATUS_FAILED,
            STATUS_TIMEOUT,
        },
        STATUS_RUNNING: {
            STATUS_READY,
            STATUS_RETRYING,
            STATUS_WAITING,
            STATUS_BLOCKED,
            STATUS_REPLANNING,
            STATUS_PAUSED,
            STATUS_FINISHED,
            STATUS_FAILED,
            STATUS_CANCELLED,
            STATUS_TIMEOUT,
        },
        STATUS_RETRYING: {
            STATUS_RUNNING,
            STATUS_WAITING,
            STATUS_BLOCKED,
            STATUS_REPLANNING,
            STATUS_FAILED,
            STATUS_CANCELLED,
            STATUS_TIMEOUT,
            STATUS_PAUSED,
        },
        STATUS_WAITING: {
            STATUS_READY,
            STATUS_RUNNING,
            STATUS_BLOCKED,
            STATUS_REPLANNING,
            STATUS_FAILED,
            STATUS_CANCELLED,
            STATUS_TIMEOUT,
            STATUS_PAUSED,
        },
        STATUS_BLOCKED: {
            STATUS_READY,
            STATUS_WAITING,
            STATUS_REPLANNING,
            STATUS_FAILED,
            STATUS_CANCELLED,
            STATUS_TIMEOUT,
            STATUS_PAUSED,
        },
        STATUS_REPLANNING: {
            STATUS_READY,
            STATUS_RUNNING,
            STATUS_FAILED,
            STATUS_CANCELLED,
            STATUS_TIMEOUT,
            STATUS_PAUSED,
        },
        STATUS_PAUSED: {
            STATUS_QUEUED,
            STATUS_READY,
            STATUS_RUNNING,
            STATUS_CANCELLED,
            STATUS_FAILED,
        },
        STATUS_FINISHED: set(),
        STATUS_FAILED: set(),
        STATUS_CANCELLED: set(),
        STATUS_TIMEOUT: set(),
    }

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug

    # ============================================================
    # basic helpers
    # ============================================================

    def normalize_status(self, status: Any) -> str:
        text = str(status or "").strip().lower()
        if not text:
            return self.STATUS_QUEUED
        if text not in self.ALL_STATUSES:
            return self.STATUS_QUEUED
        return text

    def is_terminal(self, status: Any) -> bool:
        return self.normalize_status(status) in self.TERMINAL_STATUSES

    def is_active(self, status: Any) -> bool:
        return self.normalize_status(status) in self.ACTIVE_STATUSES

    def is_blocked_like(self, status: Any) -> bool:
        return self.normalize_status(status) in {
            self.STATUS_BLOCKED,
            self.STATUS_WAITING,
            self.STATUS_RETRYING,
        }

    def is_runnable(self, status: Any) -> bool:
        return self.normalize_status(status) in {
            self.STATUS_READY,
            self.STATUS_RUNNING,
            self.STATUS_RETRYING,
        }

    # ============================================================
    # transition checks
    # ============================================================

    def can_transition(self, old_status: Any, new_status: Any) -> bool:
        old_s = self.normalize_status(old_status)
        new_s = self.normalize_status(new_status)

        if old_s == new_s:
            return True

        allowed = self.ALLOWED_TRANSITIONS.get(old_s, set())
        return new_s in allowed

    def explain_transition(self, old_status: Any, new_status: Any) -> str:
        old_s = self.normalize_status(old_status)
        new_s = self.normalize_status(new_status)

        if old_s == new_s:
            return f"status unchanged: {old_s}"

        if self.can_transition(old_s, new_s):
            return f"allowed transition: {old_s} -> {new_s}"

        return f"invalid transition: {old_s} -> {new_s}"

    # ============================================================
    # runtime state normalization
    # ============================================================

    def ensure_runtime_status_fields(self, runtime_state: Dict[str, Any]) -> Dict[str, Any]:
        state = copy.deepcopy(runtime_state or {})

        state["status"] = self.normalize_status(state.get("status"))

        history = state.get("runtime_status_history")
        if not isinstance(history, list):
            history = []

        if not history:
            history.append(
                self._build_history_record(
                    old_status="",
                    new_status=state["status"],
                    reason="init",
                    message="initialize runtime status history",
                )
            )

        state["runtime_status_history"] = history

        if "runtime_created_at" not in state or not state.get("runtime_created_at"):
            state["runtime_created_at"] = self._now_iso()

        return state

    # ============================================================
    # transition api
    # ============================================================

    def transition(
        self,
        runtime_state: Dict[str, Any],
        new_status: Any,
        *,
        reason: str = "",
        message: str = "",
        allow_noop: bool = True,
        extra_updates: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        state = self.ensure_runtime_status_fields(runtime_state)

        old_status = self.normalize_status(state.get("status"))
        target_status = self.normalize_status(new_status)

        if old_status == target_status and allow_noop:
            updated = copy.deepcopy(state)
            if extra_updates:
                updated.update(copy.deepcopy(extra_updates))
            result = TransitionResult(
                ok=True,
                old_status=old_status,
                new_status=target_status,
                reason=reason or "noop",
                message=message or f"status unchanged: {old_status}",
            )
            return updated, result

        if not self.can_transition(old_status, target_status):
            result = TransitionResult(
                ok=False,
                old_status=old_status,
                new_status=target_status,
                reason=reason or "invalid_transition",
                message=message or f"invalid transition: {old_status} -> {target_status}",
            )
            return copy.deepcopy(state), result

        updated = copy.deepcopy(state)
        updated["status"] = target_status

        if extra_updates:
            updated.update(copy.deepcopy(extra_updates))

        updated = self._apply_status_timestamps(
            runtime_state=updated,
            old_status=old_status,
            new_status=target_status,
        )

        updated = self._append_history(
            runtime_state=updated,
            old_status=old_status,
            new_status=target_status,
            reason=reason or "",
            message=message or f"{old_status} -> {target_status}",
        )

        result = TransitionResult(
            ok=True,
            old_status=old_status,
            new_status=target_status,
            reason=reason or "",
            message=message or f"{old_status} -> {target_status}",
        )
        return updated, result

    def force_set(
        self,
        runtime_state: Dict[str, Any],
        new_status: Any,
        *,
        reason: str = "force_set",
        message: str = "",
        extra_updates: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        state = self.ensure_runtime_status_fields(runtime_state)

        old_status = self.normalize_status(state.get("status"))
        target_status = self.normalize_status(new_status)

        updated = copy.deepcopy(state)
        updated["status"] = target_status

        if extra_updates:
            updated.update(copy.deepcopy(extra_updates))

        updated = self._apply_status_timestamps(
            runtime_state=updated,
            old_status=old_status,
            new_status=target_status,
        )

        updated = self._append_history(
            runtime_state=updated,
            old_status=old_status,
            new_status=target_status,
            reason=reason,
            message=message or f"force set: {old_status} -> {target_status}",
        )

        result = TransitionResult(
            ok=True,
            old_status=old_status,
            new_status=target_status,
            reason=reason,
            message=message or f"force set: {old_status} -> {target_status}",
        )
        return updated, result

    # ============================================================
    # convenience wrappers
    # ============================================================

    def mark_planning(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_PLANNING,
            reason=reason or "planning",
            message="runtime entering planning stage",
        )

    def mark_ready(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_READY,
            reason=reason or "ready",
            message="runtime ready to run",
        )

    def mark_running(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_RUNNING,
            reason=reason or "running",
            message="runtime running",
            extra_updates={
                "last_started_at": self._now_iso(),
            },
        )

    def mark_retrying(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
        next_retry_tick: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        extra: Dict[str, Any] = {}
        if next_retry_tick is not None:
            extra["next_retry_tick"] = int(next_retry_tick)

        return self.transition(
            runtime_state,
            self.STATUS_RETRYING,
            reason=reason or "retrying",
            message="runtime waiting for retry",
            extra_updates=extra,
        )

    def mark_waiting(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_WAITING,
            reason=reason or "waiting",
            message="runtime waiting",
        )

    def mark_blocked(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_BLOCKED,
            reason=reason or "blocked",
            message="runtime blocked",
        )

    def mark_replanning(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_REPLANNING,
            reason=reason or "replanning",
            message="runtime replanning",
        )

    def mark_paused(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_PAUSED,
            reason=reason or "paused",
            message="runtime paused",
        )

    def mark_finished(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_FINISHED,
            reason=reason or "finished",
            message="runtime finished",
            extra_updates={
                "last_finished_at": self._now_iso(),
            },
        )

    def mark_failed(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_FAILED,
            reason=reason or "failed",
            message="runtime failed",
            extra_updates={
                "last_failed_at": self._now_iso(),
            },
        )

    def mark_cancelled(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_CANCELLED,
            reason=reason or "cancelled",
            message="runtime cancelled",
            extra_updates={
                "last_cancelled_at": self._now_iso(),
            },
        )

    def mark_timeout(
        self,
        runtime_state: Dict[str, Any],
        reason: str = "",
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        return self.transition(
            runtime_state,
            self.STATUS_TIMEOUT,
            reason=reason or "timeout",
            message="runtime timeout",
            extra_updates={
                "last_timeout_at": self._now_iso(),
            },
        )

    # ============================================================
    # convenience policy transitions
    # ============================================================

    def from_failure_policy(
        self,
        runtime_state: Dict[str, Any],
        *,
        action: str,
        reason: str = "",
        next_retry_tick: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], TransitionResult]:
        clean_action = str(action or "").strip().lower()

        if clean_action == "retry":
            return self.mark_retrying(
                runtime_state,
                reason=reason or "failure_policy_retry",
                next_retry_tick=next_retry_tick,
            )

        if clean_action == "replan":
            return self.mark_replanning(
                runtime_state,
                reason=reason or "failure_policy_replan",
            )

        if clean_action == "wait":
            return self.mark_waiting(
                runtime_state,
                reason=reason or "failure_policy_wait",
            )

        if clean_action == "fail":
            return self.mark_failed(
                runtime_state,
                reason=reason or "failure_policy_fail",
            )

        return self.force_set(
            runtime_state,
            runtime_state.get("status", self.STATUS_QUEUED),
            reason="unknown_failure_policy_action",
            message=f"unknown failure policy action: {clean_action}",
        )

    # ============================================================
    # summary / graph helpers
    # ============================================================

    def summarize(self, runtime_state: Dict[str, Any]) -> Dict[str, Any]:
        state = self.ensure_runtime_status_fields(runtime_state)
        status = self.normalize_status(state.get("status"))

        return {
            "task_name": self._task_name(state),
            "status": status,
            "is_terminal": self.is_terminal(status),
            "is_active": self.is_active(status),
            "is_runnable": self.is_runnable(status),
            "is_blocked_like": self.is_blocked_like(status),
            "history_count": len(state.get("runtime_status_history", [])),
        }

    def allowed_next_statuses(self, status: Any) -> List[str]:
        current = self.normalize_status(status)
        return sorted(self.ALLOWED_TRANSITIONS.get(current, set()))

    # ============================================================
    # internals
    # ============================================================

    def _append_history(
        self,
        runtime_state: Dict[str, Any],
        old_status: str,
        new_status: str,
        reason: str,
        message: str,
    ) -> Dict[str, Any]:
        updated = copy.deepcopy(runtime_state)
        history = updated.get("runtime_status_history")
        if not isinstance(history, list):
            history = []

        history.append(
            self._build_history_record(
                old_status=old_status,
                new_status=new_status,
                reason=reason,
                message=message,
            )
        )
        updated["runtime_status_history"] = history
        return updated

    def _build_history_record(
        self,
        *,
        old_status: str,
        new_status: str,
        reason: str,
        message: str,
    ) -> Dict[str, Any]:
        return {
            "ts": self._now_iso(),
            "old_status": old_status,
            "new_status": new_status,
            "reason": reason,
            "message": message,
        }

    def _apply_status_timestamps(
        self,
        runtime_state: Dict[str, Any],
        old_status: str,
        new_status: str,
    ) -> Dict[str, Any]:
        updated = copy.deepcopy(runtime_state)
        now = self._now_iso()

        if new_status == self.STATUS_PLANNING:
            updated["planning_at"] = now
        elif new_status == self.STATUS_READY:
            updated["ready_at"] = now
        elif new_status == self.STATUS_RUNNING:
            updated["running_at"] = now
        elif new_status == self.STATUS_RETRYING:
            updated["retrying_at"] = now
        elif new_status == self.STATUS_WAITING:
            updated["waiting_at"] = now
        elif new_status == self.STATUS_BLOCKED:
            updated["blocked_at"] = now
        elif new_status == self.STATUS_REPLANNING:
            updated["replanning_at"] = now
        elif new_status == self.STATUS_PAUSED:
            updated["paused_at"] = now
        elif new_status == self.STATUS_FINISHED:
            updated["finished_at"] = now
        elif new_status == self.STATUS_FAILED:
            updated["failed_at"] = now
        elif new_status == self.STATUS_CANCELLED:
            updated["cancelled_at"] = now
        elif new_status == self.STATUS_TIMEOUT:
            updated["timeout_at"] = now

        updated["last_status_change_at"] = now
        return updated

    def _task_name(self, runtime_state: Dict[str, Any]) -> str:
        for key in ("task_name", "task_id", "id", "name", "title"):
            value = runtime_state.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "unknown_task"

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")