from __future__ import annotations

from typing import Any, Callable, Dict

from core.tasks.scheduler_core.overlay_v7332 import (
    _zero_v7332_constitutional_boundary_payload,
    _zero_v7332_constitutional_metadata,
    _zero_v7332_is_constitutional_block,
    _zero_v7332_mark_constitutional_boundary,
    _zero_v7332_repairable_decision,
)
from core.tasks.scheduler_core.overlay_v7333 import (
    _zero_v7333_attach_governed_continuation,
    _zero_v7333_governed_continuation_summary,
    _zero_v7333_repairable_decision,
)
from core.tasks.scheduler_core.overlay_v7334 import (
    _zero_v7334_attach_self_repair_summary,
    _zero_v7334_governed_self_repair_summary,
    _zero_v7334_repairable_decision,
)
from core.tasks.scheduler_core.overlay_v7335 import (
    _zero_v7335_attach_controlled_mutation_bridge,
    _zero_v7335_controlled_mutation_bridge_summary,
    _zero_v7335_has_approved_execution_authority,
    _zero_v7335_is_repair_work,
    _zero_v7335_repairable_decision,
)
from core.tasks.scheduler_core.overlay_v7336 import (
    _zero_v7336_attach_verified_mutation_continuation,
    _zero_v7336_repairable_decision,
    _zero_v7336_verified_mutation_continuation_summary,
)


def install_scheduler_final_tail_overlays(
    scheduler_cls: Any,
    *,
    global_lookup: Callable[[str, Any], Any],
    status_review_required: str,
) -> Dict[str, Any]:
    original_run_v7332 = scheduler_cls.run_one_step

    def _zero_v7332_scheduler_run_one_step(self, task, current_tick=None):
        base = global_lookup("_ZERO_V7332_ORIGINAL_SCHEDULER_RUN_ONE_STEP", original_run_v7332)
        result = base(self, task=task, current_tick=current_tick)
        return _zero_v7332_mark_constitutional_boundary(
            self,
            task=task if isinstance(task, dict) else {},
            runner_result=result if isinstance(result, dict) else {"raw_result": result},
            status_review_required=status_review_required,
        )

    scheduler_cls.run_one_step = _zero_v7332_scheduler_run_one_step
    original_repair_v7332 = scheduler_cls._is_repairable_failure

    def _zero_v7332_is_repairable_failure(self, task):
        original = global_lookup("_ZERO_V7332_ORIGINAL_IS_REPAIRABLE_FAILURE", original_repair_v7332)
        return _zero_v7332_repairable_decision(task, original, self)

    scheduler_cls._is_repairable_failure = _zero_v7332_is_repairable_failure

    original_run_v7333 = scheduler_cls.run_one_step

    def _zero_v7333_scheduler_run_one_step(self, task, current_tick=None):
        base = global_lookup("_ZERO_V7333_ORIGINAL_SCHEDULER_RUN_ONE_STEP", original_run_v7333)
        result = base(self, task=task, current_tick=current_tick)
        return _zero_v7333_attach_governed_continuation(
            self,
            task=task if isinstance(task, dict) else {},
            runner_result=result if isinstance(result, dict) else {"raw_result": result},
            status_review_required=status_review_required,
        )

    scheduler_cls.run_one_step = _zero_v7333_scheduler_run_one_step
    original_repair_v7333 = scheduler_cls._is_repairable_failure

    def _zero_v7333_is_repairable_failure(self, task):
        original = global_lookup("_ZERO_V7333_ORIGINAL_IS_REPAIRABLE_FAILURE", original_repair_v7333)
        return _zero_v7333_repairable_decision(task, original, self)

    scheduler_cls._is_repairable_failure = _zero_v7333_is_repairable_failure

    original_run_v7334 = scheduler_cls.run_one_step

    def _zero_v7334_scheduler_run_one_step(self, task, current_tick=None):
        base = global_lookup("_ZERO_V7334_ORIGINAL_SCHEDULER_RUN_ONE_STEP", original_run_v7334)
        result = base(self, task=task, current_tick=current_tick)
        if isinstance(result, dict):
            result = _zero_v7334_attach_self_repair_summary(result)
            for target in (task, result.get("task"), result.get("runtime_state")):
                if isinstance(target, dict):
                    _zero_v7334_attach_self_repair_summary(target)
        return result

    scheduler_cls.run_one_step = _zero_v7334_scheduler_run_one_step
    original_repair_v7334 = scheduler_cls._is_repairable_failure

    def _zero_v7334_is_repairable_failure(self, task):
        original = global_lookup("_ZERO_V7334_ORIGINAL_IS_REPAIRABLE_FAILURE", original_repair_v7334)
        return _zero_v7334_repairable_decision(task, original, self)

    scheduler_cls._is_repairable_failure = _zero_v7334_is_repairable_failure

    original_run_v7335 = scheduler_cls.run_one_step

    def _zero_v7335_scheduler_run_one_step(self, task, current_tick=None):
        base = global_lookup("_ZERO_V7335_ORIGINAL_SCHEDULER_RUN_ONE_STEP", original_run_v7335)
        result = base(self, task=task, current_tick=current_tick)
        if _zero_v7335_has_approved_execution_authority(task) and not _zero_v7335_is_repair_work(task):
            return result
        if isinstance(result, dict):
            result = _zero_v7335_attach_controlled_mutation_bridge(result)
            for target in (task, result.get("task"), result.get("runtime_state")):
                if isinstance(target, dict):
                    _zero_v7335_attach_controlled_mutation_bridge(target)
        return result

    scheduler_cls.run_one_step = _zero_v7335_scheduler_run_one_step
    original_repair_v7335 = scheduler_cls._is_repairable_failure

    def _zero_v7335_is_repairable_failure(self, task):
        original = global_lookup("_ZERO_V7335_ORIGINAL_IS_REPAIRABLE_FAILURE", original_repair_v7335)
        return _zero_v7335_repairable_decision(task, original, self)

    scheduler_cls._is_repairable_failure = _zero_v7335_is_repairable_failure

    original_run_v7336 = scheduler_cls.run_one_step

    def _zero_v7336_scheduler_run_one_step(self, task, current_tick=None):
        base = global_lookup("_ZERO_V7336_ORIGINAL_SCHEDULER_RUN_ONE_STEP", original_run_v7336)
        result = base(self, task=task, current_tick=current_tick)
        if isinstance(result, dict):
            result = _zero_v7336_attach_verified_mutation_continuation(result)
            for target in (task, result.get("task"), result.get("runtime_state")):
                if isinstance(target, dict):
                    _zero_v7336_attach_verified_mutation_continuation(target)
        return result

    scheduler_cls.run_one_step = _zero_v7336_scheduler_run_one_step
    original_repair_v7336 = scheduler_cls._is_repairable_failure

    def _zero_v7336_is_repairable_failure(self, task):
        original = global_lookup("_ZERO_V7336_ORIGINAL_IS_REPAIRABLE_FAILURE", original_repair_v7336)
        return _zero_v7336_repairable_decision(task, original, self)

    scheduler_cls._is_repairable_failure = _zero_v7336_is_repairable_failure

    return {
        "_zero_v7332_constitutional_metadata": _zero_v7332_constitutional_metadata,
        "_zero_v7332_is_constitutional_block": _zero_v7332_is_constitutional_block,
        "_zero_v7332_constitutional_boundary_payload": _zero_v7332_constitutional_boundary_payload,
        "_zero_v7332_mark_constitutional_boundary": _zero_v7332_mark_constitutional_boundary,
        "_ZERO_V7332_ORIGINAL_SCHEDULER_RUN_ONE_STEP": original_run_v7332,
        "_zero_v7332_scheduler_run_one_step": _zero_v7332_scheduler_run_one_step,
        "_ZERO_V7332_ORIGINAL_IS_REPAIRABLE_FAILURE": original_repair_v7332,
        "_zero_v7332_is_repairable_failure": _zero_v7332_is_repairable_failure,
        "_zero_v7333_governed_continuation_summary": _zero_v7333_governed_continuation_summary,
        "_zero_v7333_attach_governed_continuation": _zero_v7333_attach_governed_continuation,
        "_ZERO_V7333_ORIGINAL_SCHEDULER_RUN_ONE_STEP": original_run_v7333,
        "_zero_v7333_scheduler_run_one_step": _zero_v7333_scheduler_run_one_step,
        "_ZERO_V7333_ORIGINAL_IS_REPAIRABLE_FAILURE": original_repair_v7333,
        "_zero_v7333_is_repairable_failure": _zero_v7333_is_repairable_failure,
        "_zero_v7334_governed_self_repair_summary": _zero_v7334_governed_self_repair_summary,
        "_zero_v7334_attach_self_repair_summary": _zero_v7334_attach_self_repair_summary,
        "_ZERO_V7334_ORIGINAL_SCHEDULER_RUN_ONE_STEP": original_run_v7334,
        "_zero_v7334_scheduler_run_one_step": _zero_v7334_scheduler_run_one_step,
        "_ZERO_V7334_ORIGINAL_IS_REPAIRABLE_FAILURE": original_repair_v7334,
        "_zero_v7334_is_repairable_failure": _zero_v7334_is_repairable_failure,
        "_zero_v7335_controlled_mutation_bridge_summary": _zero_v7335_controlled_mutation_bridge_summary,
        "_zero_v7335_attach_controlled_mutation_bridge": _zero_v7335_attach_controlled_mutation_bridge,
        "_ZERO_V7335_ORIGINAL_SCHEDULER_RUN_ONE_STEP": original_run_v7335,
        "_zero_v7335_has_approved_execution_authority": _zero_v7335_has_approved_execution_authority,
        "_zero_v7335_is_repair_work": _zero_v7335_is_repair_work,
        "_zero_v7335_scheduler_run_one_step": _zero_v7335_scheduler_run_one_step,
        "_ZERO_V7335_ORIGINAL_IS_REPAIRABLE_FAILURE": original_repair_v7335,
        "_zero_v7335_is_repairable_failure": _zero_v7335_is_repairable_failure,
        "_zero_v7336_verified_mutation_continuation_summary": _zero_v7336_verified_mutation_continuation_summary,
        "_zero_v7336_attach_verified_mutation_continuation": _zero_v7336_attach_verified_mutation_continuation,
        "_ZERO_V7336_ORIGINAL_SCHEDULER_RUN_ONE_STEP": original_run_v7336,
        "_zero_v7336_scheduler_run_one_step": _zero_v7336_scheduler_run_one_step,
        "_ZERO_V7336_ORIGINAL_IS_REPAIRABLE_FAILURE": original_repair_v7336,
        "_zero_v7336_is_repairable_failure": _zero_v7336_is_repairable_failure,
    }
