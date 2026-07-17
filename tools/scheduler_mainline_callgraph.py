from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "tasks" / "scheduler.py"
INVENTORY = ROOT / "scheduler_mainline_inventory.txt"
REPORT = ROOT / "scheduler_mainline_callgraph.txt"

SURFACE_ORDER = (
    "run_one_step",
    "tick",
    "dispatch",
    "queue",
    "repo_state",
    "planning",
    "repair",
    "review",
    "path",
)

PUBLIC_SURFACE_ATTRS = {
    "run_one_step": {"run_one_step"},
    "tick": {"tick", "_run_simple_task_tick"},
    "dispatch": {
        "_handle_dispatch_result",
        "_handle_missing_repo_task",
        "_handle_run_one_step_exception",
        "_finalize_dispatched_task",
    },
    "queue": {"cleanup_task_queue_hygiene", "get_queue_snapshot", "get_queue_rows"},
    "repo_state": {
        "_extract_effective_status_and_answer",
        "_mark_repo_task_finished",
        "_mark_repo_task_failed",
        "_mark_repo_task_queued",
    },
    "planning": {"_plan_goal", "_execute_simple_step"},
    "repair": {
        "_find_active_duplicate_repair_task",
        "_is_repairable_failure",
        "_normalize_replan_metadata",
    },
    "review": {"approve_review_item", "reject_review_item", "get_review_queue"},
    "path": {
        "_resolve_step_path",
        "_resolve_read_path_with_fallback",
        "_needs_scheduler_path_resolution",
        "_normalize_step_scope",
        "_resolve_guard_target_path",
    },
}

HIGH_RISK_SURFACES = {
    "run_one_step",
    "tick",
    "dispatch",
    "queue",
    "repo_state",
    "repair",
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _name_of(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    if isinstance(node, ast.Subscript):
        return _name_of(node.value)
    return ""


def _calls_in(node: ast.AST) -> list[str]:
    calls: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            call_name = _name_of(child.func)
            if call_name:
                calls.add(call_name)
    return sorted(calls)


def _scheduler_class(tree: ast.Module) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Scheduler":
            return node
    raise RuntimeError("Scheduler class not found")


def _top_level_functions(
    tree: ast.Module,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _scheduler_methods(
    cls: ast.ClassDef,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _scheduler_assignments(tree: ast.Module) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "Scheduler"
            ):
                rows.append(
                    {
                        "line": node.lineno,
                        "attr": target.attr,
                        "target": f"Scheduler.{target.attr}",
                        "value": ast.unparse(node.value),
                        "value_name": _name_of(node.value),
                    }
                )
    return sorted(rows, key=lambda row: int(row["line"]))


def _symbol_from_inventory_line(line: str) -> str:
    match = re.match(r"- ([^ ]+) \(line ", line)
    return match.group(1) if match else ""


def _parse_inventory_refs() -> dict[str, dict[str, int | str]]:
    refs: dict[str, dict[str, int | str]] = {}
    pattern = re.compile(
        r"- (?P<name>[^ ]+) \(line (?P<line>\d+); "
        r"active_refs=(?P<active>\d+); archived_refs=(?P<archived>\d+); "
        r"report_refs=(?P<report>\d+); binding_class=(?P<class>[^)]+)\)"
    )
    for line in _read_text(INVENTORY).splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        refs[match.group("name")] = {
            "line": int(match.group("line")),
            "active_refs": int(match.group("active")),
            "archived_refs": int(match.group("archived")),
            "report_refs": int(match.group("report")),
            "binding_class": match.group("class"),
        }
    return refs


def _surface_for_assignment(row: dict[str, object]) -> str:
    attr = str(row["attr"])
    if (
        attr == "SCHEDULER_BUILD"
        or attr.startswith("REPAIRABLE_")
        or attr.startswith("CODE_CHAIN_")
    ):
        return ""
    value = " ".join([str(row["value"]), str(row["value_name"])]).lower()
    for surface, attrs in PUBLIC_SURFACE_ATTRS.items():
        if attr in attrs:
            return surface
    if "run_one_step" in value:
        return "run_one_step"
    if "tick" in value:
        return "tick"
    if "dispatch" in value:
        return "dispatch"
    if "queue" in value:
        return "queue"
    if "repo" in value or "status_and_answer" in value:
        return "repo_state"
    if "plan" in value or "execute_simple_step" in value:
        return "planning"
    if "repair" in value:
        return "repair"
    if "review" in value:
        return "review"
    if "path" in value or "scope" in value:
        return "path"
    return ""


def _helper_surface(name: str) -> str:
    lowered = name.lower()
    if "run_one_step" in lowered:
        return "run_one_step"
    if "tick" in lowered:
        return "tick"
    if "dispatch" in lowered or "missing_repo_task" in lowered:
        return "dispatch"
    if "queue" in lowered or "snapshot" in lowered or "rows" in lowered:
        return "queue"
    if "repo_task" in lowered or "effective_status" in lowered:
        return "repo_state"
    if "plan" in lowered or "execute_simple_step" in lowered:
        return "planning"
    if "repair" in lowered or "replan" in lowered:
        return "repair"
    if "review" in lowered:
        return "review"
    if "path" in lowered or "scope" in lowered:
        return "path"
    return ""


def _walk_helper_closure(
    seed_names: Iterable[str],
    helper_defs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> list[str]:
    seen: set[str] = set()
    pending = [name for name in seed_names if name in helper_defs]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        for call_name in _calls_in(helper_defs[name]):
            short_name = call_name.rsplit(".", 1)[-1]
            if short_name in helper_defs and short_name not in seen:
                pending.append(short_name)
    return sorted(seen, key=lambda item: helper_defs[item].lineno)


def _risk_and_recommendation(surface: str, assignments: list[dict[str, object]]) -> tuple[str, str]:
    if surface in HIGH_RISK_SURFACES:
        return "high", "consolidation candidate"
    if len(assignments) > 1:
        return "medium", "audit further"
    return "low", "keep"


def _known_refs_for_symbol(
    symbol: str,
    inventory_refs: dict[str, dict[str, int | str]],
) -> str:
    data = inventory_refs.get(symbol)
    if not data:
        return "active_refs=unknown"
    return (
        f"active_refs={data['active_refs']}; archived_refs={data['archived_refs']}; "
        f"report_refs={data['report_refs']}; binding_class={data['binding_class']}"
    )


def _final_binding_text(assignments: list[dict[str, object]]) -> str:
    if not assignments:
        return "<none>"
    by_attr: dict[str, dict[str, object]] = {}
    for row in assignments:
        by_attr[str(row["attr"])] = row
    parts = []
    for attr in sorted(by_attr):
        row = by_attr[attr]
        parts.append(f"{row['target']} = {row['value']} (line {row['line']})")
    return "; ".join(parts)


def _run_one_step_chain(
    methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    helper_defs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    assignments: list[dict[str, object]],
    inventory_refs: dict[str, dict[str, int | str]],
) -> list[str]:
    lines = []
    method = methods.get("run_one_step")
    if method is not None:
        lines.append(
            f"- method definition: Scheduler.run_one_step (line {method.lineno}; "
            f"{_known_refs_for_symbol('run_one_step', inventory_refs)})"
        )
    for name in (
        "_zero_v352_scheduler_run_one_step",
        "_zero_scheduler_run_one_step_v8",
        "_zero_scheduler_run_one_step_v16",
    ):
        helper = helper_defs.get(name)
        if helper is None:
            lines.append(f"- helper definition: {name} (<missing>)")
            continue
        lines.append(
            f"- helper definition: {name} (line {helper.lineno}; "
            f"{_known_refs_for_symbol(name, inventory_refs)})"
        )
    for row in assignments:
        if row["attr"] == "run_one_step":
            lines.append(
                f"- binding: {row['target']} = {row['value']} (line {row['line']}; "
                f"{_known_refs_for_symbol(str(row['target']), inventory_refs)})"
            )
    final = [row for row in assignments if row["attr"] == "run_one_step"][-1]
    lines.append(
        f"- final Scheduler.run_one_step binding: {final['value']} (line {final['line']})"
    )
    return lines


def build_report() -> dict[str, object]:
    tree = ast.parse(_read_text(TARGET), filename=str(TARGET))
    scheduler = _scheduler_class(tree)
    methods = _scheduler_methods(scheduler)
    helper_defs = _top_level_functions(tree)
    all_assignments = _scheduler_assignments(tree)
    inventory_refs = _parse_inventory_refs()

    assignments_by_surface: dict[str, list[dict[str, object]]] = {
        surface: [] for surface in SURFACE_ORDER
    }
    for row in all_assignments:
        surface = _surface_for_assignment(row)
        if surface in assignments_by_surface:
            assignments_by_surface[surface].append(row)

    report_lines: list[str] = []
    report_lines.append("Scheduler Mainline Call Graph Audit")
    report_lines.append("")
    report_lines.append(f"repo_root: {ROOT}")
    report_lines.append(f"target: {TARGET.relative_to(ROOT)}")
    report_lines.append(f"inventory: {INVENTORY.relative_to(ROOT)}")
    report_lines.append("audit_mode: static_ast_plus_inventory_refs")
    report_lines.append("")
    report_lines.append("Run One Step Overlay Chain")
    report_lines.append("--------------------------")
    report_lines.extend(
        _run_one_step_chain(
            methods,
            helper_defs,
            assignments_by_surface["run_one_step"],
            inventory_refs,
        )
    )
    report_lines.append("")
    report_lines.append("Surface Call Graphs")
    report_lines.append("-------------------")

    summary_rows: list[dict[str, str]] = []
    for surface in SURFACE_ORDER:
        assignments = sorted(assignments_by_surface[surface], key=lambda row: int(row["line"]))
        seed_names = [str(row["value_name"]) for row in assignments]
        involved_helpers = _walk_helper_closure(seed_names, helper_defs)
        surface_helpers = [
            name
            for name, helper in helper_defs.items()
            if _helper_surface(name) == surface and name not in involved_helpers
        ]
        involved_helpers.extend(
            sorted(surface_helpers, key=lambda name: helper_defs[name].lineno)
        )
        seen_helpers: set[str] = set()
        involved_helpers = [
            name
            for name in involved_helpers
            if not (name in seen_helpers or seen_helpers.add(name))
        ]
        risk, recommendation = _risk_and_recommendation(surface, assignments)
        summary_rows.append(
            {
                "surface": surface,
                "risk": risk,
                "recommendation": recommendation,
                "final_binding": _final_binding_text(assignments),
            }
        )

        report_lines.append(f"{surface}:")
        report_lines.append("  Scheduler.xxx assignment chain:")
        if assignments:
            for row in assignments:
                report_lines.append(
                    f"    - line {row['line']}: {row['target']} = {row['value']} "
                    f"({_known_refs_for_symbol(str(row['target']), inventory_refs)})"
                )
        else:
            report_lines.append("    - <none>")
        report_lines.append("  top-level helper definitions involved:")
        if involved_helpers:
            for name in involved_helpers:
                helper = helper_defs[name]
                report_lines.append(
                    f"    - line {helper.lineno}: {name} "
                    f"({_known_refs_for_symbol(name, inventory_refs)})"
                )
        else:
            report_lines.append("    - <none>")
        report_lines.append("  overlay order by line number:")
        overlay_rows = [
            (int(row["line"]), f"{row['target']} = {row['value']}")
            for row in assignments
        ]
        overlay_rows.extend(
            (helper_defs[name].lineno, f"def {name}(...)") for name in involved_helpers
        )
        if overlay_rows:
            for line_no, label in sorted(overlay_rows):
                report_lines.append(f"    - line {line_no}: {label}")
        else:
            report_lines.append("    - <none>")
        report_lines.append(f"  final active binding: {_final_binding_text(assignments)}")
        report_lines.append("  known active_refs from inventory:")
        if assignments or involved_helpers:
            for row in assignments:
                report_lines.append(
                    f"    - {row['target']}: "
                    f"{_known_refs_for_symbol(str(row['target']), inventory_refs)}"
                )
            for name in involved_helpers:
                report_lines.append(
                    f"    - {name}: {_known_refs_for_symbol(name, inventory_refs)}"
                )
        else:
            report_lines.append("    - <none>")
        report_lines.append(f"  risk_level: {risk}")
        report_lines.append(f"  recommendation: {recommendation}")
        report_lines.append("")

    report_lines.append("Summary")
    report_lines.append("-------")
    for row in summary_rows:
        report_lines.append(
            f"- {row['surface']}: risk={row['risk']}; "
            f"recommendation={row['recommendation']}; final={row['final_binding']}"
        )
    report_lines.append("")
    report_lines.append("Non-Mainline Issues")
    report_lines.append("-------------------")
    report_lines.append("- Static audit only. No production scheduler code was changed.")
    report_lines.append("- Dynamic getattr, imports, and runtime dispatch may hide additional edges.")

    REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return {
        "report": REPORT,
        "summary_rows": summary_rows,
        "run_one_step_final": _final_binding_text(assignments_by_surface["run_one_step"]),
    }


def main() -> int:
    result = build_report()
    print("Scheduler mainline call graph audit complete")
    print(f"report: {Path(result['report']).relative_to(ROOT)}")
    print(f"run_one_step_final: {result['run_one_step_final']}")
    print("surface_summary:")
    for row in result["summary_rows"]:
        print(
            f"- {row['surface']}: risk={row['risk']}, "
            f"recommendation={row['recommendation']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
