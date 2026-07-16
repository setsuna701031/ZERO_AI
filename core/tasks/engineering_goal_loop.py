from __future__ import annotations

"""Long horizon loop for persisted engineering goals.

EngineeringGoalLoop owns only the cycle around EngineeringGoalRunner results.
It does not execute tasks, plan work, mutate runtime internals, or enter the
RuntimeOrchestrator.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_result_projection import mapping_projection

from core.evidence.decision_evidence import DecisionEvidenceRepository
from core.evidence.evidence_authority import EvidenceAuthority
from core.evidence.evidence_repository import EvidenceRepository
from core.tasks.adaptive_persistence_gateway import AdaptivePersistenceGateway
from core.tasks.adaptive_loop_coordinator import AdaptiveLoopCoordinator
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import EngineeringGoalRunner
from core.tasks.engineering_issue_summary import apply_engineering_issue_summary
from core.tasks.engineering_runtime_contract import build_engineering_runtime_contract_from_result
from core.tasks.goal_loop_coordinator import GoalLoopCoordinator
from core.tasks.goal_loop_dispatcher import GoalLoopDispatcher
from core.tasks.goal_loop_terminal_coordinator import GoalLoopTerminalCoordinator
from core.tasks.lifecycle_coordinator import LifecycleCoordinator
from core.session.session_coordinator import SessionCoordinator
from core.session.session_progression_coordinator import SessionProgressionCoordinator
from core.program.program_coordinator import ProgramCoordinator
from core.adaptive.continuation_coordinator import ContinuationCoordinator
from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_coordinator import ReplanCoordinator
from core.adaptive.replan_runtime import ReplanRuntime
from core.goals.goal_completion_authority import is_accepted_goal_completion_result
from core.goals.goal_lineage_contract import (
    GOAL_LINEAGE_FIELDS,
    attach_goal_lineage,
    create_root_goal_lineage,
    extract_goal_lineage,
    lineage_scope_matches,
)


ENGINEERING_GOAL_LOOP_RESPONSIBILITY_MARKERS = {
    "goal_loop_uses_adaptive_loop_coordinator": True,
    "goal_loop_uses_lifecycle_coordinator": True,
    "goal_loop_uses_goal_loop_coordinator": True,
    "goal_loop_uses_session_progression_coordinator": True,
}

ENGINEERING_GOAL_LOOP_SCHEMA = "zero.engineering_goal_loop.v1"
ENGINEERING_GOAL_LOOP_CYCLE_SCHEMA = "zero.engineering_goal_loop.cycle.v1"
ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA = "zero.engineering_goal_loop.continuation_work_item.v2"
ENGINEERING_REPLAN_RECORD_SCHEMA = "zero.engineering_goal_loop.replan_record.v2"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


class EngineeringGoalLoop:
    """Run one engineering goal across bounded adaptive continuation cycles."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        repository: EngineeringGoalRepository | Any | None = None,
        runner: EngineeringGoalRunner | Any | None = None,
        issue_reporter: Any | None = None,
        decision_evidence_repository: DecisionEvidenceRepository | Any | None = None,
        evidence_repository: EvidenceRepository | Any | None = None,
        evidence_authority: EvidenceAuthority | Any | None = None,
        adaptive_persistence_gateway: AdaptivePersistenceGateway | Any | None = None,
        adaptive_loop_coordinator: AdaptiveLoopCoordinator | Any | None = None,
        lifecycle_coordinator: LifecycleCoordinator | Any | None = None,
        goal_loop_coordinator: GoalLoopCoordinator | Any | None = None,
        adaptive_replan_state_machine: Any | None = None,
        engineering_lifecycle_state_machine: Any | None = None,
        session_coordinator: SessionCoordinator | Any | None = None,
        engineering_session_state_machine: Any | None = None,
        program_coordinator: ProgramCoordinator | Any | None = None,
        engineering_program_state_machine: Any | None = None,
        session_progression_coordinator: SessionProgressionCoordinator | Any | None = None,
        continuation_coordinator: ContinuationCoordinator | Any | None = None,
        replan_coordinator: ReplanCoordinator | Any | None = None,
        goal_loop_dispatcher: GoalLoopDispatcher | Any | None = None,
        goal_loop_terminal_coordinator: GoalLoopTerminalCoordinator | Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.repository = repository or EngineeringGoalRepository(self.repo_root)
        self.issue_reporter = issue_reporter
        self.evidence_repository = evidence_repository or EvidenceRepository(self.repo_root)
        self.evidence_authority = evidence_authority or EvidenceAuthority(
            self.repo_root,
            evidence_repository=self.evidence_repository,
        )
        self.decision_evidence_repository = decision_evidence_repository or DecisionEvidenceRepository(
            self.repo_root,
            evidence_repository=self.evidence_repository,
            evidence_authority=self.evidence_authority,
        )
        self.adaptive_persistence_gateway = adaptive_persistence_gateway or AdaptivePersistenceGateway(
            repo_root=self.repo_root,
            repository=self.repository,
            decision_evidence_repository=self.decision_evidence_repository,
            evidence_repository=self.evidence_repository,
            evidence_authority=self.evidence_authority,
        )
        self.adaptive_loop_coordinator = adaptive_loop_coordinator or AdaptiveLoopCoordinator(
            repo_root=self.repo_root,
            adaptive_replan_state_machine=adaptive_replan_state_machine,
        )
        self.lifecycle_coordinator = lifecycle_coordinator or LifecycleCoordinator(
            repo_root=self.repo_root,
            engineering_lifecycle_state_machine=engineering_lifecycle_state_machine,
        )
        self.goal_loop_coordinator = goal_loop_coordinator or GoalLoopCoordinator()
        self.session_coordinator = session_coordinator or SessionCoordinator(
            repo_root=self.repo_root,
            engineering_session_state_machine=engineering_session_state_machine,
        )
        self.program_coordinator = program_coordinator or ProgramCoordinator(
            repo_root=self.repo_root,
            engineering_program_state_machine=engineering_program_state_machine,
        )
        self.session_progression_coordinator = session_progression_coordinator or SessionProgressionCoordinator(
            repo_root=self.repo_root,
            adaptive_loop_coordinator=self.adaptive_loop_coordinator,
            lifecycle_coordinator=self.lifecycle_coordinator,
            session_coordinator=self.session_coordinator,
            program_coordinator=self.program_coordinator,
            goal_loop_coordinator=self.goal_loop_coordinator,
        )
        self.continuation_coordinator = continuation_coordinator or ContinuationCoordinator(
            repo_root=self.repo_root,
            repository=self.repository,
        )
        self.replan_coordinator = replan_coordinator or ReplanCoordinator(repo_root=self.repo_root)
        self.goal_loop_dispatcher = goal_loop_dispatcher or GoalLoopDispatcher(
            repo_root=self.repo_root,
            continuation_coordinator=self.continuation_coordinator,
            replan_coordinator=self.replan_coordinator,
        )
        self.goal_loop_terminal_coordinator = goal_loop_terminal_coordinator or GoalLoopTerminalCoordinator(
            repo_root=self.repo_root,
            issue_reporter=self.issue_reporter,
            evidence_chain_summary=self._evidence_chain_summary,
        )
        self.runner = runner or EngineeringGoalRunner(
            repo_root=self.repo_root,
            repository=self.repository,
            issue_reporter=self.issue_reporter,
        )
        self._last_cycle: dict[str, Any] = {}

    def run_until_terminal(
        # goal_loop_uses_session_progression_coordinator
        self,
        goal_id: str,
        max_cycles: int = 3,
        *,
        max_replans: int = 1,
        max_continuations: int | None = None,
        session_id: str | None = None,
        runtime_session_id: str | None = None,
        goal_lineage: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        target_goal_id = _clean_text(goal_id)
        load_goal = getattr(self.repository, "load_goal", None)
        persisted_goal = load_goal(target_goal_id) if callable(load_goal) else None
        if isinstance(persisted_goal, Mapping):
            current_lineage = extract_goal_lineage(
                persisted_goal,
                require_complete=True,
                reject_conflicts=True,
            )
            if session_id is not None and current_lineage["session_id"] != _clean_text(session_id):
                raise ValueError("engineering_loop_session_identity_conflict")
            if (
                runtime_session_id is not None
                and current_lineage["runtime_session_id"] != _clean_text(runtime_session_id)
            ):
                raise ValueError("engineering_loop_runtime_session_identity_conflict")
            if goal_lineage is not None:
                requested_lineage = extract_goal_lineage(
                    goal_lineage,
                    require_complete=True,
                    reject_conflicts=True,
                )
                if (
                    requested_lineage["goal_id"] != target_goal_id
                    or not lineage_scope_matches(current_lineage, requested_lineage)
                ):
                    raise ValueError("engineering_loop_goal_lineage_identity_conflict")
        else:
            current_lineage = (
                extract_goal_lineage(
                    goal_lineage,
                    require_complete=True,
                    reject_conflicts=True,
                )
                if goal_lineage is not None
                else create_root_goal_lineage(
                    goal_id=target_goal_id,
                    session_id=session_id,
                    runtime_session_id=runtime_session_id,
                )
            )
        cycle_limit = max(1, int(max_cycles or 1))
        replan_limit = max(0, int(max_replans or 0))
        continuation_limit = cycle_limit if max_continuations is None else max(0, int(max_continuations or 0))
        cycles: list[dict[str, Any]] = []
        terminal = False
        stop_reason = "max_cycles_reached"
        refusal_reason = ""

        session_runtime = self.session_progression_coordinator.start_runtime(
            target_goal_id,
            max_cycles=cycle_limit,
            max_replans=replan_limit,
            max_continuations=continuation_limit,
        )
        continuation_runtime = ContinuationRuntime.start(
            target_goal_id,
            continuation_count=0,
            max_continuations=continuation_limit,
            goal_lineage=current_lineage,
        )
        replan_runtime = ReplanRuntime.start(
            replan_count=0,
            max_replans=replan_limit,
            goal_lineage=current_lineage,
        )

        for cycle_index in range(cycle_limit):
            cycle = self.run_one_cycle(
                session_runtime.current_goal_id,
                cycle_index=cycle_index,
                goal_lineage=current_lineage,
            )
            cycle, session_runtime = self.session_progression_coordinator.attach_cycle_progression(
                cycle,
                runtime=session_runtime.replace(
                    replan_count=replan_runtime.replan_count,
                    continuation_count=continuation_runtime.continuation_count,
                    current_goal_id=session_runtime.current_goal_id,
                ),
                cycle_index=cycle_index,
            )
            dispatch_result = self.goal_loop_dispatcher.dispatch(
                loop_decision=_as_mapping(cycle.get("goal_loop_decision")),
                cycle=cycle,
                current_goal_id=session_runtime.current_goal_id,
                cycle_index=cycle_index,
                continuation_runtime=continuation_runtime,
                replan_runtime=replan_runtime,
            )
            cycle = _as_mapping(dispatch_result.cycle)
            continuation_runtime = dispatch_result.continuation_runtime or continuation_runtime
            replan_runtime = dispatch_result.replan_runtime or replan_runtime

            if dispatch_result.refusal_reason:
                self._refuse_adaptive_continuation(cycle, dispatch_result.refusal_reason)

            cycle_completed = is_accepted_goal_completion_result(
                cycle.get("goal_completion_attestation"),
                goal_id=session_runtime.current_goal_id,
            )
            post_completion_continuation_goal_id = ""
            should_handoff_post_completion = False
            if cycle_completed:
                cycle, continuation_runtime = self._create_post_completion_continuation(
                    cycle,
                    current_goal_id=session_runtime.current_goal_id,
                    cycle_index=cycle_index,
                    continuation_runtime=continuation_runtime,
                )
                post_completion_continuation_goal_id = _clean_text(
                    _as_mapping(cycle.get("post_completion_continuation")).get("continuation_goal_id")
                )
                should_handoff_post_completion = bool(
                    post_completion_continuation_goal_id and cycle_index + 1 < cycle_limit
                )
                if should_handoff_post_completion:
                    cycle["terminal"] = False
                    cycle["stop_reason"] = "post_completion_continuation_handoff"
                else:
                    cycle["terminal"] = True
                    cycle["stop_reason"] = "complete"

            self._persist_adaptive_record(
                cycle,
                replan_count=replan_runtime.replan_count,
                continuation_count=continuation_runtime.continuation_count,
                max_replans=replan_limit,
                max_continuations=continuation_limit,
            )

            cycles.append(cycle)
            next_goal_id = (
                post_completion_continuation_goal_id
                if should_handoff_post_completion
                else _clean_text(dispatch_result.current_goal_id, session_runtime.current_goal_id)
            )
            next_stop_reason = (
                "post_completion_continuation_handoff"
                if should_handoff_post_completion
                else _clean_text(dispatch_result.stop_reason, stop_reason)
            )
            session_runtime = session_runtime.replace(
                current_goal_id=next_goal_id,
                replan_count=replan_runtime.replan_count,
                continuation_count=continuation_runtime.continuation_count,
                terminal=False if should_handoff_post_completion else bool(dispatch_result.terminal),
                stop_reason=next_stop_reason,
                refusal_reason=_clean_text(dispatch_result.refusal_reason),
            )

            if should_handoff_post_completion:
                current_lineage = extract_goal_lineage(cycle.get("continuation_work_item"), require_complete=True)
                continue

            dispatch_blocked_terminal = dispatch_result.action == "terminal_blocked"
            if dispatch_result.terminal or dispatch_blocked_terminal or cycle_completed:
                terminal = True
                stop_reason = "complete" if cycle_completed else _clean_text(dispatch_result.stop_reason, "stop")
                refusal_reason = _clean_text(dispatch_result.refusal_reason)
                session_runtime = session_runtime.replace(
                    terminal=True,
                    stop_reason=stop_reason,
                    refusal_reason=refusal_reason,
                    current_goal_id=next_goal_id,
                )
                break

        return self.goal_loop_terminal_coordinator.build_result(
            target_goal_id=target_goal_id,
            current_goal_id=session_runtime.current_goal_id,
            terminal=terminal,
            stop_reason=stop_reason,
            refusal_reason=refusal_reason,
            cycles=cycles,
            max_cycles=cycle_limit,
            max_replans=replan_limit,
            max_continuations=continuation_limit,
            session_runtime=session_runtime,
            continuation_runtime=continuation_runtime,
            replan_runtime=replan_runtime,
        )

    def run_one_cycle(
        self,
        goal_id: str,
        *,
        cycle_index: int = 0,
        goal_lineage: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        lineage = (
            extract_goal_lineage(goal_lineage, require_complete=True, reject_conflicts=True)
            if goal_lineage
            else create_root_goal_lineage(goal_id=goal_id)
        )
        runner_result = self.runner.run_goal(_clean_text(goal_id), goal_lineage=lineage)
        if isinstance(runner_result, Mapping) and (
            isinstance(runner_result.get("goal_lineage"), Mapping)
            or any(runner_result.get(field) for field in GOAL_LINEAGE_FIELDS if field != "goal_id")
        ):
            returned_lineage = extract_goal_lineage(
                runner_result,
                require_complete=True,
                reject_conflicts=True,
            )
            if not lineage_scope_matches(lineage, returned_lineage):
                raise ValueError("engineering_loop_runner_governance_identity_conflict")
            if returned_lineage["goal_id"] != lineage["goal_id"]:
                raise ValueError("engineering_loop_runner_goal_branch_conflict")
        runtime_contract = build_engineering_runtime_contract_from_result(runner_result)
        runtime_result = _as_mapping(runtime_contract.get("runtime_result"))
        adaptive = _as_mapping(runtime_contract.get("adaptive_decision"))
        decision = _clean_text(adaptive.get("decision"))
        root_cause = _as_mapping(adaptive.get("root_cause") or runtime_contract.get("runtime_root_cause"))
        cycle = attach_goal_lineage({
            "schema": ENGINEERING_GOAL_LOOP_CYCLE_SCHEMA,
            "cycle_index": int(cycle_index),
            "goal_id": _clean_text(runtime_contract.get("goal_id"), _clean_text(goal_id)),
            "ok": bool(runtime_contract.get("ok")),
            "runtime_state": _clean_text(runtime_result.get("state")),
            "engineering_runtime_contract": mapping_projection(runtime_contract, max_depth=5, max_items=40),
            "adaptive_decision": decision,
            "adaptive_decision_record": copy.deepcopy(adaptive),
            "adaptive_reason": _clean_text(adaptive.get("reason")),
            "adaptive_confidence": adaptive.get("confidence", 0.0),
            "adaptive_confidence_score": copy.deepcopy(_as_mapping(adaptive.get("confidence_score"))),
            "adaptive_evidence_chain": copy.deepcopy(adaptive.get("evidence_chain") or []),
            "root_cause_report": copy.deepcopy(_as_mapping(adaptive.get("root_cause_report"))),
            "continuation_plan": copy.deepcopy(_as_mapping(adaptive.get("continuation_plan"))),
            "replan_request": copy.deepcopy(_as_mapping(adaptive.get("replan_request"))),
            "runner_result": self._runner_cycle_projection(runner_result),
            "continuation_work_item": {},
            "replan_record": {},
            "adaptive_planning_record": copy.deepcopy(_as_mapping(adaptive.get("adaptive_planning_record"))),
            "adaptive_replan_contract": {},
            "adaptive_replan_state": {},
            "adaptive_observation": {},
            "adaptive_delta": {},
            "adaptive_loop_contract": {},
            "engineering_lifecycle_state": {},
            "engineering_session_state": {},
            "engineering_program_state": {},
            "goal_loop_decision": {},
            "updated_at": time.time(),
        }, lineage)
        completion_attestation = adaptive.get("goal_completion_authority_result")
        if completion_attestation is not None:
            cycle["goal_completion_attestation"] = completion_attestation
            to_dict = getattr(completion_attestation, "to_dict", None)
            if callable(to_dict):
                cycle["goal_completion_authority_result"] = copy.deepcopy(to_dict())
            elif isinstance(completion_attestation, Mapping):
                cycle["goal_completion_authority_result"] = copy.deepcopy(dict(completion_attestation))

        if decision == "blocked":
            cycle["root_cause"] = root_cause
        self._last_cycle = mapping_projection(cycle, max_depth=6, max_items=50)
        return cycle

    @staticmethod
    def _runner_cycle_projection(runner_result: Any) -> dict[str, Any]:
        if not isinstance(runner_result, Mapping):
            return {}
        return mapping_projection(
            {
                key: runner_result.get(key)
                for key in (
                    "schema", "ok", "action", "goal_id", "goal_lineage",
                    "lineage_id", "parent_goal_id", "root_goal_id",
                    "adaptive_decision", "runtime_root_cause", "execution_path",
                    "issues_found", "blocking_issues", "deferred_issues",
                )
                if key in runner_result
            },
            max_depth=5,
            max_items=40,
        )

    def _refuse_adaptive_continuation(self, cycle: dict[str, Any], reason: str) -> None:
        record = _as_mapping(cycle.get("adaptive_planning_record"))
        record.update(
            {
                "next_action": "stop",
                "decision_reason": _clean_text(reason),
                "refused": True,
                "refusal_reason": _clean_text(reason),
            }
        )
        cycle["adaptive_planning_record"] = record
        cycle["adaptive_refusal_reason"] = _clean_text(reason)
        cycle["decision_reason"] = _clean_text(reason)

    def _create_post_completion_continuation(
        self,
        cycle: dict[str, Any],
        *,
        current_goal_id: str,
        cycle_index: int,
        continuation_runtime: ContinuationRuntime,
    ) -> tuple[dict[str, Any], ContinuationRuntime]:
        plan = _as_mapping(cycle.get("continuation_plan"))
        next_request = _as_mapping(plan.get("next_runtime_request"))
        if not next_request:
            return cycle, continuation_runtime
        if not is_accepted_goal_completion_result(
            cycle.get("goal_completion_attestation"),
            goal_id=_clean_text(current_goal_id),
        ):
            return cycle, continuation_runtime
        if continuation_runtime.limit_reached:
            cycle["post_completion_continuation_refusal"] = "max_continuations_exhausted"
            return cycle, continuation_runtime

        work_item, next_runtime = self.continuation_coordinator.create_work_item(
            runtime=continuation_runtime,
            cycle=cycle,
            goal_id=current_goal_id,
            cycle_index=cycle_index,
            continuation_plan=plan,
            runner_result=_as_mapping(cycle.get("runner_result")),
        )
        updated = dict(cycle)
        updated["continuation_work_item"] = work_item
        updated["post_completion_continuation_created"] = True
        updated["post_completion_continuation"] = {
            "created": True,
            "source_goal_id": _clean_text(current_goal_id),
            "continuation_goal_id": _clean_text(work_item.get("goal_id")),
            "continuation_index": int(continuation_runtime.continuation_count) + 1,
            "max_continuations": int(continuation_runtime.max_continuations),
            "execution_path": {
                "after_goal_completion": True,
                "uses_continuation_coordinator": True,
                "executes_tasks": False,
                "bypasses_scheduler": False,
            },
        }
        return updated, next_runtime

    def _persist_adaptive_record(
        self,
        cycle: dict[str, Any],
        *,
        replan_count: int,
        continuation_count: int,
        max_replans: int,
        max_continuations: int,
    ) -> None:
        persist_cycle = getattr(self.adaptive_persistence_gateway, "persist_cycle", None)
        if not callable(persist_cycle):
            raise TypeError("engineering_goal_loop_requires_adaptive_persistence_gateway")
        persist_cycle(
            cycle,
            replan_count=replan_count,
            continuation_count=continuation_count,
            max_replans=max_replans,
            max_continuations=max_continuations,
        )

    def _evidence_chain_summary(self, goal_id: str) -> dict[str, Any]:
        evidence_chain_summary = getattr(self.adaptive_persistence_gateway, "evidence_chain_summary", None)
        if not callable(evidence_chain_summary):
            return {}
        return evidence_chain_summary(_clean_text(goal_id))


__all__ = [
    "ENGINEERING_CONTINUATION_WORK_ITEM_SCHEMA",
    "ENGINEERING_GOAL_LOOP_CYCLE_SCHEMA",
    "ENGINEERING_GOAL_LOOP_SCHEMA",
    "ENGINEERING_REPLAN_RECORD_SCHEMA",
    "EngineeringGoalLoop",
]
