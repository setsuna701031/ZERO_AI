from __future__ import annotations

"""Delta calculation for Adaptive Loop v2 observations.

AdaptiveDelta compares two passive observations.  It does not decide future
work, execute runtime actions, persist records, mutate goals, or write memory.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.adaptive.adaptive_observation import AdaptiveObservation


ADAPTIVE_DELTA_SCHEMA = "zero.adaptive_loop.delta.v2"


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _observation(value: AdaptiveObservation | Mapping[str, Any] | None) -> AdaptiveObservation | None:
    if value is None:
        return None
    if isinstance(value, AdaptiveObservation):
        return value
    if isinstance(value, Mapping):
        return AdaptiveObservation.from_mapping(value)
    raise TypeError("adaptive_delta_requires_observation_or_mapping")


@dataclass(frozen=True)
class AdaptiveDelta:
    goal_id: str
    previous_cycle_index: int | None
    current_cycle_index: int
    runtime_state_changed: bool = False
    adaptive_decision_changed: bool = False
    evidence_count_delta: int = 0
    validated_evidence_delta: int = 0
    remaining_task_delta: int = 0
    completed_task_delta: int = 0
    failed_task_delta: int = 0
    blocked_task_delta: int = 0
    has_progress: bool = False
    regressed: bool = False
    stalled: bool = False
    reason: str = ""
    previous_observation: Mapping[str, Any] = field(default_factory=dict)
    current_observation: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_observations(
        cls,
        previous: AdaptiveObservation | Mapping[str, Any] | None,
        current: AdaptiveObservation | Mapping[str, Any],
    ) -> "AdaptiveDelta":
        previous_obs = _observation(previous)
        current_obs = _observation(current)
        assert current_obs is not None
        if previous_obs is None:
            return cls(
                goal_id=current_obs.goal_id,
                previous_cycle_index=None,
                current_cycle_index=current_obs.cycle_index,
                has_progress=False,
                regressed=False,
                stalled=False,
                reason="initial_observation",
                previous_observation={},
                current_observation=current_obs.to_dict(),
            )
        evidence_delta = current_obs.evidence_count - previous_obs.evidence_count
        validated_delta = current_obs.validated_evidence_count - previous_obs.validated_evidence_count
        remaining_delta = current_obs.remaining_task_count - previous_obs.remaining_task_count
        completed_delta = current_obs.completed_task_count - previous_obs.completed_task_count
        failed_delta = current_obs.failed_task_count - previous_obs.failed_task_count
        blocked_delta = current_obs.blocked_task_count - previous_obs.blocked_task_count
        progress = completed_delta > 0 or remaining_delta < 0 or evidence_delta > 0 or validated_delta > 0
        regressed = remaining_delta > 0 or failed_delta > 0 or blocked_delta > 0
        state_changed = current_obs.runtime_state != previous_obs.runtime_state
        decision_changed = current_obs.adaptive_decision != previous_obs.adaptive_decision
        stalled = not progress and not regressed and not state_changed and not decision_changed
        reason = "progress_detected" if progress else "regression_detected" if regressed else "stalled" if stalled else "state_or_decision_changed"
        return cls(
            goal_id=current_obs.goal_id,
            previous_cycle_index=previous_obs.cycle_index,
            current_cycle_index=current_obs.cycle_index,
            runtime_state_changed=state_changed,
            adaptive_decision_changed=decision_changed,
            evidence_count_delta=evidence_delta,
            validated_evidence_delta=validated_delta,
            remaining_task_delta=remaining_delta,
            completed_task_delta=completed_delta,
            failed_task_delta=failed_delta,
            blocked_task_delta=blocked_delta,
            has_progress=progress,
            regressed=regressed,
            stalled=stalled,
            reason=reason,
            previous_observation=previous_obs.to_dict(),
            current_observation=current_obs.to_dict(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_DELTA_SCHEMA,
            "goal_id": self.goal_id,
            "previous_cycle_index": self.previous_cycle_index,
            "current_cycle_index": self.current_cycle_index,
            "runtime_state_changed": self.runtime_state_changed,
            "adaptive_decision_changed": self.adaptive_decision_changed,
            "evidence_count_delta": self.evidence_count_delta,
            "validated_evidence_delta": self.validated_evidence_delta,
            "remaining_task_delta": self.remaining_task_delta,
            "completed_task_delta": self.completed_task_delta,
            "failed_task_delta": self.failed_task_delta,
            "blocked_task_delta": self.blocked_task_delta,
            "has_progress": self.has_progress,
            "regressed": self.regressed,
            "stalled": self.stalled,
            "reason": self.reason,
            "previous_observation": copy.deepcopy(dict(self.previous_observation)),
            "current_observation": copy.deepcopy(dict(self.current_observation)),
            "execution_path": {
                "delta_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


def build_adaptive_delta(
    previous: AdaptiveObservation | Mapping[str, Any] | None,
    current: AdaptiveObservation | Mapping[str, Any],
) -> dict[str, Any]:
    return AdaptiveDelta.from_observations(previous, current).to_dict()


__all__ = ["ADAPTIVE_DELTA_SCHEMA", "AdaptiveDelta", "build_adaptive_delta"]
