from __future__ import annotations

"""Configurable safety policy for goal-aware adaptive planning."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AdaptivePolicy:
    require_evidence_for_completion: bool = True
    require_all_subgoals_completed: bool = True
    require_review_for_resume: bool = True
    prevent_runtime_bypass: bool = True


__all__ = ["AdaptivePolicy"]
