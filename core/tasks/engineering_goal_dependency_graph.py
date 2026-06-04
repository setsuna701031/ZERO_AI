from __future__ import annotations

"""Dependency relationship layer for engineering goals.

EngineeringGoalDependencyGraph owns dependency records and relationship
evaluation only. It does not schedule goals, select goals, plan, execute,
persist memory, or mutate lifecycle state.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


ENGINEERING_GOAL_DEPENDENCY_GRAPH_SCHEMA = "zero.engineering_goal_dependency_graph.v1"
DEPENDENCY_RECORD_SCHEMA = "zero.engineering_goal_dependency_record.v1"
DEPENDENCY_STATUS_SCHEMA = "zero.engineering_goal_dependency_status.v1"

COMPLETED_STATUSES = {"completed"}
BLOCKING_STATUSES = {"blocked", "cancelled", "failed"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return []
    cleaned = sorted({_clean_text(value) for value in values if _clean_text(value)})
    return cleaned


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class EngineeringGoalDependencyRecord:
    """Dependency relationship metadata for one engineering goal."""

    goal_id: str
    parent_goal_ids: list[str] = field(default_factory=list)
    child_goal_ids: list[str] = field(default_factory=list)
    prerequisite_goal_ids: list[str] = field(default_factory=list)
    blocked_by_goal_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringGoalDependencyRecord":
        goal_id = _clean_text(value.get("goal_id"))
        if not goal_id:
            raise ValueError("engineering_goal_dependency_record_requires_goal_id")
        return cls(
            goal_id=goal_id,
            parent_goal_ids=_clean_list(value.get("parent_goal_ids") or value.get("parents")),
            child_goal_ids=_clean_list(value.get("child_goal_ids") or value.get("children")),
            prerequisite_goal_ids=_clean_list(value.get("prerequisite_goal_ids") or value.get("prerequisites")),
            blocked_by_goal_ids=_clean_list(value.get("blocked_by_goal_ids") or value.get("blocked_by")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": DEPENDENCY_RECORD_SCHEMA,
            "goal_id": self.goal_id,
            "parent_goal_ids": list(self.parent_goal_ids),
            "child_goal_ids": list(self.child_goal_ids),
            "prerequisite_goal_ids": list(self.prerequisite_goal_ids),
            "blocked_by_goal_ids": list(self.blocked_by_goal_ids),
        }


def _record(value: EngineeringGoalDependencyRecord | Mapping[str, Any]) -> EngineeringGoalDependencyRecord:
    if isinstance(value, EngineeringGoalDependencyRecord):
        return value
    if isinstance(value, Mapping):
        return EngineeringGoalDependencyRecord.from_mapping(value)
    raise ValueError("engineering_goal_dependency_records_must_be_mappings")


class EngineeringGoalDependencyGraph:
    """Registers and evaluates engineering goal dependency relationships."""

    def __init__(
        self,
        records: Sequence[EngineeringGoalDependencyRecord | Mapping[str, Any]] | None = None,
    ) -> None:
        self._records: dict[str, EngineeringGoalDependencyRecord] = {}
        for record in records or []:
            self.register(record)

    def register(self, record: EngineeringGoalDependencyRecord | Mapping[str, Any]) -> dict[str, Any]:
        dependency_record = _record(record)
        self._records[dependency_record.goal_id] = dependency_record
        return {
            "schema": ENGINEERING_GOAL_DEPENDENCY_GRAPH_SCHEMA,
            "ok": True,
            "action": "register_dependency_record",
            "goal_id": dependency_record.goal_id,
            "dependency_record": dependency_record.as_dict(),
            "dependency_status": self.status(),
        }

    def status(self, goal_statuses: Mapping[str, Any] | None = None) -> dict[str, Any]:
        statuses = _as_mapping(goal_statuses)
        validation = self.validate()
        cycles = self.detect_cycles()
        records = [record.as_dict() for record in self._ordered_records()]
        return {
            "schema": DEPENDENCY_STATUS_SCHEMA,
            "ok": validation["ok"] and not cycles,
            "records": records,
            "validation": validation,
            "cycles": cycles,
            "completion": self.completion_status(statuses),
            "blocked_goals": self.blocked_goals(statuses),
        }

    def validate(self) -> dict[str, Any]:
        known = set(self._records)
        errors: list[dict[str, Any]] = []
        for record in self._ordered_records():
            refs = self._refs_for(record)
            for relation, goal_ids in refs.items():
                for goal_id in goal_ids:
                    if goal_id == record.goal_id:
                        errors.append(
                            {
                                "goal_id": record.goal_id,
                                "relation": relation,
                                "referenced_goal_id": goal_id,
                                "reason": "self_dependency",
                            }
                        )
                    elif goal_id not in known:
                        errors.append(
                            {
                                "goal_id": record.goal_id,
                                "relation": relation,
                                "referenced_goal_id": goal_id,
                                "reason": "unknown_goal",
                            }
                        )
        cycles = self.detect_cycles()
        for cycle in cycles:
            errors.append(
                {
                    "goal_id": cycle[0] if cycle else "",
                    "relation": "dependency_path",
                    "referenced_goal_id": cycle[-1] if cycle else "",
                    "reason": "dependency_cycle",
                    "cycle": cycle,
                }
            )
        return {
            "schema": "zero.engineering_goal_dependency_validation.v1",
            "ok": not errors,
            "errors": errors,
        }

    def parent_child_relationships(self) -> list[dict[str, Any]]:
        relationships: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for record in self._ordered_records():
            for child_id in record.child_goal_ids:
                key = (record.goal_id, child_id)
                if key not in seen:
                    seen.add(key)
                    relationships.append({"parent_goal_id": record.goal_id, "child_goal_id": child_id})
            for parent_id in record.parent_goal_ids:
                key = (parent_id, record.goal_id)
                if key not in seen:
                    seen.add(key)
                    relationships.append({"parent_goal_id": parent_id, "child_goal_id": record.goal_id})
        return sorted(relationships, key=lambda item: (item["parent_goal_id"], item["child_goal_id"]))

    def prerequisite_status(self, goal_id: str, goal_statuses: Mapping[str, Any]) -> dict[str, Any]:
        record = self._records.get(_clean_text(goal_id))
        if record is None:
            return {
                "goal_id": _clean_text(goal_id),
                "complete": False,
                "ready": False,
                "missing_prerequisites": [],
                "blocked_by_goals": [],
                "reason": "goal_not_registered",
            }
        statuses = _as_mapping(goal_statuses)
        missing = [
            prerequisite_id
            for prerequisite_id in record.prerequisite_goal_ids
            if _clean_text(statuses.get(prerequisite_id)).lower() not in COMPLETED_STATUSES
        ]
        blockers = [
            blocked_by_id
            for blocked_by_id in record.blocked_by_goal_ids
            if _clean_text(statuses.get(blocked_by_id)).lower() not in COMPLETED_STATUSES
        ]
        return {
            "goal_id": record.goal_id,
            "complete": not missing and not blockers,
            "ready": not missing and not blockers,
            "missing_prerequisites": missing,
            "blocked_by_goals": blockers,
            "reason": "dependencies_satisfied" if not missing and not blockers else "dependencies_unsatisfied",
        }

    def blocked_goals(self, goal_statuses: Mapping[str, Any]) -> list[dict[str, Any]]:
        statuses = _as_mapping(goal_statuses)
        blocked: list[dict[str, Any]] = []
        for record in self._ordered_records():
            status = self.prerequisite_status(record.goal_id, statuses)
            explicit_blockers = [
                blocked_by_id
                for blocked_by_id in record.blocked_by_goal_ids
                if _clean_text(statuses.get(blocked_by_id)).lower() in BLOCKING_STATUSES
            ]
            if status["missing_prerequisites"] or status["blocked_by_goals"] or explicit_blockers:
                blocked.append(
                    {
                        "goal_id": record.goal_id,
                        "missing_prerequisites": status["missing_prerequisites"],
                        "blocked_by_goals": status["blocked_by_goals"],
                        "blocking_status_goals": explicit_blockers,
                    }
                )
        return blocked

    def completion_status(self, goal_statuses: Mapping[str, Any]) -> list[dict[str, Any]]:
        statuses = _as_mapping(goal_statuses)
        completion: list[dict[str, Any]] = []
        for record in self._ordered_records():
            dependency_status = self.prerequisite_status(record.goal_id, statuses)
            completion.append(
                {
                    "goal_id": record.goal_id,
                    "dependencies_complete": dependency_status["complete"],
                    "status": _clean_text(statuses.get(record.goal_id), "unknown").lower(),
                    "missing_prerequisites": dependency_status["missing_prerequisites"],
                    "blocked_by_goals": dependency_status["blocked_by_goals"],
                }
            )
        return completion

    def detect_cycles(self) -> list[list[str]]:
        adjacency = {
            record.goal_id: sorted(set(record.prerequisite_goal_ids + record.blocked_by_goal_ids + record.parent_goal_ids))
            for record in self._ordered_records()
        }
        cycles: set[tuple[str, ...]] = set()

        def visit(node: str, path: list[str]) -> None:
            if node in path:
                cycle = path[path.index(node):] + [node]
                cycles.add(self._canonical_cycle(cycle))
                return
            for next_node in adjacency.get(node, []):
                if next_node not in adjacency:
                    continue
                visit(next_node, [*path, node])

        for node in sorted(adjacency):
            visit(node, [])
        return [list(cycle) for cycle in sorted(cycles)]

    def as_dict(self, goal_statuses: Mapping[str, Any] | None = None) -> dict[str, Any]:
        status = self.status(goal_statuses)
        return {
            "schema": ENGINEERING_GOAL_DEPENDENCY_GRAPH_SCHEMA,
            "records": copy.deepcopy(status["records"]),
            "parent_child_relationships": self.parent_child_relationships(),
            "dependency_status": status,
        }

    def _ordered_records(self) -> list[EngineeringGoalDependencyRecord]:
        return [self._records[goal_id] for goal_id in sorted(self._records)]

    def _refs_for(self, record: EngineeringGoalDependencyRecord) -> dict[str, list[str]]:
        return {
            "parent_goal_ids": record.parent_goal_ids,
            "child_goal_ids": record.child_goal_ids,
            "prerequisite_goal_ids": record.prerequisite_goal_ids,
            "blocked_by_goal_ids": record.blocked_by_goal_ids,
        }

    def _canonical_cycle(self, cycle: list[str]) -> tuple[str, ...]:
        if len(cycle) <= 1:
            return tuple(cycle)
        body = cycle[:-1]
        rotations = [body[index:] + body[:index] for index in range(len(body))]
        canonical = min(rotations)
        return tuple(canonical + [canonical[0]])


__all__ = [
    "DEPENDENCY_RECORD_SCHEMA",
    "DEPENDENCY_STATUS_SCHEMA",
    "ENGINEERING_GOAL_DEPENDENCY_GRAPH_SCHEMA",
    "EngineeringGoalDependencyGraph",
    "EngineeringGoalDependencyRecord",
]
