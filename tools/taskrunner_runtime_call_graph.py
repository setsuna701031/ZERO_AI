from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Iterable, List, Set


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "runtime" / "task_runner.py"
REPORT = ROOT / "taskrunner_runtime_call_graph_report.txt"

ENTRYPOINTS = [
    "run",
    "run_task",
    "run_one_step",
    "run_one_tick",
    "run_task_tick",
    "_run_one_step",
    "execute_owned_step",
    "execute_owned_steps",
    "_run_via_runtime_native_mainline",
]

LEGACY_PREFIXES = (
    "_zero_v702",
    "_zero_v800",
    "_zero_v801",
    "_zero_v810",
    "_zero_stage3b",
    "_stage3b",
    "_taskrunner_consolidated",
)

INTERESTING_TERMS = (
    "run",
    "execute",
    "runtime",
    "dispatch",
    "registry",
    "admission",
    "repair",
    "replay",
    "step",
    "tick",
    "mark_",
    "save",
    "record",
    "rollback",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _parse(path: Path) -> ast.Module:
    return ast.parse(_read_text(path), filename=str(path))


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


def _short_call_name(name: str) -> str:
    if name.startswith("self."):
        return name.split(".", 1)[1]
    return name


def _iter_calls(node: ast.AST) -> List[str]:
    calls: List[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _name_of(child.func)
            if name:
                calls.append(name)
    return calls


def _is_interesting_call(call: str) -> bool:
    text = call.lower()
    return any(term in text for term in INTERESTING_TERMS)


def _collect_functions(tree: ast.Module) -> Dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node
    return funcs


def _collect_edges(
    funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> Dict[str, List[str]]:
    edges: Dict[str, List[str]] = {}

    for name, node in funcs.items():
        calls = []
        for call in _iter_calls(node):
            short = _short_call_name(call)
            if short in funcs or _is_interesting_call(call):
                calls.append(call)

        edges[name] = sorted(set(calls))

    return edges


def _walk_graph(
    start: str,
    funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    edges: Dict[str, List[str]],
    max_depth: int = 8,
) -> List[tuple[int, str, str]]:
    rows: List[tuple[int, str, str]] = []
    seen: Set[tuple[str, int]] = set()

    def visit(name: str, depth: int) -> None:
        if depth > max_depth:
            return

        key = (name, depth)
        if key in seen:
            return
        seen.add(key)

        node = funcs.get(name)
        line = str(getattr(node, "lineno", "?")) if node is not None else "?"
        rows.append((depth, name, line))

        for call in edges.get(name, []):
            short = _short_call_name(call)
            if short in funcs:
                visit(short, depth + 1)

    visit(start, 0)
    return rows


def _legacy_functions(funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef]) -> List[str]:
    return sorted(
        name
        for name in funcs
        if name.startswith(LEGACY_PREFIXES)
    )


def _registry_functions(funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef]) -> List[str]:
    return sorted(
        name
        for name in funcs
        if "registry" in name.lower() or "admit" in name.lower() or "admission" in name.lower()
    )


def _runtime_side_effect_calls(edges: Dict[str, List[str]]) -> Dict[str, List[str]]:
    side_terms = (
        "runtime.mark_",
        "runtime.save",
        "runtime.record",
        "runtime.advance",
        "runtime.rollback",
        "registry",
        "mark_failed",
        "mark_finished",
        "save_runtime_state",
        "record_step_failure",
        "record_engineering",
        "rollback_last_apply",
    )

    out: Dict[str, List[str]] = {}
    for name, calls in edges.items():
        hits = [call for call in calls if any(term in call for term in side_terms)]
        if hits:
            out[name] = hits
    return out


def _format_tree(rows: Iterable[tuple[int, str, str]]) -> List[str]:
    lines: List[str] = []
    for depth, name, line in rows:
        prefix = "  " * depth + ("- " if depth == 0 else "-> ")
        lines.append(f"{prefix}{name}  [line {line}]")
    return lines


def _write_report(
    funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    edges: Dict[str, List[str]],
) -> None:
    lines: List[str] = []

    lines.append("TaskRunner Runtime Call Graph")
    lines.append("")
    lines.append(f"repo_root: {ROOT}")
    lines.append(f"target: {TARGET.relative_to(ROOT)}")
    lines.append(f"functions: {len(funcs)}")
    lines.append("")

    lines.append("=" * 80)
    lines.append("Mainline Entrypoint Graphs")
    lines.append("=" * 80)

    for entry in ENTRYPOINTS:
        lines.append("")
        lines.append(f"[{entry}]")
        if entry not in funcs:
            lines.append("- <missing>")
            continue
        lines.extend(_format_tree(_walk_graph(entry, funcs, edges)))

    lines.append("")
    lines.append("=" * 80)
    lines.append("Direct Call Edges For Mainline Entrypoints")
    lines.append("=" * 80)

    for entry in ENTRYPOINTS:
        lines.append("")
        lines.append(f"- {entry}")
        for call in edges.get(entry, []):
            lines.append(f"  -> {call}")
        if not edges.get(entry):
            lines.append("  -> <none>")

    lines.append("")
    lines.append("=" * 80)
    lines.append("Registry Admission Functions")
    lines.append("=" * 80)

    for name in _registry_functions(funcs):
        node = funcs[name]
        lines.append("")
        lines.append(f"- line {node.lineno}: {name}")
        for call in edges.get(name, []):
            lines.append(f"  -> {call}")
        if not edges.get(name):
            lines.append("  -> <none>")

    lines.append("")
    lines.append("=" * 80)
    lines.append("Legacy Wrapper Functions")
    lines.append("=" * 80)

    legacy = _legacy_functions(funcs)
    if legacy:
        for name in legacy:
            node = funcs[name]
            lines.append("")
            lines.append(f"- line {node.lineno}: {name}")
            for call in edges.get(name, []):
                lines.append(f"  -> {call}")
            if not edges.get(name):
                lines.append("  -> <none>")
    else:
        lines.append("- <none>")

    lines.append("")
    lines.append("=" * 80)
    lines.append("Runtime Side-effect Call Sites")
    lines.append("=" * 80)

    side_effects = _runtime_side_effect_calls(edges)
    for name in sorted(side_effects):
        node = funcs.get(name)
        line = getattr(node, "lineno", "?")
        lines.append("")
        lines.append(f"- line {line}: {name}")
        for call in side_effects[name]:
            lines.append(f"  -> {call}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("Package 32 Findings")
    lines.append("=" * 80)
    lines.append("- This report is inventory/call-graph only. No runtime behavior was changed.")
    lines.append("- Mainline wrappers should converge toward run_task_tick -> _run_one_step.")
    lines.append("- Registry admission wrappers should remain outside the business execution body.")
    lines.append("- Legacy wrapper functions listed here are candidates for Package 33/34 consolidation.")
    lines.append("- Any side-effect call site outside the selected mainline must be reviewed before cleanup.")
    lines.append("")
    lines.append("=" * 80)
    lines.append("Non-mainline Issues")
    lines.append("=" * 80)
    lines.append("- Report any unrelated failures discovered during validation instead of silently skipping them.")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    tree = _parse(TARGET)
    funcs = _collect_functions(tree)
    edges = _collect_edges(funcs)
    _write_report(funcs, edges)
    print(str(REPORT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())