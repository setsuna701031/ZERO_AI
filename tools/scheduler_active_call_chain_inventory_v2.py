from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "core" / "tasks" / "scheduler.py"
REPORT_PATH = ROOT / "scheduler_active_call_chain_inventory_v2_report.txt"


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    return ""


def _call_name(node: ast.Call) -> str:
    return _name_of(node.func)


def _return_text(source_lines: list[str], node: ast.Return) -> str:
    lineno = getattr(node, "lineno", 0)
    if lineno <= 0 or lineno > len(source_lines):
        return "<unknown>"
    return source_lines[lineno - 1].strip()


def _collect_assigned_run_one_step(tree: ast.AST) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    assignments: list[tuple[int, str]] = []
    captures: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        value_name = _name_of(node.value)

        for target in node.targets:
            target_name = _name_of(target)

            if target_name == "Scheduler.run_one_step":
                assignments.append((node.lineno, value_name))

            if value_name == "Scheduler.run_one_step":
                captures.append((node.lineno, target_name))

    return assignments, captures


def _analyze_function(
    func: ast.FunctionDef,
    source_lines: list[str],
    capture_names: set[str],
) -> dict[str, object]:
    calls: list[tuple[int, str]] = []
    returns: list[tuple[int, str]] = []
    direct_scheduler_calls: list[tuple[int, str]] = []
    captured_base_calls: list[tuple[int, str]] = []
    suspicious_run_one_step_refs: list[tuple[int, str]] = []

    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            call = _call_name(node)
            if call:
                calls.append((node.lineno, call))

            if call == "Scheduler.run_one_step":
                direct_scheduler_calls.append((node.lineno, call))

            if call in capture_names:
                captured_base_calls.append((node.lineno, call))

            if "run_one_step" in call and call not in {func.name}:
                suspicious_run_one_step_refs.append((node.lineno, call))

        if isinstance(node, ast.Return):
            returns.append((node.lineno, _return_text(source_lines, node)))

    names = {
        item.id
        for item in ast.walk(func)
        if isinstance(item, ast.Name)
    }

    referenced_captures = sorted(name for name in capture_names if name in names)
    calls_previous = bool(captured_base_calls)

    return {
        "name": func.name,
        "line": func.lineno,
        "calls": calls,
        "returns": returns,
        "direct_scheduler_calls": direct_scheduler_calls,
        "captured_base_calls": captured_base_calls,
        "referenced_captures": referenced_captures,
        "suspicious_run_one_step_refs": suspicious_run_one_step_refs,
        "calls_previous": calls_previous,
        "direct_replacement_candidate": not calls_previous,
    }


def main() -> None:
    source = SCHEDULER_PATH.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source)

    assignments, captures = _collect_assigned_run_one_step(tree)
    capture_names = {name for _, name in captures}

    run_one_step_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and "run_one_step" in node.name
    ]
    run_one_step_functions.sort(key=lambda item: item.lineno)

    analyses = [
        _analyze_function(func, source_lines, capture_names)
        for func in run_one_step_functions
    ]

    final_active = assignments[-1][1] if assignments else "<none>"

    report: list[str] = []
    report.append("Scheduler Active Call Chain Inventory V2")
    report.append("")
    report.append(f"scheduler_path: {SCHEDULER_PATH}")
    report.append(f"total_lines: {len(source_lines)}")
    report.append(f"run_one_step_functions: {len(run_one_step_functions)}")
    report.append(f"run_one_step_assignments: {len(assignments)}")
    report.append(f"base_captures: {len(captures)}")
    report.append(f"final_active_run_one_step: {final_active}")
    report.append("")

    report.append("Assignment Timeline:")
    for lineno, value in assignments:
        marker = "  <-- FINAL ACTIVE" if value == final_active and lineno == assignments[-1][0] else ""
        report.append(f"- line {lineno}: Scheduler.run_one_step = {value}{marker}")
    report.append("")

    report.append("Base Capture Timeline:")
    for lineno, name in captures:
        report.append(f"- line {lineno}: {name} = Scheduler.run_one_step")
    report.append("")

    report.append("Function Call Detail:")
    for item in analyses:
        report.append(f"- line {item['line']}: {item['name']}")
        report.append(f"  calls_previous_captured_base: {item['calls_previous']}")
        report.append(f"  direct_replacement_candidate: {item['direct_replacement_candidate']}")

        referenced = item["referenced_captures"]
        if referenced:
            report.append(f"  referenced_captures: {', '.join(referenced)}")

        captured_calls = item["captured_base_calls"]
        if captured_calls:
            report.append("  captured_base_calls:")
            for lineno, call in captured_calls:
                report.append(f"    - line {lineno}: {call}()")

        scheduler_calls = item["direct_scheduler_calls"]
        if scheduler_calls:
            report.append("  direct_scheduler_run_one_step_calls:")
            for lineno, call in scheduler_calls:
                report.append(f"    - line {lineno}: {call}()")

        suspicious = item["suspicious_run_one_step_refs"]
        if suspicious:
            report.append("  run_one_step_related_calls:")
            for lineno, call in suspicious:
                report.append(f"    - line {lineno}: {call}()")

        returns = item["returns"]
        if returns:
            report.append("  returns:")
            for lineno, text in returns[:12]:
                report.append(f"    - line {lineno}: {text}")
            if len(returns) > 12:
                report.append(f"    - ... {len(returns) - 12} more return statements")

        calls = item["calls"]
        if calls:
            report.append("  calls_sample:")
            for lineno, call in calls[:20]:
                report.append(f"    - line {lineno}: {call}()")
            if len(calls) > 20:
                report.append(f"    - ... {len(calls) - 20} more calls")

    report.append("")
    report.append("Direct Replacement Candidates:")
    for item in analyses:
        if item["direct_replacement_candidate"]:
            report.append(f"- line {item['line']}: {item['name']}")
    report.append("")

    report.append("Likely Chain Breaks:")
    for item in analyses:
        if item["name"] == final_active:
            continue
        if item["direct_replacement_candidate"] and str(item["name"]).startswith("_zero_scheduler_run_one_step"):
            report.append(f"- line {item['line']}: {item['name']} does not call a captured previous run_one_step")
    report.append("")

    report.append("Safety Notes:")
    report.append("- This tool does not modify scheduler.py.")
    report.append("- A direct replacement candidate may still delegate indirectly; inspect calls_sample before deleting older layers.")
    report.append("- Do not remove any scheduler layer until the active chain and tests confirm it is dead.")
    report.append("- Non-mainline issue reporting: report unrelated suspicious scheduler/runtime issues explicitly.")
    report.append("")

    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()