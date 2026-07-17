from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "core" / "tasks" / "scheduler.py"
REPORT_PATH = ROOT / "scheduler_active_call_chain_inventory_report.txt"


def _line_text(lines: list[str], lineno: int) -> str:
    if lineno <= 0 or lineno > len(lines):
        return ""
    return lines[lineno - 1].strip()


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    return ""


def _collect_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
    return names


def main() -> None:
    source = SCHEDULER_PATH.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)

    function_defs: dict[str, ast.FunctionDef] = {}
    run_one_step_defs: list[ast.FunctionDef] = []
    assignments: list[tuple[int, str, str]] = []
    captures: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            function_defs[node.name] = node
            if "run_one_step" in node.name:
                run_one_step_defs.append(node)

        if isinstance(node, ast.Assign):
            value_name = _name_of(node.value)
            for target in node.targets:
                target_name = _name_of(target)

                if target_name == "Scheduler.run_one_step":
                    assignments.append((node.lineno, target_name, value_name))

                if value_name == "Scheduler.run_one_step":
                    captures.append((node.lineno, target_name, value_name))

    final_assignment = assignments[-1] if assignments else None
    final_active = final_assignment[2] if final_assignment else "<none>"

    report: list[str] = []
    report.append("Scheduler Active Call Chain Inventory")
    report.append("")
    report.append(f"scheduler_path: {SCHEDULER_PATH}")
    report.append(f"total_lines: {len(lines)}")
    report.append(f"run_one_step_defs: {len(run_one_step_defs)}")
    report.append(f"run_one_step_assignments: {len(assignments)}")
    report.append(f"base_captures: {len(captures)}")
    report.append(f"final_active_run_one_step: {final_active}")
    report.append("")

    report.append("Run One Step Assignment Timeline:")
    for lineno, target, value in assignments:
        marker = "  <-- FINAL ACTIVE" if final_assignment and lineno == final_assignment[0] else ""
        report.append(f"- line {lineno}: {target} = {value}{marker}")
    report.append("")

    report.append("Base Capture Timeline:")
    for lineno, target, value in captures:
        report.append(f"- line {lineno}: {target} = {value}")
    report.append("")

    report.append("Run One Step Definitions Detail:")
    for func in sorted(run_one_step_defs, key=lambda item: item.lineno):
        names = _collect_names(func)
        referenced_captures = [
            capture_name
            for _, capture_name, _ in captures
            if capture_name in names
        ]

        calls_previous = bool(referenced_captures)
        report.append(f"- line {func.lineno}: {func.name}")
        report.append(f"  calls_captured_base: {calls_previous}")
        if referenced_captures:
            report.append(f"  captured_base_refs: {', '.join(sorted(referenced_captures))}")

        interesting_refs = sorted(
            name
            for name in names
            if (
                "ORIGINAL" in name
                or "base_run_one_step" in name
                or "run_one_step" in name
            )
            and name != func.name
        )
        if interesting_refs:
            report.append(f"  interesting_refs: {', '.join(interesting_refs)}")
    report.append("")

    report.append("Potentially Direct Replacement Layers:")
    for func in sorted(run_one_step_defs, key=lambda item: item.lineno):
        names = _collect_names(func)
        referenced_captures = [
            capture_name
            for _, capture_name, _ in captures
            if capture_name in names
        ]
        if not referenced_captures:
            report.append(f"- line {func.lineno}: {func.name}")
    report.append("")

    report.append("Safety Notes:")
    report.append("- This tool does not modify scheduler.py.")
    report.append("- Do not remove run_one_step layers until this report confirms whether they call captured bases.")
    report.append("- Treat final_active_run_one_step as the currently bound Scheduler.run_one_step implementation.")
    report.append("- Non-mainline issue reporting: any unrelated suspicious scheduler/runtime issue found during consolidation must be reported explicitly, not silently skipped.")
    report.append("")

    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()