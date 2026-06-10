from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Sequence

from core.adaptive.adaptive_contract import AdaptiveAction, AdaptiveDecision, AdaptivePlanRevision, DeviationReport
from core.adaptive.adaptive_memory_context import AdaptiveMemoryContext


class AdaptiveReplanner:
    """Produce bounded decisions and revisions without executing steps."""

    def __init__(self, *, max_retries: int = 2, max_replans: int = 2) -> None:
        self.max_retries = max(0, int(max_retries))
        self.max_replans = max(0, int(max_replans))

    def decide(
        self,
        report: DeviationReport,
        *,
        step: Mapping[str, Any],
        retry_count: int = 0,
        replan_count: int = 0,
        adaptive_memory_context: AdaptiveMemoryContext | Mapping[str, Any] | None = None,
    ) -> AdaptiveDecision:
        if not report.deviation_detected:
            return AdaptiveDecision(AdaptiveAction.CONTINUE, "observation_matches_expected")
        if report.reason == "contract_violation" or not report.recoverable:
            return AdaptiveDecision(
                AdaptiveAction.BLOCK,
                report.reason,
                resume_from_step_id=report.step_id,
                requires_user_review=True,
            )
        if report.reason == "transient_error":
            if retry_count < self.max_retries:
                return AdaptiveDecision(AdaptiveAction.RETRY, "bounded_transient_retry", resume_from_step_id=report.step_id)
            return AdaptiveDecision(AdaptiveAction.BLOCK, "retry_limit_exhausted", resume_from_step_id=report.step_id)
        if replan_count >= self.max_replans:
            return AdaptiveDecision(AdaptiveAction.BLOCK, "replan_limit_exhausted", resume_from_step_id=report.step_id)

        inserted = step.get("adaptive_inserted_steps")
        replaced = step.get("adaptive_replacement_steps")
        action = AdaptiveAction.REPLAN if report.reason == "artifact_missing" or inserted or replaced else AdaptiveAction.RESUME
        return AdaptiveDecision(
            action,
            f"recoverable_{report.reason}",
            resume_from_step_id=report.step_id,
            inserted_steps=tuple(copy.deepcopy(inserted)) if isinstance(inserted, list) else (),
            replaced_steps=tuple(copy.deepcopy(replaced)) if isinstance(replaced, list) else (),
        )

    def revise(
        self,
        *,
        original_plan_id: str,
        steps: Sequence[Mapping[str, Any]],
        failed_step_index: int,
        decision: AdaptiveDecision,
    ) -> tuple[list[dict[str, Any]], AdaptivePlanRevision]:
        revised = [copy.deepcopy(dict(step)) for step in steps]
        changed: list[dict[str, Any]] = []
        if decision.replaced_steps:
            replacement = [copy.deepcopy(dict(step)) for step in decision.replaced_steps]
            revised[failed_step_index : failed_step_index + 1] = replacement
            changed.extend(replacement)
        if decision.inserted_steps:
            inserted = [copy.deepcopy(dict(step)) for step in decision.inserted_steps]
            revised[failed_step_index:failed_step_index] = inserted
            changed.extend(inserted)
        if not changed and 0 <= failed_step_index < len(revised):
            changed.append(copy.deepcopy(revised[failed_step_index]))

        digest = hashlib.sha256(json.dumps(revised, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
        revision = AdaptivePlanRevision(
            original_plan_id=original_plan_id,
            revised_plan_id=f"{original_plan_id}:revision:{digest}",
            revision_reason=decision.reason,
            changed_steps=tuple(changed),
            resume_from_step_id=decision.resume_from_step_id,
        )
        return revised, revision


__all__ = ["AdaptiveReplanner"]
