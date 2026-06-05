from __future__ import annotations

"""Contract enforcement for engineering task result issue reporting.

Boundary:
- Result-shape validation and normalization only.
- No runtime orchestration.
- No scheduler execution.
- No repository mutation.
- No UI rendering.

This contract makes issue reporting mandatory for engineering work results.
Every result that leaves the Work Package / Goal / Program execution layer must
carry a complete issue summary, even when there are no issues.
"""

import copy
from typing import Any, Mapping, Sequence


ENGINEERING_RESULT_CONTRACT_SCHEMA = "zero.engineering_result_contract.v1"

REQUIRED_ENGINEERING_RESULT_FIELDS: tuple[str, ...] = (
    "task_result",
    "issues_found",
    "issues_deferred",
    "deferred_issues",
    "blocking_issues",
    "success_allowed",
)

NOT_IN_SCOPE_MARKERS: tuple[str, ...] = (
    "not_in_scope",
    "out_of_scope",
    "outside_scope",
    "outside_current_scope",
    "scope_out",
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


class EngineeringResultContractError(ValueError):
    """Raised when an engineering result violates mandatory issue reporting."""


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_issue_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise EngineeringResultContractError("issue_list_must_be_list")
    issues: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise EngineeringResultContractError("issue_entry_must_be_mapping")
        issues.append(copy.deepcopy(dict(item)))
    return issues


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


def _task_result_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    task_result = result.get("task_result")
    if isinstance(task_result, Mapping):
        return copy.deepcopy(dict(task_result))

    summary_keys = (
        "schema",
        "ok",
        "mode",
        "action",
        "package_id",
        "goal_id",
        "portfolio_id",
        "program_id",
        "selected_goal_id",
        "selected_portfolio_id",
        "terminal",
        "stop_reason",
        "error",
        "reason",
    )
    return {key: copy.deepcopy(result[key]) for key in summary_keys if key in result}


def normalize_engineering_result_contract(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a result with the mandatory engineering issue fields normalized."""

    if not isinstance(result, Mapping):
        raise EngineeringResultContractError("engineering_result_must_be_mapping")

    updated = copy.deepcopy(dict(result))
    issues_found = _as_issue_list(updated.get("issues_found", []))

    raw_deferred = updated.get("issues_deferred", updated.get("deferred_issues", []))
    issues_deferred = _as_issue_list(raw_deferred)
    blocking_issues = _as_issue_list(updated.get("blocking_issues", []))

    blocking_keys = {_issue_key(issue) for issue in blocking_issues}
    deferred_keys = {_issue_key(issue) for issue in issues_deferred}

    for issue in issues_found:
        key = _issue_key(issue)
        if _issue_blocks_current_task(issue) and key not in blocking_keys:
            blocking_issues.append(copy.deepcopy(dict(issue)))
            blocking_keys.add(key)
        elif _issue_is_deferred(issue) and key not in deferred_keys:
            issues_deferred.append(copy.deepcopy(dict(issue)))
            deferred_keys.add(key)

    success_allowed = bool(updated.get("success_allowed", True))
    if blocking_issues:
        success_allowed = False

    updated["task_result"] = _task_result_from_result(updated)
    updated["issues_found"] = issues_found
    updated["issues_deferred"] = issues_deferred
    updated["deferred_issues"] = copy.deepcopy(issues_deferred)
    updated["blocking_issues"] = blocking_issues
    updated["success_allowed"] = success_allowed
    updated["engineering_result_contract"] = {
        "schema": ENGINEERING_RESULT_CONTRACT_SCHEMA,
        "required_fields": list(REQUIRED_ENGINEERING_RESULT_FIELDS),
        "non_mainline_issue_reporting_required": True,
        "not_in_scope_issue_must_be_deferred": True,
        "blocking_issue_blocks_success": True,
    }

    if not success_allowed:
        updated["ok"] = False

    return updated


def validate_engineering_result_contract(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate mandatory engineering result fields and return a normalized copy."""

    if not isinstance(result, Mapping):
        raise EngineeringResultContractError("engineering_result_must_be_mapping")

    missing: list[str] = []
    if "task_result" not in result:
        missing.append("task_result")
    if "issues_found" not in result:
        missing.append("issues_found")
    if "blocking_issues" not in result:
        missing.append("blocking_issues")
    if "success_allowed" not in result:
        missing.append("success_allowed")
    if "issues_deferred" not in result and "deferred_issues" not in result:
        missing.append("issues_deferred")
    if missing:
        raise EngineeringResultContractError("missing_engineering_result_fields:" + ",".join(missing))

    normalized = normalize_engineering_result_contract(result)

    if normalized["blocking_issues"] and bool(result.get("success_allowed")):
        raise EngineeringResultContractError("blocking_issues_require_success_allowed_false")

    if normalized["success_allowed"] is False and bool(result.get("ok", False)):
        raise EngineeringResultContractError("success_not_allowed_requires_ok_false")

    deferred_keys = {_issue_key(issue) for issue in normalized["issues_deferred"]}
    blocking_keys = {_issue_key(issue) for issue in normalized["blocking_issues"]}
    for issue in normalized["issues_found"]:
        key = _issue_key(issue)
        if _is_not_in_scope_issue(issue) and key not in deferred_keys:
            raise EngineeringResultContractError("not_in_scope_issue_must_be_deferred")
        if _issue_blocks_current_task(issue) and key not in blocking_keys:
            raise EngineeringResultContractError("blocking_issue_must_be_listed_in_blocking_issues")

    return normalized


__all__ = [
    "BLOCKING_RECOMMENDED_ACTIONS",
    "DEFERRED_RECOMMENDED_ACTIONS",
    "ENGINEERING_RESULT_CONTRACT_SCHEMA",
    "NOT_IN_SCOPE_MARKERS",
    "REQUIRED_ENGINEERING_RESULT_FIELDS",
    "EngineeringResultContractError",
    "normalize_engineering_result_contract",
    "validate_engineering_result_contract",
]
