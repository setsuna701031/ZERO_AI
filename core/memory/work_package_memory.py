from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


WORK_PACKAGE_MEMORY_SCHEMA = "zero.memory.work_package.v1"
WORK_PACKAGE_MEMORY_TERMINAL_STATES = frozenset(
    {"completed", "blocked", "failed", "cancelled"}
)
GENERIC_MEMORY_TOKENS = frozenset(
    {
        "behavior",
        "context",
        "engineering",
        "evidence",
        "experience",
        "future",
        "lifecycle",
        "memory",
        "package",
        "planning",
        "preserve",
        "repair",
        "runtime",
        "scheduler",
        "workpackage",
    }
)


class WorkPackageMemoryError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(*values: Any) -> set[str]:
    text = " ".join(str(value or "") for value in values).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9_./-]{3,}", text)
        if token and token not in GENERIC_MEMORY_TOKENS
    }


def _list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _collect_modified_files(record: Mapping[str, Any]) -> list[str]:
    found = {str(item) for item in record.get("target_files") or [] if str(item)}

    def visit(value: Any, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {"changed_files", "modified_files"} and isinstance(item, list):
                    found.update(str(path) for path in item if str(path))
                elif key in {"path", "file_path", "target_path"} and isinstance(item, str):
                    found.add(item)
                else:
                    visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, depth + 1)

    visit(record.get("execution_evidence"))
    return sorted(found)


def _evidence_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _list(record.get("execution_evidence"))
    replan_history = _list(record.get("replan_history"))
    return {
        "evidence_count": len(evidence),
        "successful_steps": sum(1 for item in evidence if isinstance(item, Mapping) and item.get("ok")),
        "failed_steps": sum(1 for item in evidence if isinstance(item, Mapping) and item.get("ok") is False),
        "step_indexes": [
            item.get("step_index") for item in evidence if isinstance(item, Mapping)
        ],
        "replan_count": len(replan_history),
        "replan_request_ids": [
            item.get("request_id") for item in replan_history if isinstance(item, Mapping)
        ],
        "replan_appended_steps": sum(
            int(item.get("appended_step_count") or 0)
            for item in replan_history
            if isinstance(item, Mapping)
        ),
    }


def _test_result_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    progress = _mapping(record.get("progress"))
    validation = progress.get("validation_summary")
    return {
        "validation_commands": _list(record.get("validation_commands")),
        "validation_summary": copy.deepcopy(validation),
        "completed_steps": int(progress.get("completed_steps") or 0),
        "failed_steps": int(progress.get("failed_steps") or 0),
    }


@dataclass(frozen=True)
class WorkPackageMemoryRecord:
    memory_record_id: str
    package_id: str
    session_id: str
    task_id: str
    original_objective: dict[str, Any]
    planning_snapshot: dict[str, Any]
    task_graph_summary: dict[str, Any]
    runtime_lifecycle_history: list[dict[str, Any]]
    execution_evidence_summary: dict[str, Any]
    final_status: str
    root_cause: str
    warnings: list[Any]
    errors: list[Any]
    non_mainline_findings: list[Any]
    modified_files_summary: list[str]
    test_result_summary: dict[str, Any]
    committed_at: str
    schema: str = WORK_PACKAGE_MEMORY_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.__dict__)

    @classmethod
    def from_runtime_record(cls, record: Mapping[str, Any]) -> "WorkPackageMemoryRecord":
        final_status = str(record.get("status") or "").lower()
        if final_status not in WORK_PACKAGE_MEMORY_TERMINAL_STATES:
            raise WorkPackageMemoryError(f"final_memory_requires_terminal_state:{final_status}")
        package_id = str(record.get("package_id") or "")
        session_id = str(record.get("session_id") or "")
        task_id = str(record.get("task_id") or "")
        if not package_id or not session_id or not task_id:
            raise WorkPackageMemoryError("work_package_memory_identity_required")
        planning = _mapping(record.get("planning_snapshot"))
        progress = _mapping(record.get("progress"))
        record_id = "wpm-" + hashlib.sha256(
            f"{package_id}:{session_id}:{task_id}:{final_status}".encode("utf-8")
        ).hexdigest()[:20]
        return cls(
            memory_record_id=record_id,
            package_id=package_id,
            session_id=session_id,
            task_id=task_id,
            original_objective={
                "title": str(record.get("title") or ""),
                "goal": str(record.get("goal") or ""),
                "description": str(record.get("description") or ""),
                "requirements": _list(record.get("requirements")),
                "target_files": _list(record.get("target_files")),
            },
            planning_snapshot=planning,
            task_graph_summary=_mapping(record.get("task_graph_summary")),
            runtime_lifecycle_history=_list(record.get("runtime_lifecycle_history")),
            execution_evidence_summary=_evidence_summary(record),
            final_status=final_status,
            root_cause=str(record.get("root_cause") or record.get("blocked_reason") or ""),
            warnings=[*_list(record.get("warnings")), *_list(planning.get("warnings"))],
            errors=_list(planning.get("errors")),
            non_mainline_findings=_list(progress.get("non_mainline_findings")),
            modified_files_summary=_collect_modified_files(record),
            test_result_summary=_test_result_summary(record),
            committed_at=_now(),
        )


class WorkPackageMemoryStore:
    """Persistent WorkPackage experience store. It exposes context, never execution control."""

    def __init__(self, root: str | Path = "workspace/work_package_memory") -> None:
        self.root = Path(root)
        self.records_dir = self.root / "records"

    def _path(self, memory_record_id: str) -> Path:
        return self.records_dir / f"{memory_record_id}.json"

    def commit_terminal(self, runtime_record: Mapping[str, Any]) -> dict[str, Any]:
        memory = WorkPackageMemoryRecord.from_runtime_record(runtime_record)
        payload = memory.to_dict()
        json.dumps(payload, ensure_ascii=False)
        path = self._path(memory.memory_record_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return payload

    def get_for_package(self, package_id: str) -> dict[str, Any] | None:
        matches = [
            item
            for item in self.list_records()
            if str(item.get("package_id") or "") == str(package_id or "")
        ]
        matches.sort(key=lambda item: str(item.get("committed_at") or ""))
        return matches[-1] if matches else None

    def list_records(self) -> list[dict[str, Any]]:
        if not self.records_dir.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.records_dir.glob("*.json"))
        ]

    def query_related(
        self,
        *,
        objective: str,
        target_files: list[str] | tuple[str, ...],
        failure_type: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        query_tokens = _tokens(objective, *target_files, failure_type)
        query_files = {str(item).replace("\\", "/").lower() for item in target_files if str(item)}
        failure_tokens = _tokens(failure_type)
        ranked: list[tuple[int, str, dict[str, Any]]] = []
        for record in self.list_records():
            objective_payload = _mapping(record.get("original_objective"))
            record_tokens = _tokens(
                objective_payload.get("goal"),
                objective_payload.get("description"),
                *(_list(objective_payload.get("target_files"))),
                *(_list(record.get("modified_files_summary"))),
                record.get("root_cause"),
                record.get("final_status"),
            )
            record_files = {
                str(item).replace("\\", "/").lower()
                for item in [
                    *_list(objective_payload.get("target_files")),
                    *_list(record.get("modified_files_summary")),
                ]
                if str(item)
            }
            file_score = 20 * len(query_files & record_files)
            failure_score = 10 * len(failure_tokens & _tokens(record.get("root_cause")))
            objective_score = len(query_tokens & record_tokens)
            score = file_score + failure_score + objective_score
            if file_score <= 0 and failure_score <= 0 and objective_score < 3:
                continue
            context = {
                "memory_record_id": record.get("memory_record_id"),
                "package_id": record.get("package_id"),
                "task_id": record.get("task_id"),
                "final_status": record.get("final_status"),
                "root_cause": record.get("root_cause"),
                "task_graph_summary": copy.deepcopy(record.get("task_graph_summary") or {}),
                "execution_evidence_summary": copy.deepcopy(
                    record.get("execution_evidence_summary") or {}
                ),
                "modified_files_summary": _list(record.get("modified_files_summary")),
                "test_result_summary": copy.deepcopy(record.get("test_result_summary") or {}),
                "relevance_score": score,
            }
            ranked.append((score, str(record.get("committed_at") or ""), context))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked[: max(0, int(limit))]]


__all__ = [
    "WORK_PACKAGE_MEMORY_SCHEMA",
    "WORK_PACKAGE_MEMORY_TERMINAL_STATES",
    "WorkPackageMemoryError",
    "WorkPackageMemoryRecord",
    "WorkPackageMemoryStore",
]
