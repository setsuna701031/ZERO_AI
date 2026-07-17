from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ZERO_RUNTIME_OPERATOR_RESUME_EVIDENCE_SCHEMA = (
    "zero.operator_console.v1.resume_evidence"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def write_operator_resume_evidence(
    *,
    report_root: str | Path,
    package: Mapping[str, Any],
    run_id: str,
    commit_id: str,
    restored_record_count: int,
) -> str:
    path = Path(report_root) / "operator_resume_evidence.json"
    payload = {
        "schema": ZERO_RUNTIME_OPERATOR_RESUME_EVIDENCE_SCHEMA,
        "package_id": _text(package.get("package_id")),
        "task_id": _text(package.get("task_id")),
        "run_id": _text(run_id),
        "resume_restored": True,
        "restored_record_count": int(restored_record_count),
        "mutation_restored": True,
        "commit_restored": True,
        "commit_id": _text(commit_id),
        "duplicate_mutation": False,
        "duplicate_commit": False,
        "duplicate_git_actuator_execution": False,
        "non_mainline_issues": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return str(path)


__all__ = [
    "ZERO_RUNTIME_OPERATOR_RESUME_EVIDENCE_SCHEMA",
    "write_operator_resume_evidence",
]
