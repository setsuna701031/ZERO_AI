from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "core" / "tasks" / "scheduler.py"
OUTPUT_PATH = ROOT / "scheduler_review_inventory.txt"

REVIEW_KEYWORDS = [
    "approve_review_item",
    "reject_review_item",
    "get_review_queue",
    "review_queue",
    "review_item",
    "review_status",
    "review",
]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _line_col(node: ast.AST) -> Tuple[int, int]:
    return int(getattr(node, "lineno", 0) or 0), int(getattr(node, "col_offset", 0) or 0)


def _safe_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _safe_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _safe_name(node.func)
    if isinstance(node, ast.Subscript):
        return _safe_name(node.value)
    return ""


def _context_for_line(lines: List[str], line_no: int, radius: int = 2) -> str:
    start = max(1, line_no - radius)
    end = min(len(lines), line_no + radius)
    out = []
    for idx in range(start, end + 1):
        marker = ">" if idx == line_no else " "
        out.append(f"{marker} {idx}: {lines[idx - 1].rstrip()}")
    return "\n".join(out)


def _classify_line(path: Path, line_no: int, text: str) -> str:
    lower_path = str(path).replace("\\", "/").lower()
    lower = text.lower()

    if "/tests/" in lower_path or lower_path.startswith("tests/"):
        return "test only"
    if "deprecated" in lower or "legacy" in lower:
        return "legacy/deprecated"
    if "inventory" in lower_path or "inventory" in lower:
        return "inventory only"
    if "runtime" in lower_path or "dispatcher" in lower_path or "operator" in lower_path:
        return "runtime/operator/dispatcher adjacent"
    return "source"


def _scan_repo_text() -> Dict[str, List[Tuple[str, int, str, str]]]:
    results: Dict[str, List[Tuple[str, int, str, str]]] = {key: [] for key in REVIEW_KEYWORDS}

    skip_dirs = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        "node_modules",
        ".venv",
        "venv",
    }

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".txt", ".md", ".json", ".yaml", ".yml"}:
            continue

        try:
            text = _read_text(path)
        except Exception:
            continue

        rel = path.relative_to(ROOT).as_posix()
        for line_no, line in enumerate(text.splitlines(), start=1):
            for key in REVIEW_KEYWORDS:
                if key in line:
                    results[key].append(
                        (
                            rel,
                            line_no,
                            line.strip(),
                            _classify_line(path.relative_to(ROOT), line_no, line),
                        )
                    )

    return results


def _scan_scheduler_ast() -> Dict[str, List[Tuple[int, str, str]]]:
    text = _read_text(SCHEDULER_PATH)
    tree = ast.parse(text)

    definitions: Dict[str, List[Tuple[int, str, str]]] = {
        "approve_review_item": [],
        "reject_review_item": [],
        "get_review_queue": [],
    }
    calls: Dict[str, List[Tuple[int, str, str]]] = {
        "approve_review_item": [],
        "reject_review_item": [],
        "get_review_queue": [],
    }

    parents: Dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def owner_name(node: ast.AST) -> str:
        current = node
        while current in parents:
            current = parents[current]
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current.name
        return "<module>"

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in definitions:
                line, _ = _line_col(node)
                definitions[node.name].append((line, node.name, owner_name(node)))

        if isinstance(node, ast.Call):
            name = _safe_name(node.func)
            leaf = name.split(".")[-1]
            if leaf in calls:
                line, _ = _line_col(node)
                calls[leaf].append((line, name, owner_name(node)))

    return {"definitions": definitions, "calls": calls}


def _status_for(entries: List[Tuple[str, int, str, str]]) -> str:
    active = [
        item
        for item in entries
        if item[3] not in {"test only", "inventory only", "legacy/deprecated"}
    ]
    if active:
        return "ACTIVE"
    if entries:
        return "LEGACY/TEST_ONLY"
    return "DEAD"


def main() -> None:
    repo_hits = _scan_repo_text()
    ast_hits = _scan_scheduler_ast()

    lines: List[str] = []
    lines.append("Scheduler Review API Inventory")
    lines.append("")
    lines.append(f"scheduler_path: {SCHEDULER_PATH}")
    lines.append(f"output_path: {OUTPUT_PATH}")
    lines.append("scope: inventory only; scheduler.py not modified")
    lines.append("")

    for api in ["approve_review_item", "reject_review_item", "get_review_queue"]:
        entries = repo_hits.get(api, [])
        definitions = ast_hits["definitions"].get(api, [])
        calls = ast_hits["calls"].get(api, [])
        status = _status_for(entries)

        lines.append(api)
        lines.append("-" * len(api))
        lines.append(f"status: {status}")
        lines.append("")

        lines.append("definitions in scheduler.py:")
        if definitions:
            for line_no, name, owner in definitions:
                lines.append(f"- line {line_no}: {name} owner={owner}")
        else:
            lines.append("- none")
        lines.append("")

        lines.append("calls in scheduler.py AST:")
        if calls:
            for line_no, name, owner in calls:
                lines.append(f"- line {line_no}: call={name} owner={owner}")
        else:
            lines.append("- none")
        lines.append("")

        lines.append("repo text hits:")
        if entries:
            for rel, line_no, text, classification in entries:
                lines.append(f"- {rel}:{line_no}: [{classification}] {text}")
        else:
            lines.append("- none")
        lines.append("")

    lines.append("Review keyword sweep")
    lines.append("--------------------")
    for key in REVIEW_KEYWORDS:
        entries = repo_hits.get(key, [])
        lines.append(f"{key}: {len(entries)} hit(s)")
    lines.append("")

    lines.append("Dependency summary")
    lines.append("------------------")
    for api in ["approve_review_item", "reject_review_item", "get_review_queue"]:
        entries = repo_hits.get(api, [])
        tests = [e for e in entries if e[3] == "test only"]
        runtime = [e for e in entries if "runtime" in e[0].lower()]
        operator = [e for e in entries if "operator" in e[0].lower()]
        dispatcher = [e for e in entries if "dispatcher" in e[0].lower()]
        lines.append(f"{api}:")
        lines.append(f"  test_dependency: {bool(tests)} ({len(tests)})")
        lines.append(f"  runtime_dependency: {bool(runtime)} ({len(runtime)})")
        lines.append(f"  operator_dependency: {bool(operator)} ({len(operator)})")
        lines.append(f"  dispatcher_dependency: {bool(dispatcher)} ({len(dispatcher)})")
    lines.append("")

    lines.append("Non-Mainline Issues Found")
    lines.append("-------------------------")
    lines.append("inventory only; inspect hits above before scheduling any code changes")
    lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(OUTPUT_PATH))


if __name__ == "__main__":
    main()