from __future__ import annotations

import copy
from typing import Any, Dict

from core.tools.tool_budget import evaluate_tool_budget
from core.tools.tool_failure_policy import recommend_for_previous_failures
from core.tools.tool_risk_policy import assess_tool_risk


ALLOW_TOOL = "ALLOW_TOOL"
DENY_TOOL = "DENY_TOOL"
ANSWER_DIRECTLY = "ANSWER_DIRECTLY"
NEED_CONFIRMATION = "NEED_CONFIRMATION"
STOP = "STOP"
REPLAN = "REPLAN"

FINAL_DECISIONS = {
    ALLOW_TOOL,
    DENY_TOOL,
    ANSWER_DIRECTLY,
    NEED_CONFIRMATION,
    STOP,
    REPLAN,
}


class ToolController:
    """
    Single final-decision gate for L5/B tool proposals.

    Policies may recommend. This controller is the only module that emits the
    final decision enum consumed by executors and the agent loop.
    """

    def decide(
        self,
        *,
        proposal: Any,
        policy_recommendation: Dict[str, Any],
        decision_input: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload = normalize_decision_input(decision_input, proposal=proposal, policy=policy_recommendation)
        policy_status = str(policy_recommendation.get("status") or "")
        policy_ok = policy_recommendation.get("ok") is True

        if policy_status == "no_tool":
            return _decision(
                ANSWER_DIRECTLY,
                "policy_recommended_no_tool",
                policy_recommendation,
                payload,
            )

        if _should_answer_from_existing_observation(payload, policy_recommendation):
            return _decision(
                ANSWER_DIRECTLY,
                "repeated_tool_proposal_after_observation",
                policy_recommendation,
                payload,
            )

        budget = evaluate_tool_budget(payload)
        risk = assess_tool_risk(
            tool=policy_recommendation.get("tool") or payload.get("requested_tool"),
            args=policy_recommendation.get("args"),
            schema=policy_recommendation.get("schema"),
            policy=policy_recommendation.get("policy"),
        )
        if budget.get("ok") is not True:
            return _decision(
                STOP,
                str(budget.get("reason") or "budget_stop"),
                policy_recommendation,
                payload,
                budget=budget,
                risk=risk,
            )

        failure = recommend_for_previous_failures(payload.get("previous_failures"))
        if failure.get("recommendation") == "STOP":
            return _decision(
                STOP,
                str(failure.get("reason") or "failure_policy_stop"),
                policy_recommendation,
                payload,
                budget=budget,
                failure=failure,
                risk=risk,
            )
        if failure.get("recommendation") == "REPLAN":
            return _decision(
                REPLAN,
                str(failure.get("reason") or "failure_policy_replan"),
                policy_recommendation,
                payload,
                budget=budget,
                failure=failure,
                risk=risk,
            )

        if not policy_ok:
            if policy_status == "invalid_args":
                final = REPLAN
            elif policy_status == "denied":
                final = DENY_TOOL
            elif policy_status == "invalid_tool":
                final = STOP
            else:
                final = DENY_TOOL
            return _decision(
                final,
                str(policy_recommendation.get("reason") or policy_status or "policy_denied"),
                policy_recommendation,
                payload,
                budget=budget,
                failure=failure,
                risk=risk,
            )

        if risk.get("confirmation_required") is True:
            return _decision(
                NEED_CONFIRMATION,
                "high_risk_tool_requires_confirmation",
                policy_recommendation,
                payload,
                budget=budget,
                failure=failure,
                risk=risk,
            )

        return _decision(
            ALLOW_TOOL,
            str(policy_recommendation.get("reason") or "controller_allowed"),
            policy_recommendation,
            payload,
            budget=budget,
            failure=failure,
            risk=risk,
        )


def normalize_decision_input(
    value: Dict[str, Any] | None,
    *,
    proposal: Any = None,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = copy.deepcopy(value) if isinstance(value, dict) else {}
    policy_payload = policy if isinstance(policy, dict) else {}
    payload.setdefault("goal", "")
    payload.setdefault("requested_tool", str(policy_payload.get("tool") or ""))
    payload.setdefault("last_tool", "")
    payload.setdefault("observation_summary", "")
    payload.setdefault("previous_failures", [])
    payload.setdefault("budget_remaining", {})
    payload.setdefault("tool_budget", {})
    payload.setdefault("tool_calls", 0)
    payload.setdefault("loop_steps", 0)
    payload.setdefault("same_tool_repeats", 0)
    payload.setdefault("retries_for_tool", 0)
    payload["proposal_summary"] = _proposal_summary(proposal)
    return payload


def controller_observation(controller_decision: Dict[str, Any]) -> Dict[str, Any]:
    final_decision = str(controller_decision.get("final_decision") or STOP)
    policy = controller_decision.get("policy_recommendation") if isinstance(controller_decision.get("policy_recommendation"), dict) else {}
    status = _status_for_non_execution(final_decision, policy)
    tool = str(policy.get("tool") or controller_decision.get("decision_input", {}).get("requested_tool") or "")
    args = policy.get("args") if isinstance(policy.get("args"), dict) else {}
    reason = str(controller_decision.get("reason") or status)
    return {
        "ok": final_decision == ANSWER_DIRECTLY,
        "tool": tool,
        "args": copy.deepcopy(args),
        "status": status,
        "final_decision": final_decision,
        "output": {
            "status": status,
            "tool": tool,
            "final_decision": final_decision,
            "controller": copy.deepcopy(controller_decision),
            "policy": copy.deepcopy(policy.get("policy") or {}),
            "observation": {
                "type": "no_tool" if final_decision == ANSWER_DIRECTLY else "tool_error",
                "summary": reason,
                "data": {
                    "status": status,
                    "reason": reason,
                    "final_decision": final_decision,
                },
            },
            "trace": {
                "tool_call_id": None,
                "tool": tool,
                "args": _summarize_args(args),
                "duration_ms": 0,
                "source": "tool_controller",
            },
        },
        "error": None if final_decision == ANSWER_DIRECTLY else reason,
        "request_id": None,
        "side_effect_level": "none",
    }


def annotate_tool_result(tool_result: Dict[str, Any], controller_decision: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(tool_result)
    result["final_decision"] = str(controller_decision.get("final_decision") or "")
    output = result.get("output") if isinstance(result.get("output"), dict) else {}
    output = copy.deepcopy(output)
    output["controller"] = copy.deepcopy(controller_decision)
    result["output"] = output
    return result


def _decision(
    final_decision: str,
    reason: str,
    policy: Dict[str, Any],
    decision_input: Dict[str, Any],
    *,
    budget: Dict[str, Any] | None = None,
    failure: Dict[str, Any] | None = None,
    risk: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    input_payload = copy.deepcopy(decision_input)
    if isinstance(budget, dict) and isinstance(budget.get("budget_remaining"), dict):
        input_payload["budget_remaining"] = copy.deepcopy(budget.get("budget_remaining"))
    risk_payload = copy.deepcopy(risk or {})
    why = _why_fields(final_decision, reason, policy, budget=budget, failure=failure, risk=risk_payload)
    return {
        "ok": final_decision == ALLOW_TOOL,
        "final_decision": final_decision,
        "reason": reason,
        "risk_level": str(risk_payload.get("risk_level") or ""),
        "risk_reason": str(risk_payload.get("risk_reason") or ""),
        "confirmation_required": bool(risk_payload.get("confirmation_required")),
        "why_call_tool": why["why_call_tool"],
        "why_not_call_tool": why["why_not_call_tool"],
        "why_stop_or_replan": why["why_stop_or_replan"],
        "requested_tool": policy.get("tool"),
        "policy_recommendation": copy.deepcopy(policy),
        "risk_recommendation": risk_payload,
        "budget_recommendation": copy.deepcopy(budget or {}),
        "failure_recommendation": copy.deepcopy(failure or {}),
        "decision_input": input_payload,
    }


def _status_for_non_execution(final_decision: str, policy: Dict[str, Any]) -> str:
    policy_status = str(policy.get("status") or "").strip()
    if final_decision == ANSWER_DIRECTLY:
        return "no_tool"
    if policy_status in {"invalid_args", "invalid_tool", "denied"}:
        return policy_status
    if final_decision == STOP:
        return "blocked"
    if final_decision == REPLAN:
        return "failed"
    if final_decision == NEED_CONFIRMATION:
        return "denied"
    return "blocked"


def _should_answer_from_existing_observation(decision_input: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    requested_tool = str(decision_input.get("requested_tool") or policy.get("tool") or "")
    last_tool = str(decision_input.get("last_tool") or "")
    observation_summary = str(decision_input.get("observation_summary") or "").strip()
    previous_failures = decision_input.get("previous_failures")
    same_tool_repeats = int(decision_input.get("same_tool_repeats") or 0)
    return bool(
        requested_tool
        and requested_tool == last_tool
        and same_tool_repeats > 0
        and observation_summary
        and not previous_failures
        and policy.get("ok") is True
    )


def _proposal_summary(proposal: Any) -> Dict[str, Any]:
    if not isinstance(proposal, dict):
        return {"type": type(proposal).__name__}
    return {
        "type": proposal.get("type") or "",
        "tool": proposal.get("tool") or "",
        "has_args": isinstance(proposal.get("args"), dict),
    }


def _why_fields(
    final_decision: str,
    reason: str,
    policy: Dict[str, Any],
    *,
    budget: Dict[str, Any] | None = None,
    failure: Dict[str, Any] | None = None,
    risk: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    policy_reason = str(policy.get("reason") or "")
    budget_reason = str((budget or {}).get("reason") or "")
    failure_reason = str((failure or {}).get("reason") or "")
    risk_reason = str((risk or {}).get("risk_reason") or "")
    if final_decision == ALLOW_TOOL:
        return {
            "why_call_tool": policy_reason or reason or "controller_allowed",
            "why_not_call_tool": "",
            "why_stop_or_replan": "",
        }
    if final_decision == ANSWER_DIRECTLY:
        return {
            "why_call_tool": "",
            "why_not_call_tool": reason or policy_reason or "answer_directly",
            "why_stop_or_replan": "",
        }
    if final_decision in {STOP, REPLAN}:
        return {
            "why_call_tool": "",
            "why_not_call_tool": reason or budget_reason or failure_reason,
            "why_stop_or_replan": reason or budget_reason or failure_reason,
        }
    return {
        "why_call_tool": "",
        "why_not_call_tool": reason or risk_reason or policy_reason,
        "why_stop_or_replan": "",
    }


def _summarize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for key, value in (args or {}).items():
        if str(key).lower() == "content":
            summary[str(key)] = {"type": type(value).__name__, "length": len(str(value))}
        else:
            summary[str(key)] = copy.deepcopy(value)
    return summary
