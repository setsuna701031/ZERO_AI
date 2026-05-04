#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZERO W Pack - Persona Status Bridge

Place this file at:
    E:\zero_ai\persona_status_bridge.py

Purpose:
- Read ZERO self-edit status and review files.
- Produce a compact status report for UI / Persona / CLI.
- No write-back action exists in this bridge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


SELF_EDIT_ROOT = Path("workspace") / "self_edit"
WORKCOPY_DIR = SELF_EDIT_ROOT / "zero_ai_workcopy"
REVIEW_DIR = SELF_EDIT_ROOT / "review"

STATUS_JSON = SELF_EDIT_ROOT / "persona_status.json"
STATUS_TXT = SELF_EDIT_ROOT / "persona_status.txt"
CHANGED_FILES_TXT = REVIEW_DIR / "changed_files.txt"
DIFF_TXT = REVIEW_DIR / "diff.txt"
MANIFEST_JSON = REVIEW_DIR / "manifest.json"
BRIDGE_REPORT_JSON = SELF_EDIT_ROOT / "persona_bridge_report.json"
BRIDGE_REPORT_TXT = SELF_EDIT_ROOT / "persona_bridge_report.txt"


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []


def build_report() -> Dict[str, Any]:
    status = read_json(STATUS_JSON)
    manifest = read_json(MANIFEST_JSON)
    changed_lines = read_lines(CHANGED_FILES_TXT)

    return {
        "workcopy_ready": WORKCOPY_DIR.exists(),
        "workcopy_path": str(WORKCOPY_DIR),
        "status_phase": status.get("phase"),
        "status_summary": status.get("summary"),
        "changed_file_count": len(changed_lines),
        "changed_files": changed_lines,
        "review_ready": MANIFEST_JSON.exists(),
        "apply_back_allowed_by_bridge": False,
        "human_review_required": True,
        "paths": {
            "persona_status_json": str(STATUS_JSON),
            "persona_status_txt": str(STATUS_TXT),
            "changed_files": str(CHANGED_FILES_TXT),
            "diff": str(DIFF_TXT),
            "manifest": str(MANIFEST_JSON),
        },
        "manifest_error": manifest.get("error"),
    }


def write_report() -> None:
    SELF_EDIT_ROOT.mkdir(parents=True, exist_ok=True)
    report = build_report()
    BRIDGE_REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "[ZERO PERSONA BRIDGE REPORT]",
        f"Workcopy ready       : {report['workcopy_ready']}",
        f"Workcopy path        : {report['workcopy_path']}",
        f"Status phase         : {report.get('status_phase')}",
        f"Status summary       : {report.get('status_summary')}",
        f"Review ready         : {report['review_ready']}",
        f"Changed file count   : {report['changed_file_count']}",
        f"Human review required: {report['human_review_required']}",
        "",
        "[CHANGED FILES]",
    ]

    if report["changed_files"]:
        lines.extend(f"- {p}" for p in report["changed_files"])
    else:
        lines.append("(none)")

    lines.extend(
        [
            "",
            "[GATE]",
            "This bridge does not apply changes back.",
            "Use self_edit_apply_back.py only after manual review.",
        ]
    )

    BRIDGE_REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(BRIDGE_REPORT_TXT.read_text(encoding="utf-8"))


def main() -> int:
    write_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
