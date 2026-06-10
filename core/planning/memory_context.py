from __future__ import annotations

"""Read-only memory context contracts and deterministic context assembly."""

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from core.memory.memory_query import MemoryQuery
from core.memory.memory_repository import MemoryRepository


MEMORY_CONTEXT_SCHEMA = "zero.planning.memory_context.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _evidence_refs(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class MemoryContextItem:
    memory_id: str
    memory_type: str
    title: str
    summary: str
    relevance_reason: str
    evidence_refs: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "memory_type": self.memory_type,
            "title": self.title,
            "summary": self.summary,
            "relevance_reason": self.relevance_reason,
            "evidence_refs": copy.deepcopy(self.evidence_refs),
        }


@dataclass(frozen=True)
class PlannerMemoryPolicy:
    max_related_tasks: int = 5
    max_related_decisions: int = 5
    max_related_issues: int = 5
    max_engineering_events: int = 5
    allow_issue_memory: bool = True
    allow_decision_memory: bool = True
    allow_engineering_memory: bool = True


@dataclass(frozen=True)
class MemoryContext:
    task_id: str
    goal: str
    related_tasks: list[MemoryContextItem] = field(default_factory=list)
    related_decisions: list[MemoryContextItem] = field(default_factory=list)
    related_issues: list[MemoryContextItem] = field(default_factory=list)
    related_engineering_events: list[MemoryContextItem] = field(default_factory=list)
    evidence_refs: list[Any] = field(default_factory=list)
    generated_at: str = field(default_factory=_now)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEMORY_CONTEXT_SCHEMA,
            "task_id": self.task_id,
            "goal": self.goal,
            "related_tasks": [item.to_dict() for item in self.related_tasks],
            "related_decisions": [item.to_dict() for item in self.related_decisions],
            "related_issues": [item.to_dict() for item in self.related_issues],
            "related_engineering_events": [item.to_dict() for item in self.related_engineering_events],
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "generated_at": self.generated_at,
            "warnings": list(self.warnings),
        }


class MemoryContextBuilder:
    """Build planner input context without writing memory or making decisions."""

    def __init__(
        self,
        repository: MemoryRepository | None = None,
        *,
        query: MemoryQuery | None = None,
        policy: PlannerMemoryPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.query = query or (MemoryQuery(repository) if repository is not None else None)
        self.policy = policy or PlannerMemoryPolicy()

    def build(self, *, task_id: str = "", goal: str = "") -> MemoryContext:
        task_id = _text(task_id)
        goal = _text(goal)
        if self.query is None:
            return MemoryContext(task_id=task_id, goal=goal)
        try:
            tasks = self._task_items(task_id, goal)
            decisions = self._decision_items(task_id)
            issues = self._issue_items(task_id, goal)
            events = self._engineering_items(task_id, goal)
            return MemoryContext(
                task_id=task_id,
                goal=goal,
                related_tasks=tasks,
                related_decisions=decisions,
                related_issues=issues,
                related_engineering_events=events,
                evidence_refs=self._collect_evidence(tasks, decisions, issues, events),
            )
        except Exception as exc:
            return MemoryContext(
                task_id=task_id,
                goal=goal,
                warnings=[f"memory_context_query_failed:{type(exc).__name__}:{exc}"],
            )

    def _task_items(self, task_id: str, goal: str) -> list[MemoryContextItem]:
        records = self.query.find_task_history(task_id) if task_id else []
        if not records and goal and self.repository is not None:
            records = [
                record
                for record in self.repository.list_by_type("task")
                if _text(record.get("goal")).casefold() == goal.casefold()
            ]
        return self._limited([
            self._item(
                record,
                title=_text(record.get("goal")) or "task history",
                summary=_text(record.get("result")) or "task result unavailable",
                reason="same_task_id" if task_id else "same_goal",
            )
            for record in records
        ], self.policy.max_related_tasks)

    def _decision_items(self, task_id: str) -> list[MemoryContextItem]:
        if not self.policy.allow_decision_memory:
            return []
        records = self.query.find_previous_decisions(task_id) if task_id else []
        return self._limited([
            self._item(
                record,
                title=_text(record.get("decision")) or "previous decision",
                summary=_text(record.get("reason")) or "decision reason unavailable",
                reason="same_task_id",
            )
            for record in records
        ], self.policy.max_related_decisions)

    def _issue_items(self, task_id: str, goal: str) -> list[MemoryContextItem]:
        if not self.policy.allow_issue_memory:
            return []
        records = self.query.find_related_issues(task_id or None, text=None if task_id else goal or None)
        return self._limited([
            self._item(
                record,
                title=_text(record.get("title")) or "related issue",
                summary=_text(record.get("root_cause")) or "root cause unavailable",
                reason="same_task_id" if task_id else "goal_text_match",
            )
            for record in records
        ], self.policy.max_related_issues)

    def _engineering_items(self, task_id: str, goal: str) -> list[MemoryContextItem]:
        if not self.policy.allow_engineering_memory:
            return []
        records = self.query.find_engineering_events(task_id or None, text=None if task_id else goal or None)
        return self._limited([
            self._item(
                record,
                title=_text(record.get("title")) or "engineering event",
                summary=_text(record.get("description")) or "event description unavailable",
                reason="same_task_id" if task_id else "goal_text_match",
            )
            for record in records
        ], self.policy.max_engineering_events)

    @staticmethod
    def _limited(items: list[MemoryContextItem], limit: int) -> list[MemoryContextItem]:
        return items[-limit:] if limit > 0 else []

    @staticmethod
    def _item(
        record: Mapping[str, Any],
        *,
        title: str,
        summary: str,
        reason: str,
    ) -> MemoryContextItem:
        return MemoryContextItem(
            memory_id=_text(record.get("record_id")),
            memory_type=_text(record.get("memory_type")),
            title=title,
            summary=summary,
            relevance_reason=reason,
            evidence_refs=_evidence_refs(record.get("evidence_refs")),
        )

    @staticmethod
    def _collect_evidence(*groups: list[MemoryContextItem]) -> list[Any]:
        collected: list[Any] = []
        for group in groups:
            for item in group:
                for evidence in item.evidence_refs:
                    if evidence not in collected:
                        collected.append(copy.deepcopy(evidence))
        return collected


__all__ = [
    "MEMORY_CONTEXT_SCHEMA",
    "MemoryContext",
    "MemoryContextBuilder",
    "MemoryContextItem",
    "PlannerMemoryPolicy",
]
