from __future__ import annotations

"""Append-only persistence and query boundary for evidence records.

EvidenceRepository is deliberately not a MemoryRepository and does not own goal,
runtime, or adaptive decisions.  It stores immutable evidence events and exposes
read-only query helpers for planner/goal completion checks.
"""

import copy
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from core.evidence.evidence_chain import EvidenceChain
from core.evidence.evidence_record import EvidenceRecord
from core.evidence.evidence_validator import is_provenance_validated_evidence
from core.goals.goal_contract import clean_required_text
from core.goals.goal_lineage_contract import extract_goal_lineage


EVIDENCE_EVENT_SCHEMA = "zero.evidence_event.v1"
EVIDENCE_REPOSITORY_SCHEMA = "zero.evidence_repository.v1"


class EvidenceRepository:
    """Persist and query evidence without owning goal or runtime decisions."""

    def __init__(self, repo_root: str | Path, *, storage_path: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = Path(storage_path) if storage_path is not None else Path("runtime/evidence/evidence_records.jsonl")
        self._live_records: dict[str, EvidenceRecord] = {}
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    def add_record(self, record: EvidenceRecord | Mapping[str, Any]) -> EvidenceRecord:
        """Append an evidence record and return the normalized record."""

        evidence = self._normalize_record(record)
        event = {
            "schema": EVIDENCE_EVENT_SCHEMA,
            "event_type": "evidence_recorded",
            "payload": evidence.to_dict(),
        }
        try:
            encoded = json.dumps(event, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("evidence_record_must_be_json_serializable") from exc
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("a", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
        self._live_records[self._record_key(evidence)] = evidence
        return evidence

    def add_records(self, records: Sequence[EvidenceRecord | Mapping[str, Any]]) -> list[EvidenceRecord]:
        return [self.add_record(record) for record in records]

    def get_record(
        self,
        evidence_id: str,
        *,
        session_id: str | None = None,
        goal_lineage_id: str | None = None,
        root_goal_id: str | None = None,
    ) -> EvidenceRecord | None:
        target = clean_required_text(evidence_id, "evidence_id")
        records = [record for record in self._latest_records().values() if record.evidence_id == target]
        if session_id is not None:
            records = [record for record in records if self._session_id(record) == str(session_id)]
        if goal_lineage_id is not None:
            records = [record for record in records if self._lineage(record).get("goal_lineage_id") == str(goal_lineage_id)]
        if root_goal_id is not None:
            records = [record for record in records if self._lineage(record).get("root_goal_id") == str(root_goal_id)]
        return records[0] if len(records) == 1 else None

    def list_records(self) -> list[EvidenceRecord]:
        return list(self._latest_records().values())

    def list_by_goal(
        self,
        goal_id: str,
        *,
        session_id: str | None = None,
        goal_lineage_id: str | None = None,
        root_goal_id: str | None = None,
    ) -> list[EvidenceRecord]:
        target = clean_required_text(goal_id, "goal_id")
        return self._matching(
            lambda record: record.goal_id == target
            and (session_id is None or self._session_id(record) == str(session_id))
            and (goal_lineage_id is None or self._lineage(record).get("goal_lineage_id") == str(goal_lineage_id))
            and (root_goal_id is None or self._lineage(record).get("root_goal_id") == str(root_goal_id))
        )

    def list_by_subgoal(self, subgoal_id: str) -> list[EvidenceRecord]:
        target = clean_required_text(subgoal_id, "subgoal_id")
        return self._matching(lambda record: record.subgoal_id == target)

    def list_by_source(self, source: str) -> list[EvidenceRecord]:
        target = clean_required_text(source, "source")
        return self._matching(lambda record: record.source == target)

    def list_validated_by_goal(self, goal_id: str) -> list[EvidenceRecord]:
        return [record for record in self.list_by_goal(goal_id) if is_provenance_validated_evidence(record, goal_id=goal_id)]

    def list_validated_by_subgoal(self, subgoal_id: str) -> list[EvidenceRecord]:
        return [record for record in self.list_by_subgoal(subgoal_id) if is_provenance_validated_evidence(record)]

    def build_chain(self, goal_id: str, *, subgoal_id: str | None = None, session_id: str | None = None) -> EvidenceChain:
        records = self.list_by_goal(goal_id, session_id=session_id)
        return EvidenceChain.from_records(goal_id, records, subgoal_id=subgoal_id)

    def build_chain_from_records(
        self,
        goal_id: str,
        records: Sequence[EvidenceRecord | Mapping[str, Any]],
        *,
        subgoal_id: str | None = None,
    ) -> EvidenceChain:
        return EvidenceChain.from_records(goal_id, records, subgoal_id=subgoal_id)

    def chain_for_goal(self, goal_id: str) -> EvidenceChain:
        return self.build_chain(goal_id)

    def chain_for_subgoal(self, goal_id: str, subgoal_id: str) -> EvidenceChain:
        return self.build_chain(goal_id, subgoal_id=subgoal_id)

    def _matching(self, predicate: Callable[[EvidenceRecord], bool]) -> list[EvidenceRecord]:
        return [record for record in self._latest_records().values() if predicate(record)]

    def _latest_records(self) -> dict[str, EvidenceRecord]:
        latest: dict[str, EvidenceRecord] = {}
        for record in self._load_records():
            latest[self._record_key(record)] = record
        latest.update(self._live_records)
        return latest

    def _load_records(self) -> list[EvidenceRecord]:
        if not self.storage_path.is_file():
            return []
        records: list[EvidenceRecord] = []
        with self.storage_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid_evidence_jsonl_line:{line_number}") from exc
                if not isinstance(event, Mapping) or not isinstance(event.get("payload"), Mapping):
                    raise ValueError(f"invalid_evidence_event_line:{line_number}")
                records.append(EvidenceRecord.from_mapping(copy.deepcopy(dict(event["payload"]))))
        return records

    @staticmethod
    def _normalize_record(record: EvidenceRecord | Mapping[str, Any]) -> EvidenceRecord:
        return record if isinstance(record, EvidenceRecord) else EvidenceRecord.from_mapping(record)

    @staticmethod
    def _session_id(record: EvidenceRecord) -> str:
        metadata = record.metadata if isinstance(record.metadata, Mapping) else {}
        return str(metadata.get("session_id") or metadata.get("runtime_session_id") or "").strip()

    @staticmethod
    def _lineage(record: EvidenceRecord) -> dict[str, str]:
        return extract_goal_lineage({"goal_id": record.goal_id, "metadata": record.metadata})

    @classmethod
    def _record_key(cls, record: EvidenceRecord) -> str:
        session_id = cls._session_id(record)
        lineage_id = cls._lineage(record).get("goal_lineage_id", "")
        scope = "::".join(part for part in (session_id, lineage_id) if part)
        return f"{scope}::{record.evidence_id}" if scope else record.evidence_id


__all__ = [
    "EVIDENCE_EVENT_SCHEMA",
    "EVIDENCE_REPOSITORY_SCHEMA",
    "EvidenceRepository",
]
