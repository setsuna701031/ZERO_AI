from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping


RUNTIME_DECISION_ADVISOR_SCHEMA = "zero.runtime.decision_advisor.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _unique_text(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    result: list[str] = []
    for value in values:
        normalized = _text(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _risk_flag(reason: str) -> str:
    normalized = reason.lower()
    if "adapter" in normalized and "unavailable" in normalized:
        return "mutation_adapter_unavailable_risk"
    if "adapter" in normalized and "incomplete" in normalized:
        return "mutation_adapter_incomplete_risk"
    if "validation_failed" in normalized or "validation" in normalized:
        return "validation_failure_risk"
    if "unsafe_path" in normalized or ("unsafe" in normalized and "path" in normalized):
        return "unsafe_path_risk"
    if "rollback" in normalized:
        return "rollback_risk"
    return "prior_denial_risk"


def build_runtime_decision_advice(
    goal: Any,
    memory_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Convert memory context to deterministic, non-authoritative hints."""
    context = _mapping(memory_context)
    recommended_paths = _unique_text(context.get("successful_paths"))
    prior_denial_reasons = _unique_text(context.get("prior_denial_reasons"))
    completed = context.get("completed_experiences")
    previous_success_available = bool(recommended_paths) or bool(
        isinstance(completed, (list, tuple)) and completed
    )

    risk_flags: list[str] = []
    for reason in prior_denial_reasons:
        flag = _risk_flag(reason)
        if flag not in risk_flags:
            risk_flags.append(flag)

    planner_hints: list[dict[str, Any]] = []
    if previous_success_available:
        planner_hints.append({
            "hint": "review_previous_success",
            "recommended_paths": copy.deepcopy(recommended_paths),
            "advisory_only": True,
        })
    if prior_denial_reasons:
        planner_hints.append({
            "hint": "avoid_prior_denials",
            "risk_flags": copy.deepcopy(risk_flags),
            "advisory_only": True,
        })

    return {
        "schema": RUNTIME_DECISION_ADVISOR_SCHEMA,
        "ok": True,
        "advisor_status": "advice_available" if planner_hints else "no_advice",
        "goal": _text(goal),
        "previous_success_available": previous_success_available,
        "recommended_paths": recommended_paths,
        "prior_denial_reasons": prior_denial_reasons,
        "risk_flags": risk_flags,
        "planner_hints": planner_hints,
        "read_only": True,
        "decision_authority": False,
        "requested_changes_modified": False,
    }


@dataclass(frozen=True)
class RuntimeDecisionAdvisor:
    def advise(
        self,
        goal: Any,
        memory_context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return build_runtime_decision_advice(goal, memory_context)


__all__ = [
    "RUNTIME_DECISION_ADVISOR_SCHEMA",
    "RuntimeDecisionAdvisor",
    "build_runtime_decision_advice",
]
