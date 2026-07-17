from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "core" / "tasks" / "scheduler.py"
TASK_RUNNER_PATH = ROOT / "core" / "runtime" / "task_runner.py"
REPORT = ROOT / "taskrunner_boundary_inventory.txt"

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

TASKRUNNER_TERMS = (
    "TaskRunner",
    "task_runner",
    "Task runner",
    "task runner",
)

SCHEDULER_TERMS = (
    "Scheduler",
    "scheduler",
)

BOUNDARY_KEYWORDS = (
    "TaskRunner",
    "task_runner",
    "scheduler",
    "run_one_step",
    "execute_step",
    "execute_owned_step",
    "dispatch",
    "runtime_dispatch",
    "authority",
    "execution_authority",
    "runtime_identity",
    "goal_lineage",
    "operator_session",
    "step_executor",
    "handoff",
    "bridge",
)

BOUNDARY_FAMILIES = (
    "scheduler_to_taskrunner",
    "taskrunner_to_scheduler",
    "taskrunner_dispatch",
    "authority_identity",
    "operator_boundary",
    "step_execution",
    "bridge_or_handoff",
    "tests",
    "unknown",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


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
    except Exception:
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


def _owner_map(tree: ast.Module) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _owner_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current = node
    class_name = ""
    function_name = "<module>"
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_name = current.name
        if isinstance(current, ast.ClassDef):
            class_name = current.name
            break
    return f"{class_name}.{function_name}" if class_name else function_name


def _bucket_for_path(path: Path) -> str:
    rel = _rel(path)
    if rel == _rel(SCHEDULER_PATH):
        return "scheduler"
    if rel == _rel(TASK_RUNNER_PATH):
        return "task_runner"
    if rel.startswith("tests/") or "/tests/" in rel:
        return "tests"
    if rel.startswith("tools/") or "/tools/" in rel:
        return "tools"
    if rel.startswith("docs/") or "/docs/" in rel:
        return "docs"
    if rel.startswith("archive/") or "/archive/" in rel or "_archive_candidate/" in rel:
        return "archive"
    if path.suffix.lower() != ".py":
        return "text"
    return "production"


def _classify_family(path: Path, line_text: str, owner: str = "") -> str:
    rel = _rel(path).lower()
    text = " ".join([rel, line_text.lower(), owner.lower()])
    if rel.startswith("tests/") or "/tests/" in rel:
        return "tests"
    if "taskrunner" in text or "task_runner" in text:
        if rel.endswith("core/tasks/scheduler.py") or "scheduler" in owner.lower():
            return "scheduler_to_taskrunner"
    if rel.endswith("core/runtime/task_runner.py") and "scheduler" in text:
        return "taskrunner_to_scheduler"
    if "runtime_dispatch" in text or "dispatcher" in text or "dispatch" in text:
        return "taskrunner_dispatch"
    if "authority" in text or "runtime_identity" in text or "goal_lineage" in text or "execution_authority" in text:
        return "authority_identity"
    if "operator" in text or "operator_session" in text:
        return "operator_boundary"
    if "step_executor" in text or "execute_step" in text or "execute_owned_step" in text:
        return "step_execution"
    if "bridge" in text or "handoff" in text:
        return "bridge_or_handoff"
    return "unknown"


def _text_hits() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in _iter_text_files():
        try:
            text = _read_text(path)
        except Exception:
            continue
        if not any(term in text for term in BOUNDARY_KEYWORDS):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(term in line for term in BOUNDARY_KEYWORDS):
                rows.append(
                    {
                        "path": _rel(path),
                        "line": line_no,
                        "bucket": _bucket_for_path(path),
                        "family": _classify_family(path, line),
                        "text": line.strip()[:260],
                    }
                )
    return rows


def _ast_boundary_rows(path: Path) -> list[dict[str, object]]:
    tree = _safe_parse(path)
    if tree is None:
        return []
    parents = _owner_map(tree)
    rows: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _name_of(node.func)
            if any(term.lower() in name.lower() for term in BOUNDARY_KEYWORDS):
                owner = _owner_name(node, parents)
                line = int(getattr(node, "lineno", 0) or 0)
                rows.append(
                    {
                        "path": _rel(path),
                        "line": line,
                        "owner": owner,
                        "kind": "call",
                        "symbol": name,
                        "family": _classify_family(path, name, owner),
                    }
                )
        elif isinstance(node, ast.Assign):
            targets = [_name_of(target) for target in node.targets]
            value = _name_of(node.value)
            combined = " ".join([*targets, value])
            if any(term.lower() in combined.lower() for term in BOUNDARY_KEYWORDS):
                owner = _owner_name(node, parents)
                line = int(getattr(node, "lineno", 0) or 0)
                rows.append(
                    {
                        "path": _rel(path),
                        "line": line,
                        "owner": owner,
                        "kind": "assign",
                        "symbol": combined,
                        "family": _classify_family(path, combined, owner),
                    }
                )
    return sorted(rows, key=lambda row: (str(row["path"]), int(row["line"]), str(row["kind"])))


def _summarize(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        summary[value] = summary.get(value, 0) + 1
    return dict(sorted(summary.items(), key=lambda item: (-item[1], item[0])))


def _append_rows(report_lines: list[str], rows: list[dict[str, object]], *, limit: int = 120) -> None:
    if not rows:
        report_lines.append("- <none>")
        return
    for row in rows[:limit]:
        if "text" in row:
            report_lines.append(
                f"- {row['path']}:{row['line']} [{row['bucket']}; {row['family']}] {row['text']}"
            )
        else:
            report_lines.append(
                f"- {row['path']}:{row['line']} [{row['kind']}; {row['family']}; owner={row['owner']}] {row['symbol']}"
            )
    if len(rows) > limit:
        report_lines.append(f"- ... truncated {len(rows) - limit}")


def _write_report() -> dict[str, object]:
    text_rows = _text_hits()
    scheduler_ast_rows = _ast_boundary_rows(SCHEDULER_PATH) if SCHEDULER_PATH.exists() else []
    task_runner_ast_rows = _ast_boundary_rows(TASK_RUNNER_PATH) if TASK_RUNNER_PATH.exists() else []
    ast_rows = scheduler_ast_rows + task_runner_ast_rows

    scheduler_to_taskrunner = [
        row for row in text_rows + ast_rows if row.get("family") == "scheduler_to_taskrunner"
    ]
    taskrunner_to_scheduler = [
        row for row in text_rows + ast_rows if row.get("family") == "taskrunner_to_scheduler"
    ]
    unknown_rows = [row for row in text_rows + ast_rows if row.get("family") == "unknown"]

    report_lines: list[str] = []
    report_lines.append("TaskRunner Runtime Boundary Inventory")
    report_lines.append("")
    report_lines.append(f"repo_root: {ROOT}")
    report_lines.append(f"scheduler_path: {SCHEDULER_PATH.relative_to(ROOT)}")
    report_lines.append(f"task_runner_path: {TASK_RUNNER_PATH.relative_to(ROOT)}")
    report_lines.append("scope: inventory only; production code not modified")
    report_lines.append("")

    report_lines.append("Summary")
    report_lines.append("-------")
    report_lines.append(f"text_hits: {len(text_rows)}")
    report_lines.append(f"ast_boundary_rows: {len(ast_rows)}")
    report_lines.append(f"scheduler_ast_rows: {len(scheduler_ast_rows)}")
    report_lines.append(f"task_runner_ast_rows: {len(task_runner_ast_rows)}")
    report_lines.append(f"scheduler_to_taskrunner_rows: {len(scheduler_to_taskrunner)}")
    report_lines.append(f"taskrunner_to_scheduler_rows: {len(taskrunner_to_scheduler)}")
    report_lines.append(f"unknown_rows: {len(unknown_rows)}")
    report_lines.append("")

    report_lines.append("Boundary Family Summary")
    report_lines.append("-----------------------")
    family_summary = _summarize(text_rows + ast_rows, "family")
    for family in BOUNDARY_FAMILIES:
        report_lines.append(f"- {family}: {family_summary.get(family, 0)}")
    report_lines.append("")

    report_lines.append("Bucket Summary")
    report_lines.append("--------------")
    for bucket, count in _summarize(text_rows, "bucket").items():
        report_lines.append(f"- {bucket}: {count}")
    report_lines.append("")

    report_lines.append("Scheduler To TaskRunner")
    report_lines.append("-----------------------")
    _append_rows(report_lines, scheduler_to_taskrunner, limit=160)
    report_lines.append("")

    report_lines.append("TaskRunner To Scheduler")
    report_lines.append("-----------------------")
    _append_rows(report_lines, taskrunner_to_scheduler, limit=160)
    report_lines.append("")

    report_lines.append("TaskRunner Dispatch / Authority / Operator Boundary Rows")
    report_lines.append("--------------------------------------------------------")
    boundary_rows = [
        row
        for row in text_rows + ast_rows
        if row.get("family")
        in {
            "taskrunner_dispatch",
            "authority_identity",
            "operator_boundary",
            "step_execution",
            "bridge_or_handoff",
        }
    ]
    _append_rows(report_lines, boundary_rows, limit=220)
    report_lines.append("")

    report_lines.append("Unknown Boundary Rows")
    report_lines.append("---------------------")
    report_lines.append("Unknown rows are not deletion candidates. They require a follow-up classifier or behavior audit before action.")
    _append_rows(report_lines, unknown_rows, limit=220)
    report_lines.append("")

    report_lines.append("Initial Closure Decision")
    report_lines.append("------------------------")
    report_lines.append("- Do not modify scheduler.py in this package.")
    report_lines.append("- Do not modify task_runner.py in this package.")
    report_lines.append("- Treat Scheduler -> TaskRunner and TaskRunner -> Scheduler references as runtime boundary evidence, not cleanup candidates.")
    report_lines.append("- Any consolidation must be preceded by a behavior audit and targeted contract tests.")
    report_lines.append("")

    report_lines.append("Non-Mainline Issues")
    report_lines.append("-------------------")
    report_lines.append("- Inventory only. Report any unrelated runtime/operator/dispatcher issues in a separate package instead of silently modifying them.")
    report_lines.append("")

    REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    return {
        "report": REPORT,
        "text_hits": len(text_rows),
        "ast_boundary_rows": len(ast_rows),
        "scheduler_ast_rows": len(scheduler_ast_rows),
        "task_runner_ast_rows": len(task_runner_ast_rows),
        "scheduler_to_taskrunner_rows": len(scheduler_to_taskrunner),
        "taskrunner_to_scheduler_rows": len(taskrunner_to_scheduler),
        "unknown_rows": len(unknown_rows),
        "family_summary": family_summary,
    }


def main() -> int:
    result = _write_report()
    print("TaskRunner boundary inventory complete")
    print(f"report: {Path(result['report']).relative_to(ROOT)}")
    print(
        "counts: "
        f"text_hits={result['text_hits']}, "
        f"ast_boundary_rows={result['ast_boundary_rows']}, "
        f"scheduler_ast_rows={result['scheduler_ast_rows']}, "
        f"task_runner_ast_rows={result['task_runner_ast_rows']}, "
        f"scheduler_to_taskrunner_rows={result['scheduler_to_taskrunner_rows']}, "
        f"taskrunner_to_scheduler_rows={result['taskrunner_to_scheduler_rows']}, "
        f"unknown_rows={result['unknown_rows']}"
    )
    print("boundary_family_summary:")
    family_summary = result["family_summary"]
    for family in BOUNDARY_FAMILIES:
        print(f"- {family}: {family_summary.get(family, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
