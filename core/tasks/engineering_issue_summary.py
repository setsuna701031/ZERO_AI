from __future__ import annotations

"""Shared issue summary fields for engineering package results.

Boundary:
- Builds and attaches the mandatory engineering issue summary.
- Enforces the result contract shape before results leave Goal / Portfolio /
  Program execution layers.
- Does not run RuntimeOrchestrator, Scheduler, Memory, or UI code.
"""

import copy
from pathlib import Path
from typing import Any, Mapping

from core.tasks.engineering_issue_reporter import EngineeringIssueReporter
from core.tasks.engineering_result_contract import normalize_engineering_result_contract


ENGINEERING_ISSUE_SUMMARY_SCHEMA = "zero.engineering_issue_summary.v2"

DEFERRED_RECOMMENDED_ACTIONS: frozenset[str] = frozenset(
    {
        "queue_for_next_package",
        "defer_to_next_package",
        "defer",
        "report_only",
        "ignore_with_reason",
        "track_as_non_mainline_issue",
    }
)

BLOCKING_RECOMMENDED_ACTIONS: frozenset[str] = frozenset(
    {
        "block_current_task",
        "stop_current_task",
        "fix_before_success",
        "require_resolution",
        "manual_intervention_required",
    }
)

NOT_IN_SCOPE_MARKERS: tuple[str, ...] = (
    "not_in_scope",
    "out_of_scope",
    "outside_scope",
    "outside_current_scope",
    "scope_out",
)


def _as_issue_list(value: Any) -> list[dict[str, Any]]:
    return [copy.deepcopy(dict(item)) for item in value] if isinstance(value, list) else []


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _issue_key(issue: Mapping[str, Any]) -> str:
    explicit_id = _clean_text(issue.get("issue_id") or issue.get("id"))
    if explicit_id:
        return f"id:{explicit_id}"
    normalized = {
        "severity": _clean_text(issue.get("severity")),
        "category": _clean_text(issue.get("category") or issue.get("issue_type")),
        "reason": _clean_text(issue.get("reason") or issue.get("message") or issue.get("summary")),
        "path": _clean_text(issue.get("path") or issue.get("file") or issue.get("target_path")),
        "recommended_action": _clean_text(issue.get("recommended_action")),
    }
    return "anon:" + repr(sorted(normalized.items()))


def _contains_marker(value: Any, markers: tuple[str, ...]) -> bool:
    text = _clean_text(value).lower()
    return any(marker in text for marker in markers)


def _is_not_in_scope_issue(issue: Mapping[str, Any]) -> bool:
    fields = (
        issue.get("reason"),
        issue.get("category"),
        issue.get("issue_type"),
        issue.get("scope"),
        issue.get("recommended_action"),
        issue.get("message"),
        issue.get("summary"),
    )
    return any(_contains_marker(value, NOT_IN_SCOPE_MARKERS) for value in fields)


def _issue_blocks_current_task(issue: Mapping[str, Any]) -> bool:
    if bool(issue.get("blocks_current_task")):
        return True
    if bool(issue.get("blocking")):
        return True
    if _clean_text(issue.get("recommended_action")) in BLOCKING_RECOMMENDED_ACTIONS:
        return True
    severity = _clean_text(issue.get("severity")).lower()
    risk = _clean_text(issue.get("risk") or issue.get("risk_level")).lower()
    if severity in {"blocking", "critical", "fatal"}:
        return True
    if risk in {"high", "critical"} and bool(issue.get("blocks_current_task")):
        return True
    return False


def _issue_is_deferred(issue: Mapping[str, Any]) -> bool:
    if bool(issue.get("deferred")):
        return True
    if _clean_text(issue.get("recommended_action")) in DEFERRED_RECOMMENDED_ACTIONS:
        return True
    return _is_not_in_scope_issue(issue)


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for issue in issues:
        key = _issue_key(issue)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(copy.deepcopy(dict(issue)))
    return deduped


def build_engineering_issue_summary(
    repo_root: str | Path,
    *,
    issue_reporter: EngineeringIssueReporter | Any | None = None,
) -> dict[str, Any]:
    reporter = issue_reporter or EngineeringIssueReporter(repo_root)
    reporter_summary = reporter.build_summary()

    issues_found = _dedupe_issues(_as_issue_list(reporter_summary.get("issues")))
    blocking_issues = _dedupe_issues(_as_issue_list(reporter_summary.get("blocking_issues")))

    blocking_keys = {_issue_key(issue) for issue in blocking_issues}
    for issue in issues_found:
        key = _issue_key(issue)
        if _issue_blocks_current_task(issue) and key not in blocking_keys:
            blocking_issues.append(copy.deepcopy(dict(issue)))
            blocking_keys.add(key)

    deferred_issues: list[dict[str, Any]] = []
    deferred_keys: set[str] = set()
    for issue in issues_found:
        key = _issue_key(issue)
        if key in blocking_keys:
            continue
        if _issue_is_deferred(issue) and key not in deferred_keys:
            deferred_issues.append(copy.deepcopy(dict(issue)))
            deferred_keys.add(key)

    reporter_success_allowed = bool(reporter_summary.get("success_allowed", True))
    success_allowed = reporter_success_allowed and not bool(blocking_issues)

    return {
        "schema": ENGINEERING_ISSUE_SUMMARY_SCHEMA,
        "issues_found": issues_found,
        "issues_deferred": deferred_issues,
        "deferred_issues": copy.deepcopy(deferred_issues),
        "blocking_issues": blocking_issues,
        "success_allowed": success_allowed,
    }


def apply_engineering_issue_summary(
    result: Mapping[str, Any],
    *,
    repo_root: str | Path,
    issue_reporter: EngineeringIssueReporter | Any | None = None,
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(result)) if isinstance(result, Mapping) else {}
    issue_summary = build_engineering_issue_summary(repo_root, issue_reporter=issue_reporter)
    updated.update(
        {
            "issues_found": issue_summary["issues_found"],
            "issues_deferred": issue_summary["issues_deferred"],
            "deferred_issues": issue_summary["deferred_issues"],
            "blocking_issues": issue_summary["blocking_issues"],
            "success_allowed": issue_summary["success_allowed"],
        }
    )
    return normalize_engineering_result_contract(updated)


__all__ = [
    "ENGINEERING_ISSUE_SUMMARY_SCHEMA",
    "apply_engineering_issue_summary",
    "build_engineering_issue_summary",
]
