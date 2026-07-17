from __future__ import annotations

import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python tools/work_package_readable_report.py <package_id>")
        return 2

    package_id = sys.argv[1]
    root = Path(".")
    record_path = root / "workspace" / "runtime_work_packages" / f"{package_id}.json"

    if not record_path.is_file():
        print(f"not found: {record_path}")
        return 1

    record = load_json(record_path)
    progress = record.get("progress_snapshot") or {}
    memory_id = progress.get("memory_record_id") or record.get("memory_record_id")

    memory = {}
    if memory_id:
        mp = root / "workspace" / "work_package_memory" / "records" / f"{memory_id}.json"
        if mp.is_file():
            memory = load_json(mp)

    summary = memory or record
    evidence = summary.get("execution_evidence_summary") or {}
    test_summary = summary.get("test_result_summary") or {}
    objective = summary.get("original_objective") or {}

    print("# ZERO Work Package Report")
    print()
    print(f"Package: {package_id}")
    print(f"Title: {objective.get('title') or record.get('title') or ''}")
    print(f"Status: {summary.get('final_status') or progress.get('lifecycle_state') or record.get('lifecycle_state')}")
    print(f"Memory: {record.get('memory_status') or summary.get('memory_status') or ''}")
    print()

    print("## Progress")
    print(f"- Completed steps: {test_summary.get('completed_steps', progress.get('completed_steps', 0))}")
    print(f"- Failed steps: {test_summary.get('failed_steps', progress.get('failed_steps', 0))}")
    print(f"- Remaining steps: {progress.get('remaining_steps', 0)}")
    print(f"- Evidence count: {evidence.get('evidence_count', 0)}")
    print()

    print("## Validation Commands")
    commands = test_summary.get("validation_commands") or record.get("validation_commands") or []
    if commands:
        for cmd in commands:
            print(f"- {cmd}")
    else:
        print("- None")
    print()

    print("## Modified Files")
    files = summary.get("modified_files_summary") or []
    files = [str(x) for x in files if str(x).strip()]
    if files:
        for f in files:
            print(f"- {f}")
    else:
        print("- None")
    print()

    print("## Non-mainline Findings")
    findings = summary.get("non_mainline_findings") or []
    if findings:
        for item in findings:
            print(f"- {item}")
    else:
        print("- None")
    print()

    root_cause = summary.get("root_cause") or progress.get("root_cause")
    print("## Root Cause")
    print(root_cause or "None")
    print()

    remaining = progress.get("remaining_failures") or summary.get("remaining_failures") or []
    print("## Remaining Failures")
    if remaining:
        for item in remaining:
            print(f"- {item}")
    else:
        print("- None")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
