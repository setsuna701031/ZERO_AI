from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


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


def observe_runner_result(runner_result: Any, task: Optional[Dict[str, Any]] = None) -> LoopObservation:
    result = runner_result if isinstance(runner_result, dict) else {}
    task_dict = task if isinstance(task, dict) else {}

    runtime_state = result.get("runtime_state")
    if not isinstance(runtime_state, dict):
        runtime_state = task_dict.get("runtime_state") if isinstance(task_dict.get("runtime_state"), dict) else {}

    status = normalize_status(
        first_nonempty_str(
            result.get("status"),
            runtime_state.get("status"),
            task_dict.get("status"),
            "unknown",
        )
    )

    action = normalize_status(result.get("action"))

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

    return LoopObservation(
        ok=bool(result.get("ok", status not in FAILURE_STATUSES)),
        status=status,
        action=action,
        error=error_value,
        final_answer=final_answer,
        current_step_index=current_step_index,
        steps_total=steps_total,
        raw=dict(result),
    )


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
) -> Dict[str, Any]:
    observation = observe_runner_result(runner_result, task)
    decision = decide_next_action(
        observation,
        allow_replan=allow_replan,
        max_replans=max_replans,
        replan_count=replan_count,
    )
    return decision.to_dict()


def main() -> int:
    cases = [
        ("finished", {"ok": True, "status": "finished"}, "finish"),
        ("running", {"ok": True, "status": "running", "current_step_index": 0, "steps_total": 2}, "continue"),
        ("failed_replan", {"ok": False, "status": "failed", "error": "tool failed"}, "replan"),
        ("blocked", {"ok": False, "status": "blocked", "error": "guard blocked"}, "blocked"),
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
