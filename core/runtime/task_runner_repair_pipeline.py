from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from core.runtime.failure_policy import FailurePolicy
from core.runtime.repair_observability import build_repair_chain_id, build_repair_observability
from core.runtime.task_runner_engineering_action_runtime_helpers import (
    stringify_failure_message as _stringify_failure_message,
)


def maybe_inject_repair_steps_after_failure(
    *,
    runtime: Any,
    repair_planner: Any,
    repair_step_injector: Any,
    audit: Any,
    task: Dict[str, Any],
    state: Dict[str, Any],
    step: Any,
    step_result: Dict[str, Any],
    step_index: int,
    current_tick: int,
    trace_tick: int,
    infer_repair_source_path: Callable[..., str],
    read_repair_source_text: Callable[..., str],
    first_repair_action_path: Callable[[Any], str],
    safe_int: Callable[[Any, int], int],
    trace: Callable[[Dict[str, Any], str, Dict[str, Any]], None],
    stringify_failure_message: Optional[Callable[[Any], str]] = None,
    sync_runtime_state_back_to_task: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None,
) -> Optional[Dict[str, Any]]:
    """
    AER Repair Hook v1.

    Convert an observed runtime failure into injected repair steps.

    This is deliberately gated.  The runtime will only inject repair steps
    when the task or failed step explicitly opts in with auto_repair=True.

    Boundary:
    - The hook does not call an LLM.
    - The hook does not mutate target repo files directly.
    - The hook only writes generated repair candidates into the normal task
      sandbox flow via regular write_file/run_python/verify_file steps.
    """
    if not isinstance(task, dict) or not isinstance(state, dict):
        return None
    if not isinstance(step, dict) or not isinstance(step_result, dict):
        return None
    if bool(step_result.get("ok", False)):
        return None

    if bool(step.get("repair_injected")):
        return None

    if not bool(
        task.get("auto_repair")
        or task.get("enable_auto_repair")
        or step.get("auto_repair")
        or step.get("enable_auto_repair")
    ):
        return None

    repair_context = state.setdefault("repair_context", {})
    if not isinstance(repair_context, dict):
        repair_context = {}
        state["repair_context"] = repair_context

    source_path = infer_repair_source_path(step=step, step_result=step_result)
    repair_chain_id = build_repair_chain_id(
        task=task,
        source_path=source_path,
        step_index=step_index,
        current_tick=current_tick,
    )
    policy_decision_obj = FailurePolicy.decide_repair(
        task=task,
        state=state,
        step=step,
        step_result=step_result,
        source_path=source_path,
    )
    policy_decision = (
        policy_decision_obj.to_dict()
        if hasattr(policy_decision_obj, "to_dict")
        else copy.deepcopy(policy_decision_obj)
    )
    if not isinstance(policy_decision, dict):
        policy_decision = {"allow": False, "action": "fail", "reason": "invalid repair policy decision"}

    observability = build_repair_observability(
        task=task,
        step=step,
        source_path=source_path,
        step_index=step_index,
        current_tick=current_tick,
        policy_decision=policy_decision,
        repair_chain_id=repair_chain_id,
    )
    repair_context["last_repair_observability"] = copy.deepcopy(observability)
    repair_context["last_repair_policy_decision"] = copy.deepcopy(policy_decision)
    repair_context["last_repair_chain_id"] = repair_chain_id

    trace(
        task,
        "repair_policy_decision",
        {
            "step_index": step_index,
            "current_tick": current_tick,
            "trace_tick": trace_tick,
            **copy.deepcopy(observability),
        },
    )
    audit.log_event(
        task,
        "repair_policy_decision",
        {
            "tick": trace_tick,
            "scheduler_tick": current_tick,
            "step_index": step_index,
            **copy.deepcopy(observability),
        },
        source="repair_policy",
    )

    if not bool(policy_decision.get("allow", False)):
        action = str(policy_decision.get("action") or "fail").strip().lower()
        reason = str(policy_decision.get("reason") or "repair policy blocked")
        state["repair_policy_decision"] = copy.deepcopy(policy_decision)
        state["repair_observability"] = copy.deepcopy(observability)
        if action == "review_required" or bool(policy_decision.get("requires_review")):
            state = runtime.apply_runtime_transition(
                task,
                state,
                owner="task_runtime",
                action="repair_policy_review_required",
                updates={
                    "status": "review_required",
                    "next_action": "wait_for_external_event",
                    "last_error": reason,
                },
            )
            state["requires_review"] = True
        else:
            state = runtime.apply_runtime_transition(
                task,
                state,
                owner="task_runtime",
                action="repair_policy_failed",
                updates={
                    "status": "failed",
                    "next_action": "finish",
                    "last_error": reason,
                },
            )
        if bool(policy_decision.get("quarantine")):
            state["repair_quarantine"] = {
                "active": True,
                "reason": reason,
                "repair_chain_id": repair_chain_id,
            }
        try:
            state = runtime.save_runtime_state(task, state)
        except Exception:
            pass
        trace(
            task,
            "repair_policy_blocked",
            {
                "step_index": step_index,
                "current_tick": current_tick,
                "trace_tick": trace_tick,
                **copy.deepcopy(observability),
            },
        )
        return {
            "ok": False,
            "policy_blocked": True,
            "runtime_state": state,
            "repair_policy_decision": copy.deepcopy(policy_decision),
            "repair_chain_id": repair_chain_id,
        }

    max_injections = safe_int(task.get("max_repair_injections") or state.get("max_repair_injections"), 1)
    if max_injections < 1:
        max_injections = 1
    prior_injections = repair_context.get("injections")
    prior_count = len(prior_injections) if isinstance(prior_injections, list) else 0
    if prior_count >= max_injections:
        return None

    source_text = read_repair_source_text(task=task, state=state, source_path=source_path)

    try:
        repair_plan = repair_planner.plan(
            step_result=copy.deepcopy(step_result),
            previous_result=copy.deepcopy(state.get("last_step_result")),
            source_path=source_path,
            source_text=source_text,
            target_path="",
        ).to_dict()
    except Exception as exc:
        repair_context["last_repair_plan_error"] = str(exc)
        try:
            runtime.save_runtime_state(task, state)
        except Exception:
            pass
        return None

    if not isinstance(repair_plan, dict) or not bool(repair_plan.get("ok", False)):
        repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
        try:
            runtime.save_runtime_state(task, state)
        except Exception:
            pass
        return None

    verify_command = ""
    action_path = first_repair_action_path(repair_plan)
    if action_path and action_path.lower().endswith(".py"):
        verify_command = "python -m py_compile " + action_path

    try:
        injection = repair_step_injector.build_injection(
            repair_plan=copy.deepcopy(repair_plan),
            task=task,
            failed_step=step,
            failed_result=step_result,
            verify_command=verify_command,
            report_path=str(task.get("auto_repair_report_path") or "AER_AUTO_REPAIR_REPORT.md"),
        ).to_dict()
    except Exception as exc:
        repair_context["last_repair_injection_error"] = str(exc)
        repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
        try:
            runtime.save_runtime_state(task, state)
        except Exception:
            pass
        return None

    if not isinstance(injection, dict) or not bool(injection.get("ok", False)):
        repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
        repair_context["last_repair_injection"] = copy.deepcopy(injection)
        try:
            runtime.save_runtime_state(task, state)
        except Exception:
            pass
        return None

    injected_steps = injection.get("steps")
    if not isinstance(injected_steps, list) or not injected_steps:
        return None

    try:
        injected_state = repair_step_injector.inject_steps_into_state(
            runtime_state=state,
            injected_steps=injected_steps,
            insert_after_index=step_index,
        )
    except Exception as exc:
        repair_context["last_repair_injection_error"] = str(exc)
        repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
        repair_context["last_repair_injection"] = copy.deepcopy(injection)
        try:
            runtime.save_runtime_state(task, state)
        except Exception:
            pass
        return None

    stringify_failure_message = stringify_failure_message or _stringify_failure_message

    injected_state = runtime.apply_runtime_transition(
        task,
        injected_state,
        owner="task_runtime",
        action="repair_steps_injected",
        updates={
            "status": "running",
            "next_action": "run_next_tick",
            "last_error": stringify_failure_message(step_result.get("error")),
        },
    )
    injected_state["last_repair_plan"] = copy.deepcopy(repair_plan)
    injected_state["last_repair_injection"] = copy.deepcopy(injection)

    repair_context = injected_state.setdefault("repair_context", {})
    if isinstance(repair_context, dict):
        repair_context["last_repair_plan"] = copy.deepcopy(repair_plan)
        repair_context["last_repair_injection"] = copy.deepcopy(injection)
        repair_context["last_repair_source_path"] = source_path
        repair_context["last_repair_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    injected_state = runtime.save_runtime_state(task, injected_state)
    if sync_runtime_state_back_to_task is not None:
        sync_runtime_state_back_to_task(task, injected_state)

    trace(
        task,
        "repair_steps_injected",
        {
            "step_index": step_index,
            "current_tick": current_tick,
            "trace_tick": trace_tick,
            "source_path": source_path,
            "repair_plan": copy.deepcopy(repair_plan),
            "repair_injection": copy.deepcopy(injection),
            "injected_step_count": len(injected_steps),
        },
    )
    audit.log_event(
        task,
        "repair_steps_injected",
        {
            "tick": trace_tick,
            "scheduler_tick": current_tick,
            "step_index": step_index,
            "source_path": source_path,
            "classification": repair_plan.get("classification"),
            "injected_step_count": len(injected_steps),
        },
        source="task_runner",
    )

    return {
        "ok": True,
        "runtime_state": injected_state,
        "repair_plan": repair_plan,
        "repair_injection": injection,
    }
