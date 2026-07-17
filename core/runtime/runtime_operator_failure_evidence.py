from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ZERO_RUNTIME_OPERATOR_FAILURE_EVIDENCE_SCHEMA = (
    "zero.operator_console.v1.failure_evidence"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def write_operator_failure_evidence(
    *,
    report_root: str | Path,
    command: str,
    package: Mapping[str, Any],
    problems: list[str],
) -> str:
    path = Path(report_root) / "operator_failure_evidence.json"
    payload = {
        "schema": ZERO_RUNTIME_OPERATOR_FAILURE_EVIDENCE_SCHEMA,
        "command": command,
        "package_id": _text(package.get("package_id")),
        "task_id": _text(package.get("task_id")),
        "ok": False,
        "denial_reason": "invalid_package",
        "non_mainline_issues": list(problems),
        "controlled_mutation": False,
        "commit_allowed": False,
        "commit_applied": False,
        "commit_recorded": False,
        "actuator_executed": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return str(path)


__all__ = [
    "ZERO_RUNTIME_OPERATOR_FAILURE_EVIDENCE_SCHEMA",
    "write_operator_failure_evidence",
]
