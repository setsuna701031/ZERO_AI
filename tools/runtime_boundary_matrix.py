from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "runtime_boundary_matrix.txt"

TARGETS = {
    "scheduler": ROOT / "core" / "tasks" / "scheduler.py",
    "task_runner": ROOT / "core" / "runtime" / "task_runner.py",
    "dispatcher": ROOT / "core" / "runtime" / "runtime_dispatcher.py",
    "operator": ROOT / "core" / "runtime" / "work_package_operator.py",
}

SKIP_DIRS = {
    ".git",
    ".agents",
    ".codex",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "workspace",
    "cache",
    "data",
    "logs",
    "memory",
    "run",
    "htmlcov",
    "dist",
    "build",
}

TEXT_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".ps1",
    ".bat",
    ".sh",
}

BOUNDARY_TERMS = {
    "authority": ("authority", "execution_authority", "runtime_authority"),
    "identity": ("identity", "runtime_identity", "session_id", "runtime_session_id", "lineage"),
    "ownership": ("ownership", "owner", "owned", "claim"),
    "recovery": ("recovery", "recover", "repair", "rollback", "resume"),
    "dispatch": ("dispatch", "dispatcher", "dispatch_request"),
    "operator": ("operator", "work_package", "package"),
    "step_execution": ("step_executor", "execute_step", "run_step", "handler"),
    "queue": ("queue", "enqueue", "dequeue", "pending"),
    "evidence": ("evidence", "audit", "trace", "record"),
    "bridge": ("bridge", "handoff", "adapter", "gateway"),
}

COMPONENT_HINTS = {
    "scheduler": ("scheduler", "Scheduler", "core.tasks.scheduler"),
    "task_runner": ("taskrunner", "task_runner", "TaskRunner", "core.runtime.task_runner"),
    "dispatcher": ("dispatcher", "RuntimeDispatcher", "runtime_dispatcher"),
    "operator": ("operator", "RuntimeWorkPackageOperator", "work_package_operator"),
}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def _iter_text_files() -> Iterable[Path]:
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if _is_skipped(path):
            continue
        if not _is_text_file(path):
            continue
        yield path


def _safe_parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(_read_text(path), filename=str(path))
    except SyntaxError:
        return None


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


def _calls_in(node: ast.AST) -> list[tuple[int, str]]:
    calls: list[tuple[int, str]] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _name_of(child.func)
            if name:
                calls.append((int(getattr(child, "lineno", 0) or 0), name))
    return sorted(set(calls), key=lambda row: (row[0], row[1]))


def _defs_in(path: Path) -> list[dict[str, object]]:
    tree = _safe_parse(path)
    if tree is None:
        return []
    rows: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            rows.append(
                {
                    "path": _rel(path),
                    "line": int(getattr(node, "lineno", 0) or 0),
                    "kind": type(node).__name__,
                    "name": node.name,
                    "calls": _calls_in(node) if not isinstance(node, ast.ClassDef) else [],
                }
            )
    return sorted(rows, key=lambda row: (int(row["line"]), str(row["name"])))


def _component_for_text(text: str) -> set[str]:
    found: set[str] = set()
    for component, hints in COMPONENT_HINTS.items():
        for hint in hints:
            if hint.lower() in text.lower():
                found.add(component)
                break
    return found


def _family_for_text(text: str) -> str:
    lowered = text.lower()
    for family, terms in BOUNDARY_TERMS.items():
        if any(term.lower() in lowered for term in terms):
            return family
    return "uncategorized"


def _scan_cross_component_text() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in _iter_text_files():
        rel = _rel(path)
        try:
            text = _read_text(path)
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            components = _component_for_text(line)
            if len(components) < 2:
                continue
            rows.append(
                {
                    "path": rel,
                    "line": line_no,
                    "components": sorted(components),
                    "family": _family_for_text(line),
                    "text": line.strip()[:240],
                }
            )
    return rows


def _scan_target_ast_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for component, path in TARGETS.items():
        if not path.exists():
            rows.append(
                {
                    "component": component,
                    "path": _rel(path),
                    "line": 0,
                    "symbol": "<missing>",
                    "kind": "missing",
                    "call": "",
                    "target_component": "",
                    "family": "missing",
                }
            )
            continue

        for definition in _defs_in(path):
            calls = definition.get("calls", [])
            if not isinstance(calls, list):
                continue
            for line_no, call_name in calls:
                targets = _component_for_text(call_name)
                if not targets:
                    continue
                for target in sorted(targets):
                    if target == component:
                        continue
                    rows.append(
                        {
                            "component": component,
                            "path": definition["path"],
                            "line": line_no,
                            "symbol": definition["name"],
                            "kind": definition["kind"],
                            "call": call_name,
                            "target_component": target,
                            "family": _family_for_text(" ".join([str(definition["name"]), call_name])),
                        }
                    )
    return sorted(rows, key=lambda row: (str(row["component"]), str(row["target_component"]), int(row["line"])))


def _boundary_status(row: dict[str, object]) -> str:
    family = str(row.get("family") or "")
    component = str(row.get("component") or "")
    target = str(row.get("target_component") or "")

    if family in {"authority", "identity", "ownership", "recovery"}:
        return "boundary_candidate"
    if family in {"bridge", "dispatch", "operator"}:
        return "boundary_bridge"
    if component == "operator" and target == "scheduler":
        return "boundary_leak_review"
    if component == target:
        return "internal"
    return "boundary_adapter_or_reference"


def _write_report() -> dict[str, object]:
    ast_rows = _scan_target_ast_rows()
    text_rows = _scan_cross_component_text()

    status_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    direction_counts: dict[str, int] = {}

    for row in ast_rows:
        status = _boundary_status(row)
        row["status"] = status
        status_counts[status] = status_counts.get(status, 0) + 1
        family = str(row["family"])
        family_counts[family] = family_counts.get(family, 0) + 1
        direction = f"{row['component']} -> {row['target_component']}"
        direction_counts[direction] = direction_counts.get(direction, 0) + 1

    lines: list[str] = []
    lines.append("Runtime Boundary Matrix")
    lines.append("")
    lines.append("Scope")
    lines.append("-----")
    lines.append("Inventory only. No production code modified.")
    lines.append("Boundary chain: Scheduler -> TaskRunner -> Dispatcher -> Operator")
    lines.append("")

    lines.append("Targets")
    lines.append("-------")
    for name, path in TARGETS.items():
        lines.append(f"- {name}: {_rel(path)} exists={path.exists()}")
    lines.append("")

    lines.append("Summary")
    lines.append("-------")
    lines.append(f"ast_boundary_rows: {len(ast_rows)}")
    lines.append(f"text_cross_component_rows: {len(text_rows)}")
    lines.append("")

    lines.append("Direction Counts")
    lines.append("----------------")
    if direction_counts:
        for key in sorted(direction_counts):
            lines.append(f"- {key}: {direction_counts[key]}")
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Family Counts")
    lines.append("-------------")
    if family_counts:
        for key in sorted(family_counts):
            lines.append(f"- {key}: {family_counts[key]}")
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Status Counts")
    lines.append("-------------")
    if status_counts:
        for key in sorted(status_counts):
            lines.append(f"- {key}: {status_counts[key]}")
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Boundary Matrix Rows")
    lines.append("--------------------")
    if ast_rows:
        for row in ast_rows:
            lines.append(
                f"- {row['component']} -> {row['target_component']} | "
                f"{row['path']}:{row['line']} | symbol={row['symbol']} | "
                f"call={row['call']} | family={row['family']} | status={row['status']}"
            )
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Cross Component Text Samples")
    lines.append("----------------------------")
    if text_rows:
        for row in text_rows[:200]:
            lines.append(
                f"- {row['path']}:{row['line']} | "
                f"components={','.join(row['components'])} | family={row['family']} | {row['text']}"
            )
        if len(text_rows) > 200:
            lines.append(f"- ... truncated {len(text_rows) - 200}")
    else:
        lines.append("- <none>")
    lines.append("")

    lines.append("Non-Mainline Issues")
    lines.append("-------------------")
    lines.append("- Inventory only. No production code was changed.")
    lines.append("- Cross-component text rows can include tests, docs, reports, and string references.")
    lines.append("- Boundary leak rows are review candidates, not automatic defects.")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return {
        "report": REPORT,
        "ast_boundary_rows": len(ast_rows),
        "text_cross_component_rows": len(text_rows),
        "direction_counts": direction_counts,
        "family_counts": family_counts,
        "status_counts": status_counts,
    }


def main() -> int:
    result = _write_report()
    print("Runtime boundary matrix complete")
    print(f"report: {Path(result['report']).relative_to(ROOT)}")
    print(
        "counts: "
        f"ast_boundary_rows={result['ast_boundary_rows']}, "
        f"text_cross_component_rows={result['text_cross_component_rows']}"
    )
    print("direction_counts:")
    if result["direction_counts"]:
        for key in sorted(result["direction_counts"]):
            print(f"- {key}: {result['direction_counts'][key]}")
    else:
        print("- <none>")
    print("family_counts:")
    if result["family_counts"]:
        for key in sorted(result["family_counts"]):
            print(f"- {key}: {result['family_counts'][key]}")
    else:
        print("- <none>")
    print("status_counts:")
    if result["status_counts"]:
        for key in sorted(result["status_counts"]):
            print(f"- {key}: {result['status_counts'][key]}")
    else:
        print("- <none>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
