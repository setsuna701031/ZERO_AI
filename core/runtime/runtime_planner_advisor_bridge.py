from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


RUNTIME_PLANNER_ADVISOR_BRIDGE_SCHEMA = (
    "zero.runtime.planner_advisor_bridge.v1"
)


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


def _normalized_path(value: Any) -> str:
    return _text(value).replace("\\", "/").removeprefix("./")


def _has_caution_risk(risk_flags: Sequence[str]) -> bool:
    caution_terms = ("validation", "unsafe_path", "adapter", "rollback")
    return any(
        any(term in flag.lower() for term in caution_terms)
        for flag in risk_flags
    )


def build_planner_advisor_bridge(
    goal: Any,
    requested_changes: Sequence[Mapping[str, Any]] | None,
    decision_advice: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Translate advisory data to deterministic, non-authoritative rankings."""
    advice = _mapping(decision_advice)
    changes = copy.deepcopy(list(requested_changes or []))
    preferred_paths = (
        _unique_text(advice.get("recommended_paths"))
        if advice.get("previous_success_available") is True
        else []
    )
    avoid_risk_flags = _unique_text(advice.get("risk_flags"))
    preferred_path_keys = {_normalized_path(path) for path in preferred_paths}
    caution = _has_caution_risk(avoid_risk_flags)

    candidate_rankings: list[dict[str, str]] = []
    for change in changes:
        item = change if isinstance(change, Mapping) else {}
        target_path = _normalized_path(item.get("target_path"))
        if target_path and target_path in preferred_path_keys:
            ranking = "preferred"
        elif caution:
            ranking = "caution"
        else:
            ranking = "neutral"
        candidate_rankings.append({
            "change_id": _text(item.get("change_id")),
            "ranking": ranking,
        })

    planner_hints: list[dict[str, Any]] = []
    if preferred_paths:
        planner_hints.append({
            "hint": "prefer_previous_success_paths",
            "paths": copy.deepcopy(preferred_paths),
            "advisory_only": True,
        })
    if avoid_risk_flags:
        planner_hints.append({
            "hint": "avoid_known_risks",
            "risk_flags": copy.deepcopy(avoid_risk_flags),
            "advisory_only": True,
        })

    return {
        "schema": RUNTIME_PLANNER_ADVISOR_BRIDGE_SCHEMA,
        "ok": True,
        "bridge_status": "hints_available" if planner_hints else "no_hints",
        "goal": _text(goal),
        "planner_hints": planner_hints,
        "preferred_paths": preferred_paths,
        "avoid_risk_flags": avoid_risk_flags,
        "candidate_rankings": candidate_rankings,
        "read_only": True,
        "decision_authority": False,
        "requested_changes_modified": False,
    }


@dataclass(frozen=True)
class RuntimePlannerAdvisorBridge:
    def build(
        self,
        goal: Any,
        requested_changes: Sequence[Mapping[str, Any]] | None,
        decision_advice: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return build_planner_advisor_bridge(
            goal, requested_changes, decision_advice
        )


__all__ = [
    "RUNTIME_PLANNER_ADVISOR_BRIDGE_SCHEMA",
    "RuntimePlannerAdvisorBridge",
    "build_planner_advisor_bridge",
]
