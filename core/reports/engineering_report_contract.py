from __future__ import annotations

import copy
from typing import Any, Mapping


ENGINEERING_REPORT_SCHEMA = "zero.engineering_report_usability.v1"
SAFE_TO_PUSH = "safe_to_push"
PUSH_AFTER_REVIEW = "push_after_review"
NOT_SAFE_TO_PUSH = "not_safe_to_push"


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _finding(value: Any, *, classification: str, mainline_blocker: bool) -> dict[str, Any]:
    item = _mapping(value)
    return {
        "test_file": _text(item.get("test_file")),
        "line": int(item.get("line") or 0),
        "expected": _text(item.get("expected")),
        "actual": _text(item.get("actual")),
        "suspected_layer": _text(item.get("suspected_layer")),
        "classification": classification,
        "mainline_blocker": bool(item.get("mainline_blocker", mainline_blocker)),
    }


def _next_action_prompt(report: Mapping[str, Any]) -> str:
    failures = _list(report.get("remaining_failures"))
    findings = _list(report.get("non_mainline_findings"))
    commands = [_text(item) for item in _list(report.get("commands_to_run")) if _text(item)]
    lines = ["Objective: Close the next truthful engineering boundary."]
    if failures:
        failure = _mapping(failures[0])
        location = _text(failure.get("test_file"))
        if failure.get("line"):
            location = f"{location}:{failure['line']}"
        lines.extend(["", f"Next Failure: {location}", f"Suspected Layer: {_text(failure.get('suspected_layer'))}"])
    elif findings:
        lines.extend(["", "Next Action: Review non-mainline findings before push."])
    else:
        lines.extend(["", "Next Action: No remaining failures."])
    lines.extend(["", "Commands To Run:"])
    lines.extend(f"- {command}" for command in commands)
    return "\n".join(lines)


def build_engineering_report(result: Mapping[str, Any], *, report_type: str = "engineering") -> dict[str, Any]:
    source = _mapping(result)
    remaining_failures = [
        _finding(item, classification="mainline_blocker", mainline_blocker=True)
        for item in _list(source.get("remaining_failures"))
    ]
    non_mainline_findings = [
        _finding(item, classification="non_mainline_finding", mainline_blocker=False)
        for item in _list(source.get("non_mainline_findings"))
    ]
    safe_to_push = (
        NOT_SAFE_TO_PUSH
        if remaining_failures
        else PUSH_AFTER_REVIEW
        if non_mainline_findings
        else SAFE_TO_PUSH
        if bool(source.get("ok"))
        else NOT_SAFE_TO_PUSH
    )
    report = {
        "schema": ENGINEERING_REPORT_SCHEMA,
        "report_type": _text(report_type, "engineering"),
        "current_status": _text(source.get("status"), "completed" if source.get("ok") else "failed"),
        "completed": _list(source.get("completed")),
        "root_cause": copy.deepcopy(source.get("root_cause")),
        "ownership_authority_path_contract_map": _mapping(source.get("execution_path")),
        "modified_files": _list(source.get("changed_files") or source.get("modified_files")),
        "added_updated_tests": _list(source.get("added_updated_tests")),
        "validation_results": _list(source.get("validation_results")),
        "remaining_failures": remaining_failures,
        "non_mainline_findings": non_mainline_findings,
        "safe_to_push": safe_to_push,
        "commands_to_run": _list(source.get("commands_to_run")),
        "hard_engineering_boundary": {
            "truthful_status_required": True,
            "runtime_ownership_unchanged": True,
            "report_projection_only": True,
        },
    }
    report["next_action_package"] = {"prompt": _next_action_prompt(report)}
    report["contract_validation"] = validate_engineering_report(report)
    return report


def attach_engineering_report(result: Mapping[str, Any], *, report_type: str = "engineering") -> dict[str, Any]:
    from core.reports.engineering_report_formatter import format_engineering_report

    updated = _mapping(result)
    report = build_engineering_report(updated, report_type=report_type)
    updated["engineering_report"] = report
    updated["engineering_report_markdown"] = format_engineering_report(report)
    return updated


def validate_engineering_report(report: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema",
        "report_type",
        "current_status",
        "completed",
        "root_cause",
        "ownership_authority_path_contract_map",
        "modified_files",
        "added_updated_tests",
        "validation_results",
        "remaining_failures",
        "non_mainline_findings",
        "safe_to_push",
        "next_action_package",
        "commands_to_run",
        "hard_engineering_boundary",
    }
    missing = sorted(required.difference(report.keys())) if isinstance(report, Mapping) else sorted(required)
    return {"ok": not missing, "missing_fields": missing, "schema": ENGINEERING_REPORT_SCHEMA}


__all__ = [
    "ENGINEERING_REPORT_SCHEMA",
    "NOT_SAFE_TO_PUSH",
    "PUSH_AFTER_REVIEW",
    "SAFE_TO_PUSH",
    "attach_engineering_report",
    "build_engineering_report",
    "validate_engineering_report",
]
