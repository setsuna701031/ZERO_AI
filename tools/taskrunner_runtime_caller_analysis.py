from __future__ import annotations

import ast
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "runtime" / "task_runner.py"
REPORT = ROOT / "taskrunner_runtime_caller_analysis_report.txt"

LEGACY_PREFIXES = (
    "_zero_v702",
    "_zero_v800",
    "_zero_v801",
    "_zero_v810",
    "_zero_stage3b",
    "_stage3b",
    "_taskrunner_consolidated",
)

MAINLINE_NAMES = {
    "run",
    "run_task",
    "run_one_step",
    "run_one_tick",
    "run_task_tick",
    "_run_one_step",
    "execute_owned_step",
    "execute_owned_steps",
    "_run_via_runtime_native_mainline",
}

RUNTIME_TERMS = (
    "run",
    "tick",
    "step",
    "execute",
    "runtime",
    "dispatch",
    "registry",
    "admit",
    "admission",
    "repair",
    "replay",
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


def _short_name(name: str) -> str:
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

    for caller, node in funcs.items():
        callees: List[str] = []
        for raw_call in _iter_calls(node):
            short = _short_name(raw_call)
            if short in funcs:
                callees.append(short)
        edges[caller] = sorted(set(callees))

    return edges


def _reverse_edges(edges: Dict[str, List[str]]) -> Dict[str, List[str]]:
    reverse: Dict[str, List[str]] = defaultdict(list)

    for caller, callees in edges.items():
        for callee in callees:
            reverse[callee].append(caller)

    return {key: sorted(set(value)) for key, value in reverse.items()}


def _is_legacy(name: str) -> bool:
    return name.startswith(LEGACY_PREFIXES)


def _is_runtime_related(name: str) -> bool:
    text = name.lower()
    return any(term in text for term in RUNTIME_TERMS)


def _reachable_from(
    starts: Iterable[str],
    edges: Dict[str, List[str]],
) -> Set[str]:
    visited: Set[str] = set()
    stack = list(starts)

    while stack:
        name = stack.pop()
        if name in visited:
            continue
        visited.add(name)

        for callee in edges.get(name, []):
            if callee not in visited:
                stack.append(callee)

    return visited


def _line(funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef], name: str) -> int | str:
    node = funcs.get(name)
    return getattr(node, "lineno", "?") if node is not None else "?"


def _format_name(
    funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    name: str,
) -> str:
    return f"{name} [line {_line(funcs, name)}]"


def _write_section(lines: List[str], title: str) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)


def _write_report(
    funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    edges: Dict[str, List[str]],
    reverse: Dict[str, List[str]],
) -> None:
    lines: List[str] = []

    all_funcs = set(funcs)
    legacy_funcs = sorted(name for name in all_funcs if _is_legacy(name))
    runtime_funcs = sorted(name for name in all_funcs if _is_runtime_related(name))
    reachable = _reachable_from((name for name in MAINLINE_NAMES if name in funcs), edges)

    caller_counts = Counter({name: len(reverse.get(name, [])) for name in all_funcs})
    callee_counts = Counter({name: len(edges.get(name, [])) for name in all_funcs})

    dead_legacy = [
        name
        for name in legacy_funcs
        if not reverse.get(name)
    ]

    unreachable_legacy_from_mainline = [
        name
        for name in legacy_funcs
        if name not in reachable
    ]

    runtime_no_callers = [
        name
        for name in runtime_funcs
        if not reverse.get(name) and name not in MAINLINE_NAMES
    ]

    hubs = sorted(
        all_funcs,
        key=lambda name: (caller_counts[name], callee_counts[name], name),
        reverse=True,
    )

    lines.append("TaskRunner Runtime Caller Analysis")
    lines.append("")
    lines.append(f"repo_root: {ROOT}")
    lines.append(f"target: {TARGET.relative_to(ROOT)}")
    lines.append(f"functions: {len(all_funcs)}")
    lines.append(f"runtime_related_functions: {len(runtime_funcs)}")
    lines.append(f"legacy_functions: {len(legacy_funcs)}")
    lines.append(f"reachable_from_mainline: {len(reachable)}")
    lines.append(f"dead_legacy_no_callers: {len(dead_legacy)}")
    lines.append(f"unreachable_legacy_from_mainline: {len(unreachable_legacy_from_mainline)}")
    lines.append("")

    _write_section(lines, "Runtime Hub Functions")
    lines.append("")
    lines.append("Top functions by direct caller count:")
    for name in hubs[:40]:
        if caller_counts[name] <= 0:
            continue
        lines.append(
            f"- {_format_name(funcs, name)} | callers={caller_counts[name]} | callees={callee_counts[name]}"
        )
        callers = reverse.get(name, [])
        for caller in callers[:12]:
            lines.append(f"  <- {_format_name(funcs, caller)}")
        if len(callers) > 12:
            lines.append(f"  <- ... truncated {len(callers) - 12}")

    _write_section(lines, "Mainline Caller Map")
    for name in sorted(MAINLINE_NAMES):
        lines.append("")
        lines.append(f"- {_format_name(funcs, name)}")
        callers = reverse.get(name, [])
        callees = edges.get(name, [])
        lines.append("  callers:")
        if callers:
            for caller in callers:
                lines.append(f"    <- {_format_name(funcs, caller)}")
        else:
            lines.append("    <- <none>")
        lines.append("  callees:")
        if callees:
            for callee in callees:
                lines.append(f"    -> {_format_name(funcs, callee)}")
        else:
            lines.append("    -> <none>")

    _write_section(lines, "Legacy Wrapper Caller Map")
    if legacy_funcs:
        for name in legacy_funcs:
            lines.append("")
            lines.append(f"- {_format_name(funcs, name)}")
            lines.append(f"  reachable_from_mainline: {name in reachable}")
            callers = reverse.get(name, [])
            callees = edges.get(name, [])
            lines.append("  callers:")
            if callers:
                for caller in callers:
                    lines.append(f"    <- {_format_name(funcs, caller)}")
            else:
                lines.append("    <- <none>")
            lines.append("  callees:")
            if callees:
                for callee in callees:
                    lines.append(f"    -> {_format_name(funcs, callee)}")
            else:
                lines.append("    -> <none>")
    else:
        lines.append("- <none>")

    _write_section(lines, "Dead Legacy Candidates")
    if dead_legacy:
        for name in dead_legacy:
            lines.append(f"- {_format_name(funcs, name)}")
    else:
        lines.append("- <none>")

    _write_section(lines, "Unreachable Legacy From Mainline")
    if unreachable_legacy_from_mainline:
        for name in unreachable_legacy_from_mainline:
            lines.append(f"- {_format_name(funcs, name)}")
    else:
        lines.append("- <none>")

    _write_section(lines, "Runtime-related Functions Without Direct Callers")
    if runtime_no_callers:
        for name in runtime_no_callers:
            lines.append(f"- {_format_name(funcs, name)}")
    else:
        lines.append("- <none>")

    _write_section(lines, "Suggested Package 34 Targets")
    lines.append("- Do not delete anything from this report alone.")
    lines.append("- First inspect dead legacy candidates manually.")
    lines.append("- Prioritize wrappers that meet all conditions:")
    lines.append("  1. legacy prefix")
    lines.append("  2. no direct callers")
    lines.append("  3. unreachable from mainline")
    lines.append("  4. no test references")
    lines.append("- After that, run targeted tests before any cleanup.")

    _write_section(lines, "Non-mainline Issues")
    lines.append("- This package only analyzes callers. No runtime behavior was changed.")
    lines.append("- Any unrelated failures discovered during validation must be reported explicitly.")

    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    tree = _parse(TARGET)
    funcs = _collect_functions(tree)
    edges = _collect_edges(funcs)
    reverse = _reverse_edges(edges)
    _write_report(funcs, edges, reverse)
    print(str(REPORT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())