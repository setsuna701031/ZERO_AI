from __future__ import annotations

"""Data contract for non-mainline engineering issue reports."""

import copy
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


ENGINEERING_ISSUE_REPORT_SCHEMA = "zero.engineering_issue_report.v1"

RISK_LEVELS = {"low", "medium", "high"}
RECOMMENDED_ACTIONS = {"fix_now", "queue_for_next_package", "ignore_with_reason"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_bool(value: Any) -> bool:
    return bool(value)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_file_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    files: list[str] = []
    seen: set[str] = set()
    for item in value:
        file_path = _clean_text(item)
        if file_path and file_path not in seen:
            files.append(file_path)
            seen.add(file_path)
    return files


def _reason_is_only_not_in_scope(reason: str) -> bool:
    normalized = " ".join(reason.lower().replace("-", " ").replace("_", " ").split())
    return normalized in {"not in scope", "out of scope", "not scope", "outside scope"}


@dataclass(frozen=True)
class EngineeringIssueReport:
    issue_id: str
    source_package_id: str
    affected_files: list[str]
    observed_symptom: str
    root_cause_hypothesis: str
    risk_level: str
    blocks_current_task: bool
    recommended_action: str
    reason_if_not_fixed_now: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        object.__setattr__(self, "issue_id", _clean_text(self.issue_id))
        object.__setattr__(self, "source_package_id", _clean_text(self.source_package_id))
        object.__setattr__(self, "affected_files", _as_file_list(self.affected_files))
        object.__setattr__(self, "observed_symptom", _clean_text(self.observed_symptom))
        object.__setattr__(self, "root_cause_hypothesis", _clean_text(self.root_cause_hypothesis))
        object.__setattr__(self, "risk_level", _clean_text(self.risk_level).lower())
        object.__setattr__(self, "blocks_current_task", _as_bool(self.blocks_current_task))
        object.__setattr__(self, "recommended_action", _clean_text(self.recommended_action).lower())
        object.__setattr__(self, "reason_if_not_fixed_now", _clean_text(self.reason_if_not_fixed_now))
        object.__setattr__(self, "created_at", _as_float(self.created_at, time.time()))
        self.validate()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EngineeringIssueReport":
        return cls(
            issue_id=_clean_text(value.get("issue_id") or value.get("id")),
            source_package_id=_clean_text(value.get("source_package_id")),
            affected_files=_as_file_list(value.get("affected_files")),
            observed_symptom=_clean_text(value.get("observed_symptom")),
            root_cause_hypothesis=_clean_text(value.get("root_cause_hypothesis")),
            risk_level=_clean_text(value.get("risk_level")),
            blocks_current_task=_as_bool(value.get("blocks_current_task")),
            recommended_action=_clean_text(value.get("recommended_action")),
            reason_if_not_fixed_now=_clean_text(value.get("reason_if_not_fixed_now")),
            created_at=_as_float(value.get("created_at"), time.time()),
        )

    def validate(self) -> None:
        missing = [
            field_name
            for field_name, value in (
                ("issue_id", self.issue_id),
                ("source_package_id", self.source_package_id),
                ("observed_symptom", self.observed_symptom),
                ("root_cause_hypothesis", self.root_cause_hypothesis),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"engineering_issue_report_missing_required:{','.join(missing)}")
        if not self.affected_files:
            raise ValueError("engineering_issue_report_requires_affected_files")
        if self.risk_level not in RISK_LEVELS:
            raise ValueError(f"engineering_issue_report_invalid_risk_level:{self.risk_level}")
        if self.recommended_action not in RECOMMENDED_ACTIONS:
            raise ValueError(f"engineering_issue_report_invalid_recommended_action:{self.recommended_action}")
        if self.recommended_action != "fix_now" and not self.reason_if_not_fixed_now:
            raise ValueError("engineering_issue_report_requires_reason_if_not_fixed_now")
        if self.recommended_action == "ignore_with_reason" and not self.reason_if_not_fixed_now:
            raise ValueError("engineering_issue_report_ignore_requires_reason")
        if self.reason_if_not_fixed_now and _reason_is_only_not_in_scope(self.reason_if_not_fixed_now):
            raise ValueError("engineering_issue_report_reason_cannot_only_be_not_in_scope")

    @property
    def blocks_success(self) -> bool:
        return self.risk_level == "high" and self.blocks_current_task

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_ISSUE_REPORT_SCHEMA,
            "issue_id": self.issue_id,
            "source_package_id": self.source_package_id,
            "affected_files": copy.deepcopy(self.affected_files),
            "observed_symptom": self.observed_symptom,
            "root_cause_hypothesis": self.root_cause_hypothesis,
            "risk_level": self.risk_level,
            "blocks_current_task": self.blocks_current_task,
            "recommended_action": self.recommended_action,
            "reason_if_not_fixed_now": self.reason_if_not_fixed_now,
            "created_at": self.created_at,
            "blocks_success": self.blocks_success,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


def validate_issue_reports_allow_success(reports: Sequence[Mapping[str, Any] | EngineeringIssueReport]) -> dict[str, Any]:
    blocking_reports: list[dict[str, Any]] = []
    for item in reports:
        report = item if isinstance(item, EngineeringIssueReport) else EngineeringIssueReport.from_mapping(item)
        if report.blocks_success:
            blocking_reports.append(report.to_dict())
    return {
        "ok": not blocking_reports,
        "success_allowed": not blocking_reports,
        "blocking_issue_count": len(blocking_reports),
        "blocking_issues": blocking_reports,
    }


__all__ = [
    "ENGINEERING_ISSUE_REPORT_SCHEMA",
    "RECOMMENDED_ACTIONS",
    "RISK_LEVELS",
    "EngineeringIssueReport",
    "validate_issue_reports_allow_success",
]
