from __future__ import annotations

"""Persistent reporter for non-mainline engineering issues."""

import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.tasks.engineering_issue_contract import (
    ENGINEERING_ISSUE_REPORT_SCHEMA,
    EngineeringIssueReport,
    validate_issue_reports_allow_success,
)


ENGINEERING_ISSUE_REPORTER_SCHEMA = "zero.engineering_issue_reporter.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_issue_id(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        elif char.isspace():
            safe.append("_")
    return "".join(safe).strip("._-").lower()[:80] or "issue"


class EngineeringIssueReporter:
    """Create, list, show, and persist engineering issue reports."""

    def __init__(self, repo_root: str | Path, *, storage_path: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.repo_root / "runtime" / "issues" / "issues.json"
        if not self.storage_path.is_absolute():
            self.storage_path = self.repo_root / self.storage_path

    @property
    def storage_dir(self) -> Path:
        return self.storage_path.parent

    def report_issue(self, report: Mapping[str, Any] | EngineeringIssueReport, **fields: Any) -> dict[str, Any]:
        records = self._read_records()
        raw = report.to_dict() if isinstance(report, EngineeringIssueReport) else copy.deepcopy(dict(report))
        raw.update(copy.deepcopy(dict(fields)))
        raw.setdefault("issue_id", self._new_issue_id(raw, records))
        raw.setdefault("created_at", time.time())
        issue_report = EngineeringIssueReport.from_mapping(raw)
        record = issue_report.to_dict()
        issue_id = record["issue_id"]
        if issue_id in records:
            raise ValueError(f"engineering_issue_report_already_exists:{issue_id}")
        records[issue_id] = record
        self._write_records(records)
        return copy.deepcopy(record)

    def list_issues(self) -> list[dict[str, Any]]:
        return self._ordered_records()

    def get_issue(self, issue_id: str) -> dict[str, Any] | None:
        record = self._read_records().get(_clean_text(issue_id))
        return copy.deepcopy(record) if record else None

    def delete_issue(self, issue_id: str) -> dict[str, Any]:
        target_issue_id = _clean_text(issue_id)
        records = self._read_records()
        record = records.pop(target_issue_id, None)
        if record is None:
            return {"ok": False, "issue_id": target_issue_id, "deleted": False, "reason": "issue_not_found"}
        self._write_records(records)
        return {"ok": True, "issue_id": target_issue_id, "deleted": True, "issue": copy.deepcopy(record)}

    def success_gate(self, reports: Sequence[Mapping[str, Any] | EngineeringIssueReport] | None = None) -> dict[str, Any]:
        issue_reports = list(reports) if reports is not None else self.list_issues()
        result = validate_issue_reports_allow_success(issue_reports)
        return {
            "schema": ENGINEERING_ISSUE_REPORTER_SCHEMA,
            **result,
            "updated_at": time.time(),
        }

    def build_summary(self) -> dict[str, Any]:
        issues = self.list_issues()
        risk_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        for issue in issues:
            risk = _clean_text(issue.get("risk_level"), "unknown")
            action = _clean_text(issue.get("recommended_action"), "unknown")
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
            action_counts[action] = action_counts.get(action, 0) + 1
        gate = self.success_gate(issues)
        return {
            "schema": ENGINEERING_ISSUE_REPORTER_SCHEMA,
            "ok": True,
            "issue_count": len(issues),
            "issues": issues,
            "risk_counts": risk_counts,
            "recommended_action_counts": action_counts,
            "success_allowed": bool(gate.get("success_allowed")),
            "blocking_issue_count": int(gate.get("blocking_issue_count") or 0),
            "blocking_issues": copy.deepcopy(gate.get("blocking_issues")) if isinstance(gate.get("blocking_issues"), list) else [],
            "updated_at": time.time(),
        }

    def _new_issue_id(self, raw: Mapping[str, Any], records: Mapping[str, dict[str, Any]]) -> str:
        seed_text = _clean_text(raw.get("observed_symptom") or raw.get("source_package_id"), "issue")
        seed = f"{seed_text}:{time.time_ns()}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        base = f"issue_{_safe_issue_id(seed_text)[:32]}_{digest}"
        if base not in records:
            return base
        suffix = 2
        while f"{base}_{suffix}" in records:
            suffix += 1
        return f"{base}_{suffix}"

    def _ordered_records(self) -> list[dict[str, Any]]:
        return [
            copy.deepcopy(record)
            for record in sorted(
                self._read_records().values(),
                key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("issue_id"))),
            )
        ]

    def _read_records(self) -> dict[str, dict[str, Any]]:
        if not self.storage_path.is_file():
            return {}
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        issues = data if isinstance(data, list) else data.get("issues") if isinstance(data, Mapping) else []
        records: dict[str, dict[str, Any]] = {}
        if isinstance(issues, list):
            for item in issues:
                if not isinstance(item, Mapping):
                    continue
                try:
                    record = EngineeringIssueReport.from_mapping(item).to_dict()
                except ValueError:
                    continue
                records[record["issue_id"]] = record
        return records

    def _write_records(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": ENGINEERING_ISSUE_REPORTER_SCHEMA,
            "record_schema": ENGINEERING_ISSUE_REPORT_SCHEMA,
            "issues": [
                copy.deepcopy(dict(record))
                for record in sorted(
                    records.values(),
                    key=lambda item: (_as_float(item.get("created_at")), _clean_text(item.get("issue_id"))),
                )
            ],
            "updated_at": time.time(),
        }
        self.storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


__all__ = [
    "ENGINEERING_ISSUE_REPORTER_SCHEMA",
    "EngineeringIssueReporter",
]
