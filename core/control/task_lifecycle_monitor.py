from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List

from core.control.task_lifecycle_models import TaskLifecycleSnapshot


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping_sources(task: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    nested_keys = (
        "result",
        "last_result",
        "last_step_result",
        "runtime_state",
        "result_bundle",
        "last_result_bundle",
        "work_package_result",
        "verification_result",
        "adaptive_decision",
        "adaptive_planning_record",
    )
    pending = [task]
    seen: set[int] = set()
    while pending:
        source = pending.pop(0)
        identity = id(source)
        if identity in seen:
            continue
        seen.add(identity)
        yield source

        for key in nested_keys:
            value = source.get(key)
            if isinstance(value, dict):
                pending.append(value)
        results = source.get("results")
        if isinstance(results, list):
            pending.extend(value for value in reversed(results) if isinstance(value, dict))


def _first_value(sources: Iterable[Dict[str, Any]], keys: Iterable[str]) -> Any:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, "", [], {}):
                return copy.deepcopy(value)
    return None


def _first_text(sources: Iterable[Dict[str, Any]], keys: Iterable[str]) -> str:
    value = _first_value(sources, keys)
    return _text(value)


def _current_step(task: Dict[str, Any], sources: List[Dict[str, Any]]) -> Any:
    explicit = _first_value(sources, ("current_step", "active_step"))
    if explicit is not None:
        return explicit

    index = task.get("current_step_index")
    steps = task.get("steps")
    if isinstance(index, int) and isinstance(steps, list) and 0 <= index < len(steps):
        return copy.deepcopy(steps[index])
    return None


def _artifacts(sources: List[Dict[str, Any]]) -> List[Any]:
    collected: List[Any] = []

    def add(value: Any) -> None:
        if value in (None, "", [], {}):
            return
        item = copy.deepcopy(value)
        if item not in collected:
            collected.append(item)

    for source in sources:
        direct = source.get("artifacts")
        if isinstance(direct, list):
            for item in direct:
                add(item)
        elif direct not in (None, "", {}):
            add(direct)

        paths = source.get("artifact_paths")
        if isinstance(paths, dict):
            for name, path in paths.items():
                if path not in (None, ""):
                    add({"name": str(name), "path": copy.deepcopy(path)})
        elif isinstance(paths, list):
            for path in paths:
                add(path)

        for key in ("artifact_path", "result_path", "evidence_path", "report_path", "audit_path"):
            path = source.get(key)
            if path not in (None, ""):
                add({"name": key, "path": copy.deepcopy(path)})
    return collected


def _missing(field: str, reason: str) -> Dict[str, Any]:
    return {"field": field, "available": False, "reason": reason}


def _adaptive_decision(sources: Iterable[Dict[str, Any]]) -> Any:
    explicit = _first_value(sources, ("adaptive_decision", "decision"))
    if isinstance(explicit, dict):
        return copy.deepcopy(explicit.get("next_action") or explicit.get("decision"))
    if explicit is not None:
        return explicit
    for source in sources:
        if source.get("outcome_class") and source.get("next_action"):
            return copy.deepcopy(source["next_action"])
    return None


class TaskLifecycleMonitor:
    """Read-only projection of existing task records into lifecycle snapshots."""

    def __init__(self, task_repository: Any, decision_evidence_repository: Any | None = None) -> None:
        self.task_repository = task_repository
        self.decision_evidence_repository = decision_evidence_repository

    def inspect(self, task_id: str) -> Dict[str, Any]:
        normalized_id = _text(task_id)
        if not normalized_id:
            return {"ok": False, "task_id": "", "reason": "task_id is required"}

        get_task = getattr(self.task_repository, "get_task", None)
        if not callable(get_task):
            return {"ok": False, "task_id": normalized_id, "reason": "Task repository read boundary not available"}

        task = get_task(normalized_id)
        if not isinstance(task, dict):
            return {"ok": False, "task_id": normalized_id, "reason": "Task not found"}
        return {"ok": True, **self.snapshot(task).to_dict()}

    def snapshot(self, task: Dict[str, Any]) -> TaskLifecycleSnapshot:
        sources = list(_mapping_sources(task))
        task_id = _first_text(sources, ("task_id", "task_name", "id"))
        status = _first_text(sources, ("status",)) or "unknown"
        lifecycle_state = _first_text(sources, ("lifecycle_state", "state")) or status
        current_stage = _first_value(sources, ("current_stage", "stage"))
        current_goal = _first_text(sources, ("current_goal", "goal", "instruction", "title"))
        current_step = _current_step(task, sources)
        created_at = _first_value(sources, ("created_at",))
        updated_at = _first_value(sources, ("updated_at",))
        result_summary = _first_text(sources, ("result_summary", "final_answer", "summary", "message"))
        error_summary = _first_text(sources, ("error_summary", "last_error", "failure_message", "error"))
        issue_reports = _first_value(
            sources,
            ("issue_reports", "issue_report", "issue_summary", "non_mainline_issues_found"),
        )
        artifacts = _artifacts(sources)
        next_action = _first_value(sources, ("next_action", "recommended_action"))
        outcome_class = _first_value(sources, ("outcome_class",))
        replan_count = _first_value(sources, ("replan_count",))
        continuation_count = _first_value(sources, ("continuation_count",))
        adaptive_decision = _adaptive_decision(sources)
        decision_reason = _first_value(sources, ("decision_reason", "adaptive_reason"))
        decision_evidence = _first_value(sources, ("decision_evidence", "decision_evidence_records"))
        find_decisions = getattr(self.decision_evidence_repository, "find_by_task_id", None)
        if callable(find_decisions) and task_id:
            persisted = find_decisions(task_id)
            if persisted:
                decision_evidence = persisted

        unavailable: List[Dict[str, Any]] = []
        values = {
            "task_id": task_id,
            "status": status if status != "unknown" else None,
            "lifecycle_state": lifecycle_state if lifecycle_state != "unknown" else None,
            "current_stage": current_stage,
            "current_goal": current_goal,
            "current_step": current_step,
            "created_at": created_at,
            "updated_at": updated_at,
            "result_summary": result_summary,
            "error_summary": error_summary,
            "issue_reports": issue_reports,
            "artifacts": artifacts,
            "next_action": next_action,
            "outcome_class": outcome_class,
            "replan_count": replan_count,
            "continuation_count": continuation_count,
            "adaptive_decision": adaptive_decision,
            "decision_reason": decision_reason,
            "decision_evidence": decision_evidence,
        }
        for field, value in values.items():
            if value in (None, "", [], {}):
                unavailable.append(_missing(field, f"{field} is not present in the task repository record"))

        return TaskLifecycleSnapshot(
            task_id=task_id,
            status=status,
            lifecycle_state=lifecycle_state,
            current_stage=current_stage,
            current_goal=current_goal,
            current_step=current_step,
            created_at=created_at,
            updated_at=updated_at,
            result_summary=result_summary,
            error_summary=error_summary,
            issue_reports=issue_reports if issue_reports is not None else [],
            artifacts=artifacts,
            next_action=next_action,
            outcome_class=outcome_class,
            replan_count=replan_count,
            continuation_count=continuation_count,
            adaptive_decision=adaptive_decision,
            decision_reason=decision_reason,
            decision_evidence=decision_evidence if isinstance(decision_evidence, list) else [],
            data_completeness=unavailable,
        )


__all__ = ["TaskLifecycleMonitor"]
