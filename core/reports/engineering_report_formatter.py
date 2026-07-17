from __future__ import annotations

import json
from typing import Any, Mapping


SECTION_LABELS = {
    "current_status": "Current Status",
    "completed": "Completed",
    "root_cause": "Root Cause",
    "ownership_authority_path_contract_map": "Ownership / Authority / Path Contract Map",
    "modified_files": "Modified Files",
    "added_updated_tests": "Added/Updated Tests",
    "validation_results": "Validation Results",
    "remaining_failures": "Remaining Failures",
    "non_mainline_findings": "Non-Mainline Findings",
    "safe_to_push": "Safe To Push",
    "next_action_package": "Next Action Package",
    "commands_to_run": "Commands To Run",
}


def _render(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {_render(item)}" for item in value) or "- None"
    if isinstance(value, Mapping):
        return f"```json\n{json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True)}\n```"
    if value in (None, ""):
        return "None"
    return str(value)


def format_engineering_report(report: Mapping[str, Any]) -> str:
    sections = ["# ZERO Engineering Report"]
    for key, label in SECTION_LABELS.items():
        sections.extend(["", f"## {label}", _render(report.get(key))])
    return "\n".join(sections) + "\n"


__all__ = ["SECTION_LABELS", "format_engineering_report"]
