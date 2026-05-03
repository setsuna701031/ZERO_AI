from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.agent.loop_decision_guard import guard_loop_decision, infer_decision_mode
from core.runtime.blockers import active_blockers, first_active_blocker, normalize_blockers


TERMINAL_STATUSES = {
    "finished",
    "completed",
    "done",
    "success",
    "failed",
    "error",
    "blocked",
    "cancelled",
    "canceled",
    "timeout",
}

SUCCESS_STATUSES = {"finished", "completed", "done", "success"}
FAILURE_STATUSES = {"failed", "error", "timeout"}
BLOCKED_STATUSES = {"blocked", "cancelled", "canceled"}
WAITING_STATUSES = {"waiting", "waiting_blocker", "waiting_review", "pending_review"}


@dataclass(frozen=True)
class LoopObservation:
    ok: bool
    status: str
    action: str
    error: str
    final_answer: str
    current_step_index: int
    steps_total: int
    raw: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "action": self.action,
            "error": self.error,
            "final_answer": self.final_answer,
            "current_step_index": self.current_step_index,
            "steps_total": self.steps_total,
            "raw": dict(self.raw),
        }


@dataclass(frozen=True)
class LoopDecision:
    decision: str
    next_action: str
    terminal: bool
    should_continue: bool
    should_replan: bool
    should_fail: bool
    reason: str
    observation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "next_action": self.next_action,
            "terminal": self.terminal,
            "should_continue": self.should_continue,
            "should_replan": self.should_replan,
            "should_fail": self.should_fail,
            "reason": self.reason,
            "observation": dict(self.observation),
        }


def normalize_status(status: Any) -> str:
    return str(status or "").strip().lower()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def first_nonempty_str(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def bool_from_any(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "ok", "pass", "passed"}:
        return True
    if text in {"0", "false", "no", "n", "fail", "failed"}:
        return False
    return default


def _extract_runtime_state(result: Dict[str, Any], task_dict: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = result.get("runtime_state") if isinstance(result, dict) else None
    if isinstance(runtime_state, dict):
        return runtime_state

    runtime_state = task_dict.get("runtime_state") if isinstance(task_dict, dict) else None
    if isinstance(runtime_state, dict):
        return runtime_state

    return {}


def _collect_blockers_from_sources(*sources: Dict[str, Any]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for source in sources:
        if not isinstance(source, dict):
            continue

        for item in normalize_blockers(source.get("blockers")):
            key = (str(item.get("type") or ""), str(item.get("id") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)

    return merged


def _legacy_review_blocker_from_sources(*sources: Dict[str, Any]) -> dict[str, Any] | None:
    def first_value(key: str) -> Any:
        for source in sources:
            if isinstance(source, dict) and source.get(key) not in (None, ""):
                return source.get(key)
        return None

    requires_review = bool_from_any(first_value("requires_review"), False)
    review_status = normalize_status(first_nonempty_str(first_value("review_status")))
    review_id = first_nonempty_str(first_value("review_id"))
    action = normalize_status(first_nonempty_str(first_value("agent_action"), first_value("action")))

    if not (requires_review or review_status in {"pending", "pending_review", "waiting_review"} or action in {"await_review_decision", "wait_for_review"}):
        return None

    payload = first_value("review_payload")
    if not isinstance(payload, dict):
        payload = {}

    return {
        "type": "review",
        "id": review_id or "review_pending",
        "status": review_status or "pending",
        "reason": "pending review",
        "payload": payload,
    }


def _blocker_payload_from_sources(
    *,
    local: Dict[str, Any],
    result: Dict[str, Any],
    runtime_state: Dict[str, Any],
    task_dict: Dict[str, Any],
) -> Dict[str, Any]:
    blockers = _collect_blockers_from_sources(local, result, runtime_state, task_dict)
    if not blockers:
        legacy_review = _legacy_review_blocker_from_sources(local, result, runtime_state, task_dict)
        if legacy_review:
            blockers = normalize_blockers([legacy_review])

    active = active_blockers(blockers)
    return {
        "blockers": blockers,
        "active_blockers": active,
        "active_blocker_count": len(active),
        "first_active_blocker": active[0] if active else None,
    }


def _is_waiting_for_blocker(observation: LoopObservation) -> bool:
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    blocker_gate = raw.get("blocker_gate") if isinstance(raw.get("blocker_gate"), dict) else {}
    if active_blockers(blocker_gate.get("blockers", [])):
        return True

    status = normalize_status(observation.status)
    if status in WAITING_STATUSES:
        return True

    if normalize_status(observation.action) in {"wait_for_external_event", "wait_for_blocker", "wait_for_review", "await_review_decision"}:
        return True

    return False


def observe_from_local_observation(
    local_observation: Any,
    runner_result: Any = None,
    task: Optional[Dict[str, Any]] = None,
) -> LoopObservation:
    local = local_observation if isinstance(local_observation, dict) else {}
    result = runner_result if isinstance(runner_result, dict) else {}
    task_dict = task if isinstance(task, dict) else {}
    runtime_state = _extract_runtime_state(result, task_dict)

    status = normalize_status(
        first_nonempty_str(
            local.get("status"),
            result.get("status"),
            runtime_state.get("status"),
            task_dict.get("status"),
            "unknown",
        )
    )
    action = normalize_status(first_nonempty_str(local.get("action"), result.get("action"), runtime_state.get("next_action"), task_dict.get("next_action")))
    error_value = first_nonempty_str(
        local.get("error"),
        result.get("error"),
        runtime_state.get("last_error"),
        runtime_state.get("failure_message"),
        task_dict.get("last_error"),
        task_dict.get("failure_message"),
    )
    final_answer = first_nonempty_str(
        result.get("final_answer"),
        runtime_state.get("final_answer"),
        task_dict.get("final_answer"),
    )
    current_step_index = safe_int(
        result.get(
            "current_step_index",
            runtime_state.get("current_step_index", task_dict.get("current_step_index", 0)),
        ),
        0,
    )
    steps_total = safe_int(
        result.get("steps_total", runtime_state.get("steps_total", task_dict.get("steps_total", 0))),
        0,
    )

    raw: Dict[str, Any] = dict(result)
    raw["local_observation"] = dict(local)
    raw["blocker_gate"] = _blocker_payload_from_sources(
        local=local,
        result=result,
        runtime_state=runtime_state,
        task_dict=task_dict,
    )

    return LoopObservation(
        ok=bool_from_any(local.get("ok"), bool(result.get("ok", status not in FAILURE_STATUSES))),
        status=status,
        action=action,
        error=error_value,
        final_answer=final_answer,
        current_step_index=current_step_index,
        steps_total=steps_total,
        raw=raw,
    )


def observe_runner_result(runner_result: Any, task: Optional[Dict[str, Any]] = None) -> LoopObservation:
    result = runner_result if isinstance(runner_result, dict) else {}
    task_dict = task if isinstance(task, dict) else {}
    runtime_state = _extract_runtime_state(result, task_dict)

    status = normalize_status(
        first_nonempty_str(
            result.get("status"),
            runtime_state.get("status"),
            task_dict.get("status"),
            "unknown",
        )
    )
    action = normalize_status(first_nonempty_str(result.get("action"), runtime_state.get("next_action"), task_dict.get("next_action")))
    error_value = first_nonempty_str(
        result.get("error"),
        runtime_state.get("last_error"),
        runtime_state.get("failure_message"),
        task_dict.get("last_error"),
        task_dict.get("failure_message"),
    )
    final_answer = first_nonempty_str(
        result.get("final_answer"),
        runtime_state.get("final_answer"),
        task_dict.get("final_answer"),
    )
    current_step_index = safe_int(
        result.get(
            "current_step_index",
            runtime_state.get("current_step_index", task_dict.get("current_step_index", 0)),
        ),
        0,
    )
    steps_total = safe_int(
        result.get("steps_total", runtime_state.get("steps_total", task_dict.get("steps_total", 0))),
        0,
    )

    raw = dict(result)
    raw["blocker_gate"] = _blocker_payload_from_sources(
        local={},
        result=result,
        runtime_state=runtime_state,
        task_dict=task_dict,
    )

    return LoopObservation(
        ok=bool(result.get("ok", status not in FAILURE_STATUSES)),
        status=status,
        action=action,
        error=error_value,
        final_answer=final_answer,
        current_step_index=current_step_index,
        steps_total=steps_total,
        raw=raw,
    )


def _blocker_wait_reason(observation: LoopObservation) -> str:
    raw = observation.raw if isinstance(observation.raw, dict) else {}
    gate = raw.get("blocker_gate") if isinstance(raw.get("blocker_gate"), dict) else {}
    blocker = gate.get("first_active_blocker") if isinstance(gate.get("first_active_blocker"), dict) else None
    if not blocker:
        blocker = first_active_blocker({"blockers": gate.get("blockers", [])})

    if isinstance(blocker, dict):
        blocker_type = str(blocker.get("type") or "blocker").strip() or "blocker"
        blocker_id = str(blocker.get("id") or "").strip()
        reason = str(blocker.get("reason") or "").strip()
        if blocker_id and reason:
            return f"task is waiting for blocker: {blocker_type}/{blocker_id} - {reason}"
        if blocker_id:
            return f"task is waiting for blocker: {blocker_type}/{blocker_id}"
        if reason:
            return f"task is waiting for blocker: {blocker_type} - {reason}"
        return f"task is waiting for blocker: {blocker_type}"

    return "task is waiting for external blocker"


def decide_next_action(
    observation: LoopObservation,
    *,
    allow_replan: bool = True,
    max_replans: int = 1,
    replan_count: int = 0,
) -> LoopDecision:
    status = normalize_status(observation.status)
    action = normalize_status(observation.action)
    error = str(observation.error or "").strip()
    final_answer = str(observation.final_answer or "").strip()

    # Blockers are runtime state, not AgentLoop special cases. Review,
    # approval, audit, human input, and external waits all map to this path.
    if _is_waiting_for_blocker(observation):
        return LoopDecision(
            decision="wait",
            next_action="wait_for_external_event",
            terminal=False,
            should_continue=False,
            should_replan=False,
            should_fail=False,
            reason=_blocker_wait_reason(observation),
            observation=observation.to_dict(),
        )

    if status in SUCCESS_STATUSES:
        return LoopDecision(
            decision="finish",
            next_action="finish",
            terminal=True,
            should_continue=False,
            should_replan=False,
            should_fail=False,
            reason="task reached success terminal status",
            observation=observation.to_dict(),
        )

    if status in BLOCKED_STATUSES:
        return LoopDecision(
            decision="blocked",
            next_action="finish",
            terminal=True,
            should_continue=False,
            should_replan=False,
            should_fail=True,
            reason="task reached blocked terminal status",
            observation=observation.to_dict(),
        )

    if status in FAILURE_STATUSES or observation.ok is False:
        can_replan = bool(allow_replan and replan_count < max(0, int(max_replans)))
        if can_replan:
            return LoopDecision(
                decision="replan",
                next_action="replan",
                terminal=False,
                should_continue=False,
                should_replan=True,
                should_fail=False,
                reason=error or "runner result failed and replan is available",
                observation=observation.to_dict(),
            )
        return LoopDecision(
            decision="fail",
            next_action="finish",
            terminal=True,
            should_continue=False,
            should_replan=False,
            should_fail=True,
            reason=error or "runner result failed and no replan remains",
            observation=observation.to_dict(),
        )

    if action in {"retry", "wait", "scheduler_idle"}:
        return LoopDecision(
            decision="wait",
            next_action="wait",
            terminal=False,
            should_continue=False,
            should_replan=False,
            should_fail=False,
            reason=f"runner action requests wait: {action}",
            observation=observation.to_dict(),
        )

    if final_answer and observation.steps_total <= 0:
        return LoopDecision(
            decision="finish",
            next_action="finish",
            terminal=True,
            should_continue=False,
            should_replan=False,
            should_fail=False,
            reason="final answer exists and no steps remain",
            observation=observation.to_dict(),
        )

    if observation.steps_total > 0 and observation.current_step_index >= observation.steps_total:
        return LoopDecision(
            decision="finish",
            next_action="finish",
            terminal=True,
            should_continue=False,
            should_replan=False,
            should_fail=False,
            reason="current step index reached steps_total",
            observation=observation.to_dict(),
        )

    return LoopDecision(
        decision="continue",
        next_action="run_next_tick",
        terminal=False,
        should_continue=True,
        should_replan=False,
        should_fail=False,
        reason="task is non-terminal and can continue",
        observation=observation.to_dict(),
    )


def observe_and_decide(
    runner_result: Any,
    task: Optional[Dict[str, Any]] = None,
    *,
    allow_replan: bool = True,
    max_replans: int = 1,
    replan_count: int = 0,
    local_observation: Any = None,
) -> Dict[str, Any]:
    if isinstance(local_observation, dict):
        observation = observe_from_local_observation(
            local_observation,
            runner_result=runner_result,
            task=task,
        )
    else:
        observation = observe_runner_result(runner_result, task)

    decision = decide_next_action(
        observation,
        allow_replan=allow_replan,
        max_replans=max_replans,
        replan_count=replan_count,
    )
    mode = infer_decision_mode(task, runner_result, local_observation)
    return guard_loop_decision(decision.to_dict(), mode=mode)


def main() -> int:
    cases = [
        ("finished", {"ok": True, "status": "finished"}, "finish"),
        ("running", {"ok": True, "status": "running", "current_step_index": 0, "steps_total": 2}, "continue"),
        ("failed_replan", {"ok": False, "status": "failed", "error": "tool failed"}, "replan"),
        ("blocked", {"ok": False, "status": "blocked", "error": "guard blocked"}, "blocked"),
        (
            "review_blocker",
            {"ok": True, "status": "waiting_blocker", "blockers": [{"type": "review", "id": "review-1", "status": "pending"}]},
            "wait",
        ),
    ]

    for name, result, expected in cases:
        decision = observe_and_decide(result, max_replans=1, replan_count=0)
        actual = decision.get("decision")
        print(f"[loop-decision] {name}: {actual}")
        if actual != expected:
            print(f"[loop-decision] FAIL: expected {expected}, got {actual}")
            return 1

    print("[loop-decision] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
