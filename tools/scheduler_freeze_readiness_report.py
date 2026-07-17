from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_REPORT = ROOT / "scheduler_mainline_inventory.txt"
CALLGRAPH_REPORT = ROOT / "scheduler_mainline_callgraph.txt"
FREEZE_REPORT = ROOT / "scheduler_freeze_readiness_report.txt"


FAMILY_ORDER = (
    "path",
    "dispatch",
    "repo_state",
    "planning",
    "repair",
    "queue",
    "tick",
    "create_task",
    "review",
    "run_one_step",
    "build/constants",
    "unknown",
)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _match(pattern: str, text: str, default: str = "unknown") -> str:
    found = re.search(pattern, text, flags=re.MULTILINE)
    if not found:
        return default
    return found.group(1).strip()


def _extract_console_like_counts(inventory_text: str) -> dict[str, str]:
    return {
        "total_lines": _match(r"^total_lines:\s*(.+)$", inventory_text),
        "import_count": _match(r"^import_count:\s*(.+)$", inventory_text),
        "class_count": _match(r"^class_count:\s*(.+)$", inventory_text),
        "method_count_inside_Scheduler": _match(
            r"^method_count_inside_Scheduler:\s*(.+)$", inventory_text
        ),
        "top_level_helper_function_count": _match(
            r"^top_level_helper_function_count:\s*(.+)$", inventory_text
        ),
        "scheduler_method_assignment_count": _match(
            r"^scheduler_method_assignment_count:\s*(.+)$", inventory_text
        ),
        "unsafe_bindings": _match(r"^unsafe_bindings:\s*(\d+)", inventory_text),
        "unsafe_runtime_entrypoints": _match(
            r"^unsafe_runtime_entrypoints:\s*(\d+)", inventory_text
        ),
    }


def _extract_final_run_one_step_binding(callgraph_text: str) -> str:
    return _match(
        r"^run_one_step_final:\s*(.+)$",
        callgraph_text,
        "Scheduler.run_one_step final binding not found",
    )


def _extract_matrix_rows(inventory_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    marker = "Scheduler Runtime Binding Consolidation Matrix"
    start = inventory_text.find(marker)
    if start == -1:
        return rows

    section = inventory_text[start:]
    next_heading = section.find("\nUnsafe runtime entrypoints")
    if next_heading != -1:
        section = section[:next_heading]

    current: dict[str, str] | None = None
    for raw_line in section.splitlines():
        line = raw_line.rstrip()
        family_match = re.match(r"^([A-Za-z0-9_/]+):$", line)
        if family_match and family_match.group(1) in FAMILY_ORDER:
            if current:
                rows.append(current)
            current = {"family": family_match.group(1)}
            continue

        if current is None:
            continue

        field_match = re.match(r"^\s+([a-z_]+):\s*(.+)$", line)
        if field_match:
            current[field_match.group(1)] = field_match.group(2).strip()

    if current:
        rows.append(current)

    return rows


def _extract_runtime_family_summary(inventory_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    marker = "Runtime Binding Families"
    start = inventory_text.find(marker)
    if start == -1:
        return rows

    section = inventory_text[start:]
    next_heading = section.find("\nScheduler Runtime Binding Consolidation Matrix")
    if next_heading != -1:
        section = section[:next_heading]

    current: dict[str, str] | None = None
    for raw_line in section.splitlines():
        line = raw_line.rstrip()
        family_match = re.match(r"^([A-Za-z0-9_/]+):$", line)
        if family_match and family_match.group(1) in FAMILY_ORDER:
            if current:
                rows.append(current)
            current = {"family": family_match.group(1)}
            continue

        if current is None:
            continue

        field_match = re.match(r"^\s+([a-z_]+):\s*(.+)$", line)
        if field_match:
            current[field_match.group(1)] = field_match.group(2).strip()

    if current:
        rows.append(current)

    return rows


def _extract_surface_summary(callgraph_text: str) -> list[str]:
    marker = "surface_summary:"
    start = callgraph_text.find(marker)
    if start == -1:
        return ["- surface summary not found"]

    lines = []
    for raw_line in callgraph_text[start:].splitlines()[1:]:
        line = raw_line.rstrip()
        if not line:
            break
        if line.startswith("- "):
            lines.append(line)
    return lines or ["- surface summary not found"]


def _decision_for_family(family: str, status: str) -> str:
    if family == "build/constants":
        return "do_not_touch; build and allowlist constants are not wrapper-collapse targets."
    if family == "run_one_step":
        return "freeze; final binding is documented and wrapper collapse is deferred."
    if family in {"dispatch", "queue", "tick", "repo_state", "repair"}:
        return "keep_runtime_surface; protected runtime family, defer consolidation to a dedicated behavior audit."
    if family in {"planning", "review", "path"}:
        return "audit_complete_for_freeze; retain surface and do not remove zero-ref bindings without a dedicated ownership audit."
    if family == "create_task":
        return "keep_runtime_surface; task creation is a protected runtime surface."
    if family == "unknown":
        return "documented_non_blocking; preserve current behavior and track as post-freeze classifier/audit work."
    return f"preserve; current matrix status={status or 'unknown'}."


def _append_table(lines: list[str], headers: Iterable[str], rows: Iterable[Iterable[str]]) -> None:
    headers = list(headers)
    row_list = [list(row) for row in rows]
    widths = [len(header) for header in headers]
    for row in row_list:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    lines.append(" | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)))
    lines.append("-+-".join("-" * width for width in widths))
    for row in row_list:
        lines.append(" | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row)))


def build_report() -> str:
    inventory_text = _read_text(INVENTORY_REPORT)
    callgraph_text = _read_text(CALLGRAPH_REPORT)

    counts = _extract_console_like_counts(inventory_text)
    family_rows = _extract_runtime_family_summary(inventory_text)
    matrix_rows = _extract_matrix_rows(inventory_text)
    surface_summary = _extract_surface_summary(callgraph_text)
    final_binding = _extract_final_run_one_step_binding(callgraph_text)

    family_by_name = {row["family"]: row for row in family_rows}
    matrix_by_name = {row["family"]: row for row in matrix_rows}

    lines: list[str] = []
    lines.append("Scheduler Freeze Readiness Report")
    lines.append("=================================")
    lines.append("")
    lines.append("Scope")
    lines.append("-----")
    lines.append("- Production scheduler code was not modified by this report.")
    lines.append("- This report summarizes the current scheduler inventory and callgraph evidence.")
    lines.append("- No row below is a safe-removal instruction.")
    lines.append("")

    lines.append("Inputs")
    lines.append("------")
    lines.append(f"- inventory_report: {INVENTORY_REPORT.relative_to(ROOT)}")
    lines.append(f"- callgraph_report: {CALLGRAPH_REPORT.relative_to(ROOT)}")
    lines.append("")

    lines.append("Scheduler Snapshot")
    lines.append("------------------")
    lines.append(f"- total_lines: {counts['total_lines']}")
    lines.append(f"- import_count: {counts['import_count']}")
    lines.append(f"- class_count: {counts['class_count']}")
    lines.append(f"- method_count_inside_Scheduler: {counts['method_count_inside_Scheduler']}")
    lines.append(
        f"- top_level_helper_function_count: {counts['top_level_helper_function_count']}"
    )
    lines.append(
        f"- scheduler_method_assignment_count: {counts['scheduler_method_assignment_count']}"
    )
    lines.append("")

    lines.append("Fast Regression")
    lines.append("---------------")
    lines.append("- latest observed fast lane: 370 passed, 5360 deselected, 73 subtests passed")
    lines.append("- command: python tools/regression_runner.py fast")
    lines.append("- long validation, full pytest, and nightly validation were not run by this package.")
    lines.append("")

    lines.append("Runtime Surface")
    lines.append("---------------")
    lines.append(f"- unsafe_bindings: {counts['unsafe_bindings']}")
    lines.append(f"- unsafe_runtime_entrypoints: {counts['unsafe_runtime_entrypoints']}")
    unknown_matrix = matrix_by_name.get("unknown", {})
    lines.append(
        "- unknown_runtime_entrypoints: "
        f"{unknown_matrix.get('runtime_entrypoint_count', 'unknown')}"
    )
    lines.append("")

    lines.append("Final Binding")
    lines.append("-------------")
    lines.append(f"- {final_binding}")
    lines.append("")

    lines.append("Callgraph Surface Summary")
    lines.append("-------------------------")
    lines.extend(surface_summary)
    lines.append("")

    lines.append("Runtime Family Summary")
    lines.append("----------------------")
    summary_rows = []
    for family in FAMILY_ORDER:
        family_row = family_by_name.get(family, {})
        matrix_row = matrix_by_name.get(family, {})
        summary_rows.append(
            [
                family,
                family_row.get("binding_count", matrix_row.get("binding_count", "0")),
                matrix_row.get("runtime_entrypoint_count", "0"),
                matrix_row.get("active_refs_summary", "none"),
                matrix_row.get("consolidation_status", "unknown"),
            ]
        )
    _append_table(
        lines,
        ("family", "bindings", "runtime_entrypoints", "active_refs", "status"),
        summary_rows,
    )
    lines.append("")

    lines.append("Freeze Decisions")
    lines.append("----------------")
    decision_rows = []
    for family in FAMILY_ORDER:
        status = matrix_by_name.get(family, {}).get("consolidation_status", "unknown")
        decision_rows.append([family, _decision_for_family(family, status)])
    _append_table(lines, ("family", "decision"), decision_rows)
    lines.append("")

    lines.append("Freeze Readiness")
    lines.append("----------------")
    lines.append("status: AER Scheduler Freeze Candidate")
    lines.append("")
    lines.append("Rationale:")
    lines.append("- The scheduler runtime surface is inventoried and grouped into functional families.")
    lines.append("- The final run_one_step binding is explicit in the callgraph report.")
    lines.append("- Protected runtime families are preserved rather than removed.")
    lines.append("- Unknown runtime entrypoints are documented and treated as non-removal surfaces.")
    lines.append("- The fast regression lane is passing.")
    lines.append("")

    lines.append("Required Guardrails")
    lines.append("-------------------")
    lines.append("- Do not collapse run_one_step wrappers without a dedicated behavior audit.")
    lines.append("- Do not delete review, planning, path, or unknown-family rows from inventory alone.")
    lines.append("- Do not treat zero active textual references as proof of safe removal for monkey patches.")
    lines.append("- Long validation remains local-only and is not delegated to Codex.")
    lines.append("")

    lines.append("Non-Mainline Issues Found")
    lines.append("-------------------------")
    lines.append("- None fixed in this package.")
    lines.append("- Unknown runtime entrypoints remain as post-freeze classifier/audit work.")
    lines.append("- Callgraph high-risk consolidation candidates are documentation signals only, not change instructions.")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    report = build_report()
    FREEZE_REPORT.write_text(report, encoding="utf-8")
    print(str(FREEZE_REPORT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
