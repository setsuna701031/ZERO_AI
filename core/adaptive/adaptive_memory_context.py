from __future__ import annotations

"""Read-only memory context for adaptive replanning input."""

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from core.adaptive.adaptive_contract import DeviationReport
from core.memory.memory_query import MemoryQuery
from core.memory.memory_repository import MemoryRepository


ADAPTIVE_MEMORY_CONTEXT_SCHEMA = "zero.adaptive.memory_context.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _evidence_refs(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class AdaptiveMemoryContextItem:
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
class AdaptiveMemoryPolicy:
    max_related_issues: int = 5
    max_related_decisions: int = 5
    max_engineering_events: int = 5
    allow_issue_memory: bool = True
    allow_decision_memory: bool = True
    allow_engineering_memory: bool = True


@dataclass(frozen=True)
class AdaptiveMemoryContext:
    task_id: str
    step_id: str
    deviation_reason: str
    related_issues: list[AdaptiveMemoryContextItem] = field(default_factory=list)
    related_decisions: list[AdaptiveMemoryContextItem] = field(default_factory=list)
    related_engineering_events: list[AdaptiveMemoryContextItem] = field(default_factory=list)
    evidence_refs: list[Any] = field(default_factory=list)
    generated_at: str = field(default_factory=_now)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_MEMORY_CONTEXT_SCHEMA,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "deviation_reason": self.deviation_reason,
            "related_issues": [item.to_dict() for item in self.related_issues],
            "related_decisions": [item.to_dict() for item in self.related_decisions],
            "related_engineering_events": [item.to_dict() for item in self.related_engineering_events],
            "evidence_refs": copy.deepcopy(self.evidence_refs),
            "generated_at": self.generated_at,
            "warnings": list(self.warnings),
        }


class AdaptiveMemoryContextBuilder:
    """Query historical memory without changing deviation or decision contracts."""

    def __init__(
        self,
        repository: MemoryRepository | None = None,
        *,
        query: MemoryQuery | None = None,
        policy: AdaptiveMemoryPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.query = query or (MemoryQuery(repository) if repository is not None else None)
        self.policy = policy or AdaptiveMemoryPolicy()

    def build(self, report: DeviationReport | Mapping[str, Any]) -> AdaptiveMemoryContext:
        source = report.to_dict() if isinstance(report, DeviationReport) else copy.deepcopy(dict(report))
        task_id = _text(source.get("task_id"))
        step_id = _text(source.get("step_id"))
        reason = _text(source.get("reason"))
        if self.query is None:
            return AdaptiveMemoryContext(task_id, step_id, reason)
        try:
            issues = self._issue_items(task_id, reason, source.get("observed"))
            decisions = self._decision_items(task_id)
            events = self._engineering_items(task_id, reason)
            return AdaptiveMemoryContext(
                task_id=task_id,
                step_id=step_id,
                deviation_reason=reason,
                related_issues=issues,
                related_decisions=decisions,
                related_engineering_events=events,
                evidence_refs=self._collect_evidence(issues, decisions, events),
            )
        except Exception as exc:
            return AdaptiveMemoryContext(
                task_id,
                step_id,
                reason,
                warnings=[f"adaptive_memory_context_query_failed:{type(exc).__name__}:{exc}"],
            )

    def _issue_items(self, task_id: str, reason: str, observed: Any) -> list[AdaptiveMemoryContextItem]:
        if not self.policy.allow_issue_memory:
            return []
        records = self.query.find_related_issues(task_id or None)
        relevance = "same_task_id"
        if not records:
            search_text = self._issue_search_text(reason, observed)
            records = self.query.find_related_issues(text=search_text or None)
            relevance = "deviation_text_match"
        return self._limited(
            [
                self._item(
                    record,
                    title=_text(record.get("title")) or "related issue",
                    summary=_text(record.get("root_cause")) or "root cause unavailable",
                    relevance_reason=relevance,
                )
                for record in records
            ],
            self.policy.max_related_issues,
        )

    def _decision_items(self, task_id: str) -> list[AdaptiveMemoryContextItem]:
        if not self.policy.allow_decision_memory:
            return []
        records = self.query.find_previous_decisions(task_id) if task_id else []
        return self._limited(
            [
                self._item(
                    record,
                    title=_text(record.get("decision")) or "previous decision",
                    summary=_text(record.get("reason")) or "decision reason unavailable",
                    relevance_reason="same_task_id",
                )
                for record in records
            ],
            self.policy.max_related_decisions,
        )

    def _engineering_items(self, task_id: str, reason: str) -> list[AdaptiveMemoryContextItem]:
        if not self.policy.allow_engineering_memory:
            return []
        records = self.query.find_engineering_events(task_id or None)
        relevance = "same_task_id"
        if not records and reason:
            records = self.query.find_engineering_events(text=reason)
            relevance = "deviation_text_match"
        return self._limited(
            [
                self._item(
                    record,
                    title=_text(record.get("title")) or "engineering event",
                    summary=_text(record.get("description")) or "event description unavailable",
                    relevance_reason=relevance,
                )
                for record in records
            ],
            self.policy.max_engineering_events,
        )

    @staticmethod
    def _issue_search_text(reason: str, observed: Any) -> str:
        if isinstance(observed, Mapping):
            missing = observed.get("missing_artifacts")
            if isinstance(missing, list) and missing:
                return _text(missing[0])
        return reason

    @staticmethod
    def _limited(items: list[AdaptiveMemoryContextItem], limit: int) -> list[AdaptiveMemoryContextItem]:
        return items[-limit:] if limit > 0 else []

    @staticmethod
    def _item(
        record: Mapping[str, Any],
        *,
        title: str,
        summary: str,
        relevance_reason: str,
    ) -> AdaptiveMemoryContextItem:
        return AdaptiveMemoryContextItem(
            memory_id=_text(record.get("record_id")),
            memory_type=_text(record.get("memory_type")),
            title=title,
            summary=summary,
            relevance_reason=relevance_reason,
            evidence_refs=_evidence_refs(record.get("evidence_refs")),
        )

    @staticmethod
    def _collect_evidence(*groups: list[AdaptiveMemoryContextItem]) -> list[Any]:
        evidence_refs: list[Any] = []
        for group in groups:
            for item in group:
                for evidence in item.evidence_refs:
                    if evidence not in evidence_refs:
                        evidence_refs.append(copy.deepcopy(evidence))
        return evidence_refs


__all__ = [
    "ADAPTIVE_MEMORY_CONTEXT_SCHEMA",
    "AdaptiveMemoryContext",
    "AdaptiveMemoryContextBuilder",
    "AdaptiveMemoryContextItem",
    "AdaptiveMemoryPolicy",
]
