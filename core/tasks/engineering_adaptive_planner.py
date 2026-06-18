from __future__ import annotations

"""Post-runtime adaptive planning for engineering goals.

EngineeringAdaptivePlanner is a decision-only bridge after one runtime pass. It
does not execute tasks, mutate repository records, persist lifecycle state, or
enter the RuntimeOrchestrator loop.
"""

import copy
import time
from typing import Any, Mapping

from core.tasks.adaptive_planning_foundation import evaluate_runtime_outcome
from core.goals.goal_lineage_contract import attach_goal_lineage, extract_goal_lineage


ENGINEERING_ADAPTIVE_PLANNER_SCHEMA = "zero.engineering_adaptive_planner.v2"
ENGINEERING_ADAPTIVE_DECISION_SCHEMA = "zero.engineering_adaptive_planner.decision.v2"
ENGINEERING_CONTINUATION_PLAN_SCHEMA = "zero.engineering_adaptive_planner.continuation_plan.v2"
ENGINEERING_REPLAN_REQUEST_SCHEMA = "zero.engineering_adaptive_planner.replan_request.v2"
ENGINEERING_ADAPTIVE_EVIDENCE_SCHEMA = "zero.engineering_adaptive_planner.evidence.v2"
ENGINEERING_ADAPTIVE_CONFIDENCE_SCHEMA = "zero.engineering_adaptive_planner.confidence.v2"
ENGINEERING_BLOCKED_ROOT_CAUSE_SCHEMA = "zero.engineering_adaptive_planner.blocked_root_cause.v2"

ALLOWED_ADAPTIVE_DECISIONS = frozenset({"complete", "continue", "replan", "blocked"})
CONTINUE_ALIASES = frozenset({"retry", "again", "next", "resume", "loop"})
RECOVERABLE_MARKERS = (
    "missing_artifact",
    "missing artifact",
    "missing_output",
    "missing output",
    "empty_output",
    "empty output",
    "no_output",
    "no output",
    "artifact_not_found",
    "output_not_found",
    "validation_failed",
    "validation failed",
    "verification_failed",
    "verification failed",
    "replan",
    "repairable",
    "recoverable",
)
BLOCKING_MARKERS = (
    "blocking",
    "critical",
    "fatal",
    "unrecoverable",
    "manual_intervention_required",
    "permission_denied",
    "authority_denied",
)


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _goal_id(goal: Mapping[str, Any]) -> str:
    return _clean_text(goal.get("goal_id") or goal.get("task_id") or goal.get("package_id"))



GOAL_LINEAGE_REQUIRED_FIELDS = (
    "root_goal_id",
    "goal_lineage_id",
    "session_id",
    "runtime_session_id",
    "branch_type",
    "branch_id",
)


def _goal_lineage(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return complete canonical lineage when available.

    Adaptive planning must remain compatible with legacy/non-session goals.
    It may carry lineage forward when callers already provide a complete
    lineage contract, but it must not invent missing session identity or make
    old single-goal tests fail by requiring session/runtime_session fields.
    """

    lineage = extract_goal_lineage(value)
    if not lineage:
        return {}
    if not all(_clean_text(lineage.get(field)) for field in GOAL_LINEAGE_REQUIRED_FIELDS):
        return {}
    return lineage


def _attach_lineage(record: Mapping[str, Any], lineage: Mapping[str, Any]) -> dict[str, Any]:
    """Attach lineage only when it is complete enough for the canonical contract."""

    complete_lineage = _goal_lineage(lineage)
    if not complete_lineage:
        return copy.deepcopy(dict(record))
    return attach_goal_lineage(dict(record), dict(complete_lineage))

def _clamp_confidence(value: Any, default: float = 0.75) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return min(1.0, max(0.0, confidence))


def _contains_marker(value: Any, markers: tuple[str, ...]) -> bool:
    text = repr(value).lower() if isinstance(value, Mapping) else str(value or "").lower()
    return any(marker in text for marker in markers)


def _first_text(values: list[Any]) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _target_from_goal(goal: Mapping[str, Any]) -> str:
    payload = _as_mapping(goal.get("payload"))
    return _clean_text(
        payload.get("target_path")
        or payload.get("path")
        or goal.get("target_path")
        or goal.get("path")
    ).replace("\\", "/").lstrip("./")


def _normalize_decision_name(value: Any) -> str:
    decision = _clean_text(value).lower()
    if decision in ALLOWED_ADAPTIVE_DECISIONS:
        return decision
    if decision in CONTINUE_ALIASES:
        return "continue"
    return "blocked"


def normalize_adaptive_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    """Return the strict, backwards-compatible Adaptive Planning v2 contract."""

    raw = _as_mapping(decision)
    normalized_decision = _normalize_decision_name(raw.get("decision"))
    reason = _clean_text(raw.get("reason"))
    if not reason:
        reason = "invalid_adaptive_decision" if normalized_decision == "blocked" else f"{normalized_decision}_requested"

    lineage = _goal_lineage(raw)
    normalized = {
        **raw,
        "decision": normalized_decision,
        "reason": reason,
        "confidence": _clamp_confidence(raw.get("confidence")),
        "next_action": _clean_text(raw.get("next_action")),
        "continuation_plan": copy.deepcopy(_as_mapping(raw.get("continuation_plan"))),
        "replan_request": copy.deepcopy(_as_mapping(raw.get("replan_request"))),
        "blocking_issues": copy.deepcopy(_as_list(raw.get("blocking_issues"))),
        "decision_reasoning": copy.deepcopy(_as_mapping(raw.get("decision_reasoning"))),
        "confidence_score": copy.deepcopy(_as_mapping(raw.get("confidence_score"))),
        "evidence_chain": copy.deepcopy(_as_list(raw.get("evidence_chain"))),
        "root_cause_report": copy.deepcopy(_as_mapping(raw.get("root_cause_report"))),
    }
    return _attach_lineage(normalized, lineage) if lineage else normalized


class EngineeringAdaptivePlanner:
    """Decide whether a completed runtime pass finished or needs follow-up."""

    def evaluate_goal_progress(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        runtime_root_cause: Mapping[str, Any] | None = None,
        issue_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        lifecycle = self._latest_lifecycle(runtime_result)
        goal_lineage = _goal_lineage({**_as_mapping(lifecycle), **_as_mapping(runtime_result), **_as_mapping(goal)})
        progress = _as_mapping(lifecycle.get("progress"))
        completed_tasks = _as_list(lifecycle.get("completed_tasks"))
        remaining_tasks = _as_list(lifecycle.get("remaining_tasks"))
        failed_tasks = _as_list(lifecycle.get("failed_tasks"))
        blocked_tasks = _as_list(lifecycle.get("blocked_tasks"))
        goal_state = _clean_text(lifecycle.get("goal_state")).lower()
        runtime_state = _clean_text(runtime_result.get("state")).lower()
        runtime_ok = bool(runtime_result.get("ok"))
        root_cause = _as_mapping(runtime_root_cause)
        issues = _as_mapping(issue_summary)
        blocking_issues = _as_list(issues.get("blocking_issues"))

        recoverable_failure = (
            runtime_state in {"replan", "recoverable_failure", "retryable_failure"}
            or _contains_marker(root_cause, RECOVERABLE_MARKERS)
            or any(_contains_marker(item, RECOVERABLE_MARKERS) for item in failed_tasks)
        )
        hard_blocking_failure = (
            bool(blocking_issues)
            or bool(blocked_tasks)
            or runtime_state in {"blocked"}
            or _contains_marker(root_cause, BLOCKING_MARKERS)
            or any(_contains_marker(item, BLOCKING_MARKERS) for item in failed_tasks)
        )
        blocking_failure = hard_blocking_failure and not recoverable_failure
        complete = (
            runtime_ok
            and goal_state == "completed"
            and not remaining_tasks
            and not failed_tasks
            and not blocked_tasks
            and not blocking_failure
        )
        next_runtime_request = self._next_runtime_request(runtime_result)
        incomplete_with_next_request = runtime_ok and bool(next_runtime_request) and not complete
        progress_record = {
            "schema": ENGINEERING_ADAPTIVE_PLANNER_SCHEMA,
            "goal_id": _goal_id(goal) or _clean_text(lifecycle.get("goal_id")),
            "goal_lineage": copy.deepcopy(goal_lineage),
            "runtime_ok": runtime_ok,
            "runtime_state": runtime_state,
            "goal_state": goal_state,
            "complete": complete,
            "blocked": blocking_failure,
            "remaining_tasks": copy.deepcopy(remaining_tasks),
            "completed_tasks": copy.deepcopy(completed_tasks),
            "failed_tasks": copy.deepcopy(failed_tasks),
            "blocked_tasks": copy.deepcopy(blocked_tasks),
            "progress": copy.deepcopy(progress),
            "root_cause": copy.deepcopy(root_cause),
            "blocking_issues": copy.deepcopy(blocking_issues),
            "blocking_failure": blocking_failure,
            "hard_blocking_failure": hard_blocking_failure,
            "recoverable_failure": recoverable_failure,
            "next_runtime_request": copy.deepcopy(next_runtime_request),
            "incomplete_with_next_request": incomplete_with_next_request,
            "updated_at": time.time(),
        }
        progress_record = _attach_lineage(progress_record, goal_lineage) if goal_lineage else progress_record
        progress_record["evidence_chain"] = self._build_evidence_chain(progress_record)
        return progress_record

    def decide_next_action(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        runtime_root_cause: Mapping[str, Any] | None = None,
        issue_summary: Mapping[str, Any] | None = None,
        replan_count: int = 0,
        continuation_count: int = 0,
        max_replans: int = 1,
        max_continuations: int = 3,
    ) -> dict[str, Any]:
        progress = self.evaluate_goal_progress(
            goal=goal,
            runtime_result=runtime_result,
            runtime_root_cause=runtime_root_cause,
            issue_summary=issue_summary,
        )
        goal_lineage = _goal_lineage(progress)
        if progress["complete"]:
            decision = "complete"
            reason = "goal_completed"
        elif progress["blocking_failure"]:
            decision = "blocked"
            reason = _clean_text(_as_mapping(runtime_root_cause).get("stop_reason"), "blocking_issue_or_unrecoverable_failure")
        elif progress["incomplete_with_next_request"]:
            decision = "continue"
            reason = "next_runtime_request_available"
        elif not progress["runtime_ok"] or progress["recoverable_failure"]:
            decision = "replan"
            reason = _clean_text(_as_mapping(runtime_root_cause).get("stop_reason"), "recoverable_runtime_failure")
        else:
            decision = "continue"
            reason = "goal_incomplete"

        evidence_chain = copy.deepcopy(_as_list(progress.get("evidence_chain")))
        confidence_score = self._score_confidence(decision=decision, progress=progress, evidence_chain=evidence_chain)
        root_cause_report = (
            self._build_root_cause_report(progress=progress, reason=reason, decision=decision)
            if decision in {"blocked", "replan"}
            else {}
        )
        decision_reasoning = self._build_decision_reasoning(
            decision=decision,
            reason=reason,
            progress=progress,
            confidence_score=confidence_score,
        )

        continuation_plan = (
            self.build_continuation_plan(goal=goal, runtime_result=runtime_result, progress=progress)
            if decision == "continue" or (decision == "complete" and bool(progress.get("next_runtime_request")))
            else {}
        )
        mainline_decision = "create_continuation" if continuation_plan and decision == "complete" else decision
        replan_request = (
            self.build_replan_request(goal=goal, runtime_result=runtime_result, progress=progress, reason=reason)
            if decision == "replan"
            else {}
        )
        adaptive_planning_record = evaluate_runtime_outcome(
            runtime_result,
            progress=progress,
            previous_goal=progress["goal_id"],
            previous_step=copy.deepcopy(progress["completed_tasks"][-1]) if progress["completed_tasks"] else None,
            replan_count=replan_count,
            continuation_count=continuation_count,
            max_replans=max_replans,
            max_continuations=max_continuations,
        )
        adaptive_planning_record = _attach_lineage(adaptive_planning_record, goal_lineage) if goal_lineage else adaptive_planning_record
        normalized = normalize_adaptive_decision({
            "schema": ENGINEERING_ADAPTIVE_DECISION_SCHEMA,
            "decision": decision,
            "reason": reason,
            "confidence": confidence_score["score"],
            "confidence_score": confidence_score,
            "decision_reasoning": decision_reasoning,
            "evidence_chain": evidence_chain,
            "next_action": self._next_action_for_decision(decision),
            "mainline_decision": mainline_decision,
            "create_continuation_requested": mainline_decision == "create_continuation",
            "goal_id": progress["goal_id"],
            "goal_lineage": copy.deepcopy(goal_lineage),
            "terminal": decision in {"complete", "blocked"},
            "continue_requested": decision == "continue",
            "complete_requested": decision == "complete",
            "blocked": decision == "blocked",
            "progress": progress,
            "continuation_plan": continuation_plan,
            "replan_request": replan_request,
            "blocking_issues": copy.deepcopy(_as_list(progress.get("blocking_issues"))),
            "root_cause": copy.deepcopy(_as_mapping(runtime_root_cause) if decision in {"blocked", "replan"} else {}),
            "root_cause_report": root_cause_report,
            "outcome_class": adaptive_planning_record["outcome_class"],
            "decision_reason": adaptive_planning_record["decision_reason"],
            "adaptive_planning_record": adaptive_planning_record,
            "execution_path": {
                "adaptive_planner_decides_only": True,
                "executes_tasks": False,
                "persists_goal": False,
                "runtime_orchestrator_loop_owner": False,
            },
            "updated_at": time.time(),
        })
        normalized["terminal"] = normalized["decision"] in {"complete", "blocked"}
        normalized["continue_requested"] = normalized["decision"] == "continue"
        normalized["complete_requested"] = normalized["decision"] == "complete"
        normalized["blocked"] = normalized["decision"] == "blocked"
        if normalized.get("create_continuation_requested"):
            normalized["next_action"] = "create_continuation_work_item"
        return _attach_lineage(normalized, goal_lineage) if goal_lineage else normalized

    def build_continuation_plan(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        progress: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        progress_record = _as_mapping(progress) or self.evaluate_goal_progress(goal=goal, runtime_result=runtime_result)
        goal_id = _goal_id(goal) or _clean_text(progress_record.get("goal_id"))
        goal_lineage = _goal_lineage({**progress_record, **_as_mapping(goal)})
        remaining_tasks = _as_list(progress_record.get("remaining_tasks"))
        next_runtime_request = _as_mapping(progress_record.get("next_runtime_request"))
        request_payload = _as_mapping(next_runtime_request.get("payload"))
        payload = copy.deepcopy(request_payload or _as_mapping(goal.get("payload")))
        payload.setdefault("goal_id", goal_id)
        payload.setdefault("task_id", goal_id)
        payload.setdefault("package_id", goal_id)
        payload.setdefault("goal", _clean_text(goal.get("summary") or goal.get("goal"), goal_id))
        payload.setdefault("task_type", "engineering_task")
        payload.setdefault("engineering_goal_lifecycle", True)
        payload["continuation_requested"] = True
        payload = _attach_lineage(payload, goal_lineage) if goal_lineage else payload
        target_path = _clean_text(payload.get("target_path") or payload.get("path"))
        if not remaining_tasks and target_path:
            remaining_tasks = [target_path]
        payload["remaining_tasks"] = copy.deepcopy(remaining_tasks)
        evidence_chain = copy.deepcopy(_as_list(progress_record.get("evidence_chain")))
        source_runtime_state = _clean_text(next_runtime_request.get("source_runtime_state") or runtime_result.get("state"))
        work_item_template = {
            "objective": _clean_text(payload.get("goal"), f"Continue {goal_id}"),
            "goal_lineage": copy.deepcopy(goal_lineage),
            "source_goal_id": goal_id,
            "task_type": _clean_text(payload.get("task_type"), "engineering_task"),
            "remaining_tasks": copy.deepcopy(remaining_tasks),
            "acceptance": {
                "goal_state": "completed",
                "remaining_tasks": [],
                "failed_tasks": [],
                "blocked_tasks": [],
                "created_file": target_path,
            },
            "provenance": {
                "source_runtime_state": source_runtime_state,
                "evidence_ids": [item["evidence_id"] for item in evidence_chain if isinstance(item, Mapping)],
            },
        }
        continuation_plan = {
            "schema": ENGINEERING_CONTINUATION_PLAN_SCHEMA,
            "goal_id": goal_id,
            "reason": "goal_incomplete",
            "remaining_tasks": copy.deepcopy(remaining_tasks),
            "next_runtime_request": {
                "goal_id": goal_id,
                "payload": payload,
                "source_runtime_state": source_runtime_state,
            },
            "work_item_template": work_item_template,
            "evidence_chain": evidence_chain,
            "execution_path": {
                "plan_only": True,
                "executes_tasks": False,
                "new_runtime_loop": False,
            },
            "created_at": time.time(),
        }
        return _attach_lineage(continuation_plan, goal_lineage) if goal_lineage else continuation_plan

    def build_replan_request(
        self,
        *,
        goal: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        progress: Mapping[str, Any] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        progress_record = _as_mapping(progress) or self.evaluate_goal_progress(goal=goal, runtime_result=runtime_result)
        goal_id = _goal_id(goal) or _clean_text(progress_record.get("goal_id"))
        goal_lineage = _goal_lineage({**progress_record, **_as_mapping(goal)})
        replan_reason = _clean_text(reason, "recoverable_runtime_failure")
        failed_tasks = _as_list(progress_record.get("failed_tasks"))
        remaining_tasks = _as_list(progress_record.get("remaining_tasks"))
        missing_artifacts = self._missing_artifacts(goal=goal, progress=progress_record, runtime_result=runtime_result)
        target_path = _first_text(missing_artifacts) or _first_text(remaining_tasks) or _target_from_goal(goal)
        failed_step = self._failed_step(progress_record)
        next_runtime_request = self._replan_next_runtime_request(
            goal=goal,
            goal_id=goal_id,
            target_path=target_path,
            replan_reason=replan_reason,
        )
        evidence_chain = copy.deepcopy(_as_list(progress_record.get("evidence_chain")))
        root_cause_report = self._build_root_cause_report(
            progress=progress_record,
            reason=replan_reason,
            decision="replan",
        )
        replan_request = {
            "schema": ENGINEERING_REPLAN_REQUEST_SCHEMA,
            "goal_id": goal_id,
            "source_goal_id": goal_id,
            "reason": replan_reason,
            "replan_reason": replan_reason,
            "runtime_state": _clean_text(runtime_result.get("state")),
            "failed_step": failed_step,
            "failed_tasks": copy.deepcopy(failed_tasks),
            "remaining_tasks": copy.deepcopy(remaining_tasks),
            "missing_artifacts": copy.deepcopy(missing_artifacts),
            "root_cause": copy.deepcopy(_as_mapping(progress_record.get("root_cause"))),
            "root_cause_report": root_cause_report,
            "evidence_chain": evidence_chain,
            "next_runtime_request": next_runtime_request,
            "replan_payload": {
                "trigger": replan_reason,
                "objective": "produce_a_revised_execution_plan",
                "preserve": {
                    "completed_tasks": copy.deepcopy(_as_list(progress_record.get("completed_tasks"))),
                    "goal_id": goal_id,
                    "goal_lineage": copy.deepcopy(goal_lineage),
                },
                "reconsider": {
                    "failed_tasks": copy.deepcopy(failed_tasks),
                    "remaining_tasks": copy.deepcopy(remaining_tasks),
                    "missing_artifacts": copy.deepcopy(missing_artifacts),
                },
                "constraints": {
                    "planner_decision_only": True,
                    "execute_tasks": False,
                    "runtime_ownership": False,
                },
            },
            "execution_path": {
                "request_only": True,
                "executes_tasks": False,
                "persists_goal": False,
            },
            "created_at": time.time(),
        }
        return _attach_lineage(replan_request, goal_lineage) if goal_lineage else replan_request

    def _missing_artifacts(
        self,
        *,
        goal: Mapping[str, Any],
        progress: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
    ) -> list[str]:
        root_cause = _as_mapping(progress.get("root_cause"))
        candidates: list[Any] = []
        for key in ("missing_artifacts", "missing_artifact", "target_path", "artifact_path"):
            value = root_cause.get(key)
            if isinstance(value, list):
                candidates.extend(value)
            elif value:
                candidates.append(value)
        for value in _as_list(progress.get("remaining_tasks")) + _as_list(progress.get("failed_tasks")):
            text = _clean_text(value)
            if "/" in text or "\\" in text:
                candidates.append(text.split(":", 1)[-1])
        observed = _as_mapping(runtime_result.get("work_package_result"))
        for key in ("target_path", "target_file"):
            if observed.get(key):
                candidates.append(observed.get(key))
        target = _target_from_goal(goal)
        if target:
            candidates.append(target)
        normalized: list[str] = []
        seen: set[str] = set()
        for value in candidates:
            text = _clean_text(value).replace("\\", "/").lstrip("./")
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    def _failed_step(self, progress: Mapping[str, Any]) -> dict[str, Any]:
        root_cause = _as_mapping(progress.get("root_cause"))
        explicit = _as_mapping(root_cause.get("failed_step"))
        if explicit:
            return explicit
        failed_tasks = _as_list(progress.get("failed_tasks"))
        task = _first_text(failed_tasks)
        return {
            "task_id": task,
            "reason": _clean_text(root_cause.get("stop_reason") or root_cause.get("reason"), "recoverable_runtime_failure"),
        }

    def _replan_next_runtime_request(
        self,
        *,
        goal: Mapping[str, Any],
        goal_id: str,
        target_path: str,
        replan_reason: str,
    ) -> dict[str, Any]:
        payload = copy.deepcopy(_as_mapping(goal.get("payload")))
        payload.setdefault("goal_id", goal_id)
        payload.setdefault("task_id", goal_id)
        payload.setdefault("package_id", goal_id)
        payload.setdefault("goal", _clean_text(goal.get("summary") or goal.get("goal"), goal_id))
        payload.setdefault("task_type", "engineering_task")
        payload.setdefault("operation", "create_file")
        if target_path:
            payload["target_path"] = target_path
        payload["replan_requested"] = True
        payload["replan_reason"] = replan_reason
        goal_lineage = _goal_lineage(goal)
        payload = _attach_lineage(payload, goal_lineage) if goal_lineage else payload
        request = {
            "goal_id": goal_id,
            "payload": payload,
            "source_runtime_state": "replan",
            "replan_reason": replan_reason,
        }
        return _attach_lineage(request, goal_lineage) if goal_lineage else request

    def _build_evidence_chain(self, progress: Mapping[str, Any]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        goal_lineage = _goal_lineage(progress)

        def add(kind: str, source: str, value: Any, supports: list[str]) -> None:
            if value in ("", None, [], {}, False):
                return
            record = {
                "schema": ENGINEERING_ADAPTIVE_EVIDENCE_SCHEMA,
                "evidence_id": f"evidence_{len(evidence) + 1}",
                "kind": kind,
                "source": source,
                "value": copy.deepcopy(value),
                "supports": supports,
                "goal_lineage": copy.deepcopy(goal_lineage),
            }
            evidence.append(_attach_lineage(record, goal_lineage) if goal_lineage else record)

        add("runtime_status", "runtime_result", {
            "ok": bool(progress.get("runtime_ok")),
            "state": _clean_text(progress.get("runtime_state")),
        }, ["complete", "continue", "replan", "blocked"])
        add("goal_status", "runtime_lifecycle", _clean_text(progress.get("goal_state")), ["complete", "continue"])
        add("remaining_work", "runtime_lifecycle", _as_list(progress.get("remaining_tasks")), ["continue", "replan"])
        add("failed_work", "runtime_lifecycle", _as_list(progress.get("failed_tasks")), ["replan", "blocked"])
        add("blocked_work", "runtime_lifecycle", _as_list(progress.get("blocked_tasks")), ["blocked"])
        add("root_cause", "runtime_root_cause", _as_mapping(progress.get("root_cause")), ["replan", "blocked"])
        add("blocking_issues", "issue_summary", _as_list(progress.get("blocking_issues")), ["blocked"])
        add("next_runtime_request", "runtime_result", _as_mapping(progress.get("next_runtime_request")), ["continue"])
        return evidence

    def _score_confidence(
        self,
        *,
        decision: str,
        progress: Mapping[str, Any],
        evidence_chain: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        base = {"complete": 0.72, "continue": 0.62, "replan": 0.66, "blocked": 0.7}[decision]
        factors: list[dict[str, Any]] = []

        def factor(name: str, adjustment: float, present: bool) -> None:
            if present:
                factors.append({"factor": name, "adjustment": adjustment})

        factor("runtime_and_goal_terminal_agree", 0.18, decision == "complete" and bool(progress.get("complete")))
        factor("explicit_next_runtime_request", 0.16, decision == "continue" and bool(progress.get("next_runtime_request")))
        factor("remaining_tasks_identified", 0.08, decision == "continue" and bool(progress.get("remaining_tasks")))
        factor("recoverable_failure_marker", 0.16, decision == "replan" and bool(progress.get("recoverable_failure")))
        factor("blocking_signal", 0.18, decision == "blocked" and bool(progress.get("blocking_failure")))
        factor("root_cause_available", 0.08, decision in {"blocked", "replan"} and bool(progress.get("root_cause")))
        factor("limited_evidence", -0.12, len(evidence_chain) < 2)
        score = _clamp_confidence(base + sum(float(item["adjustment"]) for item in factors))
        record = {
            "schema": ENGINEERING_ADAPTIVE_CONFIDENCE_SCHEMA,
            "score": score,
            "level": "high" if score >= 0.85 else "medium" if score >= 0.65 else "low",
            "factors": factors,
            "evidence_count": len(evidence_chain),
        }
        goal_lineage = _goal_lineage(progress)
        return _attach_lineage(record, goal_lineage) if goal_lineage else record

    def _build_decision_reasoning(
        self,
        *,
        decision: str,
        reason: str,
        progress: Mapping[str, Any],
        confidence_score: Mapping[str, Any],
    ) -> dict[str, Any]:
        record = {
            "selected": decision,
            "reason": reason,
            "facts": {
                "runtime_ok": bool(progress.get("runtime_ok")),
                "runtime_state": _clean_text(progress.get("runtime_state")),
                "goal_state": _clean_text(progress.get("goal_state")),
                "remaining_task_count": len(_as_list(progress.get("remaining_tasks"))),
                "failed_task_count": len(_as_list(progress.get("failed_tasks"))),
                "blocked_task_count": len(_as_list(progress.get("blocked_tasks"))),
            },
            "ruled_out": [
                candidate for candidate in ("complete", "continue", "replan", "blocked") if candidate != decision
            ],
            "confidence_level": _clean_text(confidence_score.get("level")),
        }
        goal_lineage = _goal_lineage(progress)
        return _attach_lineage(record, goal_lineage) if goal_lineage else record

    def _build_root_cause_report(
        self,
        *,
        progress: Mapping[str, Any],
        reason: str,
        decision: str,
    ) -> dict[str, Any]:
        root_cause = _as_mapping(progress.get("root_cause"))
        blocked_tasks = _as_list(progress.get("blocked_tasks"))
        failed_tasks = _as_list(progress.get("failed_tasks"))
        blocking_issues = _as_list(progress.get("blocking_issues"))
        primary_cause = _clean_text(
            root_cause.get("stop_reason") or root_cause.get("reason") or reason,
            "blocking_issue_or_unrecoverable_failure" if decision == "blocked" else "recoverable_runtime_failure",
        )
        record = {
            "schema": ENGINEERING_BLOCKED_ROOT_CAUSE_SCHEMA,
            "classification": "blocked" if decision == "blocked" else "recoverable",
            "primary_cause": primary_cause,
            "affected_tasks": copy.deepcopy(blocked_tasks or failed_tasks),
            "blocking_issues": copy.deepcopy(blocking_issues),
            "runtime_root_cause": copy.deepcopy(root_cause),
            "recommended_action": "stop_and_report" if decision == "blocked" else "revise_plan",
            "evidence_ids": [
                item["evidence_id"]
                for item in _as_list(progress.get("evidence_chain"))
                if isinstance(item, Mapping) and decision in _as_list(item.get("supports"))
            ],
        }
        goal_lineage = _goal_lineage(progress)
        return _attach_lineage(record, goal_lineage) if goal_lineage else record

    def _latest_lifecycle(self, runtime_result: Mapping[str, Any]) -> dict[str, Any]:
        iterations = _as_list(runtime_result.get("iterations"))
        for item in reversed(iterations):
            if not isinstance(item, Mapping):
                continue
            continuation = _as_mapping(item.get("continuation_result"))
            lifecycle = _as_mapping(continuation.get("goal_lifecycle") or continuation.get("engineering_goal_lifecycle"))
            if lifecycle:
                return lifecycle
            planning = _as_mapping(item.get("planning_result"))
            lifecycle = _as_mapping(planning.get("goal_lifecycle") or planning.get("engineering_goal_lifecycle"))
            if lifecycle:
                return lifecycle
            lifecycle_result = _as_mapping(item.get("lifecycle_result"))
            lifecycle = _as_mapping(lifecycle_result.get("goal_lifecycle"))
            if lifecycle:
                return lifecycle
        return {}

    def _next_runtime_request(self, runtime_result: Mapping[str, Any]) -> dict[str, Any]:
        direct = _as_mapping(runtime_result.get("next_runtime_request"))
        if direct:
            return direct
        iterations = _as_list(runtime_result.get("iterations"))
        for item in reversed(iterations):
            if not isinstance(item, Mapping):
                continue
            for container_key in ("continuation_result", "planning_result", "lifecycle_result"):
                container = _as_mapping(item.get(container_key))
                request = _as_mapping(container.get("next_runtime_request"))
                if request:
                    return request
        return {}

    def _next_action_for_decision(self, decision: str) -> str:
        return {
            "complete": "",
            "continue": "create_continuation_work_item",
            "replan": "create_replan_record",
            "blocked": "stop_with_root_cause",
        }.get(decision, "stop_with_root_cause")


__all__ = [
    "ALLOWED_ADAPTIVE_DECISIONS",
    "ENGINEERING_ADAPTIVE_DECISION_SCHEMA",
    "ENGINEERING_ADAPTIVE_EVIDENCE_SCHEMA",
    "ENGINEERING_ADAPTIVE_CONFIDENCE_SCHEMA",
    "ENGINEERING_ADAPTIVE_PLANNER_SCHEMA",
    "ENGINEERING_BLOCKED_ROOT_CAUSE_SCHEMA",
    "ENGINEERING_CONTINUATION_PLAN_SCHEMA",
    "ENGINEERING_REPLAN_REQUEST_SCHEMA",
    "EngineeringAdaptivePlanner",
    "normalize_adaptive_decision",
]
