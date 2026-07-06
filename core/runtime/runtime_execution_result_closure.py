"""Runtime execution result closure composer.

Composes the data-only closure path from controlled run output to a progress
apply candidate. It does not persist, advance, wake, schedule, or execute.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from core.runtime.runtime_execution_result_intake_gate import evaluate_execution_result_intake
from core.runtime.runtime_result_validation_authority import evaluate_result_validation
from core.runtime.runtime_result_progress_apply_adapter import build_progress_apply_candidate


@dataclass(frozen=True)
class RuntimeExecutionResultClosureRecord:
    loop_closure_candidate_created: bool
    result_intake_authorized: bool
    result_validation_authorized: bool
    progress_apply_candidate_created: bool
    closure_work_id: str
    closure_status: str
    denial_reason: str
    progress_memory_mutated: bool
    cursor_advanced: bool
    scheduler_wake_requested: bool
    runtime_state_mutated: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_execution_result_closure(run_bridge_record: Any) -> RuntimeExecutionResultClosureRecord:
    intake = evaluate_execution_result_intake(run_bridge_record)
    validation = evaluate_result_validation(intake)
    candidate = build_progress_apply_candidate(validation)

    denial = intake.denial_reason or validation.denial_reason or candidate.denial_reason
    return RuntimeExecutionResultClosureRecord(
        loop_closure_candidate_created=bool(candidate.progress_apply_candidate_created),
        result_intake_authorized=bool(intake.result_intake_authorized),
        result_validation_authorized=bool(validation.result_validation_authorized),
        progress_apply_candidate_created=bool(candidate.progress_apply_candidate_created),
        closure_work_id=candidate.progress_work_id,
        closure_status=candidate.progress_status,
        denial_reason=denial,
        progress_memory_mutated=False,
        cursor_advanced=False,
        scheduler_wake_requested=False,
        runtime_state_mutated=False,
    )


__all__ = ["RuntimeExecutionResultClosureRecord", "evaluate_execution_result_closure"]
