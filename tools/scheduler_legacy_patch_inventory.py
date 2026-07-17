from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = REPO_ROOT / "core" / "tasks" / "scheduler.py"
REPORT_PATH = REPO_ROOT / "scheduler_legacy_patch_inventory_report.txt"


PATCH_ASSIGNMENT_PATTERN = re.compile(
    r"^Scheduler\.(?P<method>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<target>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)

DEF_PATTERN = re.compile(
    r"^def\s+(?P<name>_zero_[A-Za-z0-9_]+|_scheduler_[A-Za-z0-9_]+)\s*\(",
    re.MULTILINE,
)

RUN_ONE_STEP_PATTERN = re.compile(
    r"^def\s+(?P<name>_zero_[A-Za-z0-9_]*run_one_step[A-Za-z0-9_]*)\s*\(",
    re.MULTILINE,
)

BASE_CAPTURE_PATTERN = re.compile(
    r"^(?P<name>_zero_[A-Za-z0-9_]*base[A-Za-z0-9_]*|_ZERO_[A-Za-z0-9_]*ORIGINAL[A-Za-z0-9_]*)\s*=\s*Scheduler\.run_one_step",
    re.MULTILINE,
)


def line_for_offset(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def main() -> int:
    source = SCHEDULER_PATH.read_text(encoding="utf-8")

    defs = [
        {
            "name": match.group("name"),
            "line": line_for_offset(source, match.start()),
        }
        for match in DEF_PATTERN.finditer(source)
    ]

    run_one_step_defs = [
        {
            "name": match.group("name"),
            "line": line_for_offset(source, match.start()),
        }
        for match in RUN_ONE_STEP_PATTERN.finditer(source)
    ]

    assignments = [
        {
            "method": match.group("method"),
            "target": match.group("target"),
            "line": line_for_offset(source, match.start()),
        }
        for match in PATCH_ASSIGNMENT_PATTERN.finditer(source)
    ]

    base_captures = [
        {
            "name": match.group("name"),
            "line": line_for_offset(source, match.start()),
        }
        for match in BASE_CAPTURE_PATTERN.finditer(source)
    ]

    lines: list[str] = [
        "Scheduler Legacy Patch Inventory",
        "",
        f"scheduler_path: {SCHEDULER_PATH}",
        f"total_lines: {len(source.splitlines())}",
        f"zero_helper_defs: {len(defs)}",
        f"run_one_step_defs: {len(run_one_step_defs)}",
        f"scheduler_method_assignments: {len(assignments)}",
        f"run_one_step_base_captures: {len(base_captures)}",
        "",
        "Run One Step Definitions:",
    ]

    for item in run_one_step_defs:
        lines.append(f"- line {item['line']}: {item['name']}")

    lines.extend(["", "Scheduler Method Assignments:"])
    for item in assignments:
        lines.append(f"- line {item['line']}: Scheduler.{item['method']} = {item['target']}")

    lines.extend(["", "Run One Step Base Captures:"])
    for item in base_captures:
        lines.append(f"- line {item['line']}: {item['name']} = Scheduler.run_one_step")

    lines.extend(
        [
            "",
            "Non-Mainline Issue Reporting:",
            "- This report does not change scheduler.py.",
            "- Repeated Scheduler.run_one_step monkey-patch layers are high-risk technical debt.",
            "- Do not remove any layer until the final active call chain and test coverage are mapped.",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())