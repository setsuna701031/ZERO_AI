from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


ROOT = Path("core/tasks/scheduler_core")
LARGE_FUNCTION_THRESHOLD = 80

FACADE_PREFIXES = (
    "install_",
    "sync_",
    "run_",
    "handle_",
    "execute_",
    "build_",
    "apply_",
)

MUTATION_MARKERS = (
    "project_runtime_status",
    "mark_repo_task_",
    "sync_blocked_state",
    "sync_unblocked_state",
    "_persist_task_payload",
    "_save_runtime_state",
    "append_history",
    "current_step_index",
    "last_step_result",
    "execution_log",
    "step_results",
)

TRACE_MARKERS = (
    "trace_step",
    "_trace_status",
    "_trace_replan",
    "_save_trace_for_task",
    "ExecutionTrace",
    "emit_scheduler_evidence",
)

RETURN_PAYLOAD_MARKERS = (
    '"ok"',
    "'ok'",
    '"status"',
    "'status'",
    '"task"',
    "'task'",
    '"step_results"',
    "'step_results'",
    '"last_step_result"',
    "'last_step_result'",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _function_end_line(node: ast.AST) -> int:
    return int(getattr(node, "end_lineno", getattr(node, "lineno", 0)) or 0)


def _function_lines(node: ast.AST) -> int:
    start = int(getattr(node, "lineno", 0) or 0)
    end = _function_end_line(node)
    return max(0, end - start + 1)


def _node_source(text_lines: list[str], node: ast.AST) -> str:
    start = int(getattr(node, "lineno", 1) or 1)
    end = _function_end_line(node)
    if start <= 0 or end <= 0 or end < start:
        return ""
    return "\n".join(text_lines[start - 1 : end])


def _count_calls(node: ast.AST) -> int:
    return sum(1 for child in ast.walk(node) if isinstance(child, ast.Call))


def _count_assignments(node: ast.AST) -> int:
    return sum(
        1
        for child in ast.walk(node)
        if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign))
    )


def _count_returns(node: ast.AST) -> int:
    return sum(1 for child in ast.walk(node) if isinstance(child, ast.Return))


def _count_branches(node: ast.AST) -> int:
    return sum(
        1
        for child in ast.walk(node)
        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.Match))
    )


def _contains_any(source: str, markers: tuple[str, ...]) -> bool:
    return any(marker in source for marker in markers)


def _classify_function(name: str, source: str, node: ast.AST) -> str:
    calls = _count_calls(node)
    assigns = _count_assignments(node)
    branches = _count_branches(node)
    returns = _count_returns(node)

    is_facade_name = name.startswith(FACADE_PREFIXES)
    has_mutation = _contains_any(source, MUTATION_MARKERS)
    has_trace = _contains_any(source, TRACE_MARKERS)
    has_payload = _contains_any(source, RETURN_PAYLOAD_MARKERS)

    if is_facade_name and calls >= max(3, assigns) and branches >= 1:
        return "facade/orchestration"
    if has_trace and has_mutation:
        return "trace+mutation flow"
    if has_mutation and branches >= 2:
        return "state mutation flow"
    if has_payload and returns >= 1 and branches >= 1:
        return "return payload flow"
    if calls >= 5 and assigns <= calls:
        return "helper orchestration"
    return "implementation/detail"


def _risk_tags(name: str, source: str, node: ast.AST) -> list[str]:
    tags: list[str] = []

    if name.startswith(FACADE_PREFIXES):
        tags.append("facade-candidate")
    if _contains_any(source, MUTATION_MARKERS):
        tags.append("mutation")
    if _contains_any(source, TRACE_MARKERS):
        tags.append("trace")
    if _contains_any(source, RETURN_PAYLOAD_MARKERS):
        tags.append("return-payload")
    if "except Exception" in source:
        tags.append("broad-except")
    if "scheduler_cls.run_one_step" in source or "_is_repairable_failure" in source:
        tags.append("monkey-patch")
    if "copy.deepcopy" in source:
        tags.append("deepcopy")
    if _count_branches(node) >= 8:
        tags.append("many-branches")

    return tags


def _iter_python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _analyze_file(path: Path) -> list[dict[str, Any]]:
    text = _read_text(path)
    lines = text.splitlines()
    tree = ast.parse(text, filename=str(path))

    rows: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        source = _node_source(lines, node)
        line_count = _function_lines(node)
        name = node.name

        rows.append(
            {
                "file": str(path).replace("\\", "/"),
                "line": int(getattr(node, "lineno", 0) or 0),
                "function": name,
                "lines": line_count,
                "calls": _count_calls(node),
                "assignments": _count_assignments(node),
                "branches": _count_branches(node),
                "returns": _count_returns(node),
                "classification": _classify_function(name, source, node),
                "risk_tags": _risk_tags(name, source, node),
            }
        )

    return rows


def _print_table(headers: list[str], rows: list[list[Any]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(str(value)))

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))

    for row in rows:
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def main() -> int:
    files = _iter_python_files(ROOT)
    all_rows: list[dict[str, Any]] = []

    for path in files:
        try:
            all_rows.extend(_analyze_file(path))
        except SyntaxError as exc:
            all_rows.append(
                {
                    "file": str(path).replace("\\", "/"),
                    "line": getattr(exc, "lineno", 0) or 0,
                    "function": "<syntax-error>",
                    "lines": 0,
                    "calls": 0,
                    "assignments": 0,
                    "branches": 0,
                    "returns": 0,
                    "classification": "syntax-error",
                    "risk_tags": [str(exc)],
                }
            )

    large_rows = sorted(
        [row for row in all_rows if int(row["lines"]) >= LARGE_FUNCTION_THRESHOLD],
        key=lambda row: int(row["lines"]),
        reverse=True,
    )

    print("Scheduler Core Facade Report")
    print(f"Root: {ROOT}")
    print(f"Files: {len(files)}")
    print(f"Functions: {len(all_rows)}")
    print(f"Large function threshold: {LARGE_FUNCTION_THRESHOLD}")
    print()

    print("Large Function Classification")
    _print_table(
        ["file", "line", "function", "lines", "class", "risk_tags"],
        [
            [
                row["file"],
                row["line"],
                row["function"],
                row["lines"],
                row["classification"],
                ",".join(row["risk_tags"]),
            ]
            for row in large_rows[:40]
        ],
    )

    print()
    print("Facade / Orchestration Candidates")
    facade_rows = [
        row
        for row in all_rows
        if row["classification"] in {"facade/orchestration", "helper orchestration"}
        or "facade-candidate" in row["risk_tags"]
    ]
    facade_rows = sorted(facade_rows, key=lambda row: int(row["lines"]), reverse=True)

    _print_table(
        ["file", "line", "function", "lines", "class", "risk_tags"],
        [
            [
                row["file"],
                row["line"],
                row["function"],
                row["lines"],
                row["classification"],
                ",".join(row["risk_tags"]),
            ]
            for row in facade_rows[:40]
        ],
    )

    print()
    print("High Risk Mutation / Trace Functions")
    risk_rows = [
        row
        for row in all_rows
        if "mutation" in row["risk_tags"]
        or "trace" in row["risk_tags"]
        or "monkey-patch" in row["risk_tags"]
    ]
    risk_rows = sorted(
        [row for row in risk_rows if int(row["lines"]) >= 40],
        key=lambda row: int(row["lines"]),
        reverse=True,
    )

    _print_table(
        ["file", "line", "function", "lines", "class", "risk_tags"],
        [
            [
                row["file"],
                row["line"],
                row["function"],
                row["lines"],
                row["classification"],
                ",".join(row["risk_tags"]),
            ]
            for row in risk_rows[:40]
        ],
    )

    print()
    print("Suggested Reading:")
    print("- Prefer not to split trace+mutation flow unless tests directly cover ordering.")
    print("- Prefer facade extraction when helper calls can preserve ordering exactly.")
    print("- Treat monkey-patch installers as high-risk even after helper extraction.")
    print("- Treat return-payload-only builders as low-risk if keys and values remain identical.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())