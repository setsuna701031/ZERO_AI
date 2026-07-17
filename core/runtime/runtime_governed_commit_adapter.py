from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


GOVERNED_COMMIT_RECORD_SCHEMA = "zero.runtime.governed_commit_record.v1"


_REQUIRED_TRUE_FIELDS = (
    "validation_passed",
    "commit_allowed",
    "controlled_mutation",
    "mutation_allowed",
    "rollback_available",
    "real_executor_enabled",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    return value is True


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return copy.deepcopy(value)
    if value in (None, ""):
        return []
    return [copy.deepcopy(value)]


def _json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


@dataclass(frozen=True)
class RuntimeGovernedCommitAdapter:
    report_root: Path | str

    def apply_governed_commit(
        self,
        *,
        runtime_result: Mapping[str, Any],
        package_id: str,
        task_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        missing = [
            field
            for field in _REQUIRED_TRUE_FIELDS
            if _bool(runtime_result.get(field)) is not True
        ]

        if missing:
            return {
                "adapter_status": "blocked",
                "commit_applied": False,
                "commit_recorded": False,
                "git_diff_recorded": False,
                "governed_commit_adapter_attached": True,
                "runtime_commit_apply_status": "blocked_by_governed_commit_adapter",
                "denial_reason": "governed_commit_adapter_blocked",
                "blocked_reasons": [f"{field}_required" for field in missing],
                "record_path": "",
            }

        report_root = Path(self.report_root)
        record_path = report_root / "governed_commit_record.json"

        record = {
            "schema": GOVERNED_COMMIT_RECORD_SCHEMA,
            "package_id": _text(package_id),
            "task_id": _text(task_id),
            "run_id": _text(run_id),
            "adapter_status": "governed_recorded",
            "commit_applied": True,
            "commit_recorded": True,
            "git_diff_recorded": True,
            "validation_passed": True,
            "commit_allowed": True,
            "mutation_allowed": True,
            "controlled_mutation": True,
            "rollback_available": True,
            "real_executor_enabled": True,
            "non_mainline_issues": _safe_list(
                runtime_result.get("non_mainline_issues")
            ),
            "evidence_files": _safe_list(runtime_result.get("evidence_files")),
            "runtime_commit_apply_status": "governed_commit_recorded",
        }

        _json_write(record_path, record)

        return {
            "adapter_status": "governed_recorded",
            "commit_applied": True,
            "commit_recorded": True,
            "git_diff_recorded": True,
            "governed_commit_adapter_attached": True,
            "runtime_commit_apply_status": "governed_commit_recorded",
            "denial_reason": "",
            "record_path": str(record_path),
            "record": record,
        }


__all__ = [
    "GOVERNED_COMMIT_RECORD_SCHEMA",
    "RuntimeGovernedCommitAdapter",
]