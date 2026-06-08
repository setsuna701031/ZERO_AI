from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class TaskLifecycleSnapshot:
    task_id: str
    status: str
    lifecycle_state: str
    current_stage: Any = None
    current_goal: str = ""
    current_step: Any = None
    created_at: Any = None
    updated_at: Any = None
    result_summary: str = ""
    error_summary: str = ""
    issue_reports: Any = field(default_factory=list)
    artifacts: List[Any] = field(default_factory=list)
    next_action: Any = None
    outcome_class: Any = None
    replan_count: Any = None
    continuation_count: Any = None
    adaptive_decision: Any = None
    decision_reason: Any = None
    decision_evidence: List[Any] = field(default_factory=list)
    data_completeness: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(
            {
                "task_id": self.task_id,
                "status": self.status,
                "lifecycle_state": self.lifecycle_state,
                "current_stage": self.current_stage,
                "current_goal": self.current_goal,
                "current_step": self.current_step,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "result_summary": self.result_summary,
                "error_summary": self.error_summary,
                "issue_reports": self.issue_reports,
                "artifacts": self.artifacts,
                "next_action": self.next_action,
                "outcome_class": self.outcome_class,
                "replan_count": self.replan_count,
                "continuation_count": self.continuation_count,
                "adaptive_decision": self.adaptive_decision,
                "decision_reason": self.decision_reason,
                "decision_evidence": self.decision_evidence,
                "data_completeness": self.data_completeness,
            }
        )


__all__ = ["TaskLifecycleSnapshot"]
