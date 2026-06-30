from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "runtime" / "task_runner.py"
REPORT = ROOT / "task_runner_mainline_inventory.txt"

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

CATEGORY_KEYWORDS = {
    "runtime_mode": ("runtime_mode", "runtime mode"),
    "execution": (
        "execute",
        "execution",
        "run",
        "step",
        "command",
        "subprocess",
        "finalize",
        "tick",
    ),
    "registry": ("registry", "operator_registry", "admission", "surface", "capability"),
    "ownership": (
        "ownership",
        "authority",
        "identity",
        "provenance",
        "issuer",
        "lineage",
        "completion",
    ),
    "repair": ("repair", "rollback", "recover", "recovery", "replay"),
    "evidence": (
        "evidence",
        "audit",
        "trace",
        "public_result",
        "persist",
        "reflection",
        "result",
    ),
}


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


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _safe_parse(path: Path) -> ast.Module:
    return ast.parse(_read_text(path), filename=str(path))


def _top_level_import_count(tree: ast.Module) -> int:
    return sum(isinstance(node, (ast.Import, ast.ImportFrom)) for node in tree.body)


def _top_level_classes(tree: ast.Module) -> list[ast.ClassDef]:
    return [node for node in tree.body if isinstance(node, ast.ClassDef)]


def _top_level_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _taskrunner_class(tree: ast.Module) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "TaskRunner":
            return node
    raise RuntimeError("TaskRunner class not found")


def _class_methods(cls: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


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
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _name_of(child.func)
            if name:
                calls.append(name)
    return sorted(set(calls))


def _category_for_private_method(name: str, calls: list[str]) -> str:
    lowered_name = name.lower()
    if lowered_name.startswith("_zero") or re.search(r"(^|_)v\d+", lowered_name):
        return "legacy/zero/v-prefixed"
    if any(token in lowered_name for token in ("legacy", "compat", "stage", "consolidated")):
        return "legacy/zero/v-prefixed"

    haystack = " ".join([lowered_name, *(call.lower() for call in calls)])
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return category
    return "other_private"


def _bucket_for_path(path: Path) -> str:
    rel = _rel(path)
    if rel == _rel(TARGET):
        return "target"
    if rel == _rel(REPORT):
        return "self_report"
    if rel == "tools/task_runner_mainline_inventory.py":
        return "self_tool"
    if rel.startswith("tests/") or "/tests/" in rel:
        return "test"
    if rel.startswith("tools/") or "/tools/" in rel:
        return "tool"
    if rel.startswith("docs/") or "/docs/" in rel:
        return "doc"
    if "/archive/" in rel or rel.startswith("archive/") or "_archive_candidate/" in rel:
        return "archive"
    return "production"


def _definition_patterns(name: str) -> tuple[re.Pattern[str], ...]:
    escaped = re.escape(name)
    return (
        re.compile(rf"^\s*(async\s+def|def)\s+{escaped}\s*\("),
        re.compile(rf"^\s*class\s+{escaped}\s*[\(:]"),
        re.compile(rf"^\s*{escaped}\s*[:=]"),
    )


def _is_definition_line(name: str, line: str) -> bool:
    return any(pattern.search(line) for pattern in _definition_patterns(name))


def _reference_rows(names: list[str]) -> dict[str, list[dict[str, object]]]:
    refs: dict[str, list[dict[str, object]]] = {name: [] for name in names}
    matcher = re.compile(
        r"(?<![A-Za-z0-9_])("
        + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
        + r")(?![A-Za-z0-9_])"
    )

    for path in _iter_text_files():
        try:
            text = _read_text(path)
        except Exception as exc:
            for name in names:
                refs[name].append(
                    {
                        "path": _rel(path),
                        "line": 0,
                        "bucket": "read_error",
                        "is_definition": False,
                        "text": f"<read_error: {exc}>",
                    }
                )
            continue

        if not matcher.search(text):
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            for match in matcher.finditer(line):
                name = match.group(1)
                refs[name].append(
                    {
                        "path": _rel(path),
                        "line": line_no,
                        "bucket": _bucket_for_path(path),
                        "is_definition": _is_definition_line(name, line),
                        "text": stripped[:240],
                    }
                )

    return refs


def _classify_refs(refs: list[dict[str, object]]) -> tuple[str, str]:
    relevant = [
        ref
        for ref in refs
        if not ref["is_definition"]
        and ref["bucket"] not in {"self_tool", "self_report", "read_error"}
    ]
    if not relevant:
        return "A", "no non-definition references found"

    buckets = {str(ref["bucket"]) for ref in relevant}
    if "production" in buckets or "target" in buckets:
        return "C", "production or target-module reference exists"
    if buckets <= {"test", "tool", "doc", "archive"}:
        return "B", "only tests/tools/docs/archive references found"
    return "B", f"non-production references only: {', '.join(sorted(buckets))}"


def _likely_removal_score(name: str, kind: str, refs: list[dict[str, object]]) -> tuple[int, int, str]:
    label, _ = _classify_refs(refs)
    non_def_count = sum(
        1
        for ref in refs
        if not ref["is_definition"]
        and ref["bucket"] not in {"self_tool", "self_report", "read_error"}
    )
    legacy_bonus = 0
    lowered = name.lower()
    if lowered.startswith("_zero") or re.search(r"(^|_)v\d+", lowered):
        legacy_bonus += 4
    if any(token in lowered for token in ("legacy", "compat", "stage", "consolidated")):
        legacy_bonus += 2
    if kind == "top_level_helper":
        legacy_bonus += 1

    label_weight = {"A": 100, "B": 50, "C": 0}[label]
    return label_weight + legacy_bonus, -non_def_count, name


def _format_ref_summary(refs: list[dict[str, object]], *, limit: int = 8) -> list[str]:
    relevant = [
        ref
        for ref in refs
        if not ref["is_definition"] and ref["bucket"] not in {"self_tool", "self_report"}
    ]
    if not relevant:
        return ["    - <none>"]
    lines: list[str] = []
    for ref in relevant[:limit]:
        lines.append(
            f"    - {ref['path']}:{ref['line']} [{ref['bucket']}] {ref['text']}"
        )
    if len(relevant) > limit:
        lines.append(f"    - ... truncated {len(relevant) - limit}")
    return lines


def _write_report() -> dict[str, object]:
    source = _read_text(TARGET)
    lines_in_file = source.splitlines()
    tree = _safe_parse(TARGET)
    taskrunner = _taskrunner_class(tree)

    top_helpers = _top_level_functions(tree)
    classes = _top_level_classes(tree)
    methods = _class_methods(taskrunner)
    private_methods = [method for method in methods if method.name.startswith("_")]

    inventory_items: list[dict[str, object]] = []
    for helper in top_helpers:
        inventory_items.append(
            {
                "name": helper.name,
                "kind": "top_level_helper",
                "line": helper.lineno,
                "category": "top_level_helper",
                "calls": _calls_in(helper),
            }
        )
    for method in private_methods:
        calls = _calls_in(method)
        inventory_items.append(
            {
                "name": method.name,
                "kind": "private_method",
                "line": method.lineno,
                "category": _category_for_private_method(method.name, calls),
                "calls": calls,
            }
        )

    refs = _reference_rows([str(item["name"]) for item in inventory_items])
    for item in inventory_items:
        label, reason = _classify_refs(refs[str(item["name"])])
        item["reference_class"] = label
        item["reference_reason"] = reason
        item["non_definition_refs"] = sum(
            1
            for ref in refs[str(item["name"])]
            if not ref["is_definition"]
            and ref["bucket"] not in {"self_tool", "self_report", "read_error"}
        )

    candidates = sorted(
        inventory_items,
        key=lambda item: _likely_removal_score(
            str(item["name"]),
            str(item["kind"]),
            refs[str(item["name"])],
        ),
        reverse=True,
    )

    grouped_private: dict[str, list[dict[str, object]]] = {
        "runtime_mode": [],
        "execution": [],
        "registry": [],
        "ownership": [],
        "repair": [],
        "evidence": [],
        "legacy/zero/v-prefixed": [],
        "other_private": [],
    }
    for item in inventory_items:
        if item["kind"] == "private_method":
            grouped_private[str(item["category"])].append(item)

    report_lines: list[str] = []
    report_lines.append("TaskRunner Mainline Closure Inventory")
    report_lines.append("")
    report_lines.append(f"repo_root: {ROOT}")
    report_lines.append(f"target: {TARGET.relative_to(ROOT)}")
    report_lines.append(f"total_lines: {len(lines_in_file)}")
    report_lines.append(f"import_count: {_top_level_import_count(tree)}")
    report_lines.append(f"class_count: {len(classes)}")
    report_lines.append(f"method_count_inside_TaskRunner: {len(methods)}")
    report_lines.append(f"top_level_helper_function_count: {len(top_helpers)}")
    report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Top-Level Helper Functions")
    report_lines.append("=" * 80)
    for helper in top_helpers:
        report_lines.append(f"- line {helper.lineno}: {helper.name}")
    if not top_helpers:
        report_lines.append("- <none>")
    report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Private Methods By Category")
    report_lines.append("=" * 80)
    for category in (
        "runtime_mode",
        "execution",
        "registry",
        "ownership",
        "repair",
        "evidence",
        "legacy/zero/v-prefixed",
        "other_private",
    ):
        rows = sorted(grouped_private[category], key=lambda item: int(item["line"]))
        report_lines.append(f"{category}: {len(rows)}")
        if rows:
            for item in rows:
                report_lines.append(
                    f"- line {item['line']}: {item['name']} "
                    f"[refs={item['non_definition_refs']}; class={item['reference_class']}]"
                )
        else:
            report_lines.append("- <none>")
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Likely Dead Helper Candidates")
    report_lines.append("=" * 80)
    report_lines.append("A = no non-definition references found")
    report_lines.append("B = only tests/tools/docs/archive references found")
    report_lines.append("C = production or target-module reference exists; do not remove yet")
    report_lines.append("")
    for item in candidates:
        if item["reference_class"] == "C":
            continue
        name = str(item["name"])
        report_lines.append(
            f"- {name} ({item['kind']}, line {item['line']}, "
            f"category={item['category']}, class={item['reference_class']})"
        )
        report_lines.append(f"  reason: {item['reference_reason']}")
        report_lines.append(f"  non_definition_refs: {item['non_definition_refs']}")
        report_lines.append("  references:")
        report_lines.extend(_format_ref_summary(refs[name]))
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Referenced / Not Removal Candidates")
    report_lines.append("=" * 80)
    for item in candidates:
        if item["reference_class"] != "C":
            continue
        name = str(item["name"])
        report_lines.append(
            f"- {name} ({item['kind']}, line {item['line']}, "
            f"category={item['category']})"
        )
        report_lines.append(f"  reason: {item['reference_reason']}")
        report_lines.append(f"  non_definition_refs: {item['non_definition_refs']}")
        report_lines.append("  sample_references:")
        report_lines.extend(_format_ref_summary(refs[name], limit=5))
        report_lines.append("")

    report_lines.append("=" * 80)
    report_lines.append("Non-Mainline Issues")
    report_lines.append("=" * 80)
    report_lines.append("- Inventory only. No production code was changed.")
    report_lines.append("- Candidates are reference-based only; removal still needs a follow-up package.")
    report_lines.append(
        "- Text search can count dynamic/string references and miss computed getattr usage."
    )
    report_lines.append("")

    REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    return {
        "items": inventory_items,
        "candidates": candidates,
        "report": REPORT,
    }


def main() -> int:
    result = _write_report()
    candidates = [
        item for item in result["candidates"] if item["reference_class"] != "C"
    ][:10]

    print("TaskRunner mainline inventory complete")
    print(f"report: {Path(result['report']).relative_to(ROOT)}")
    print("top_10_likely_removal_candidates:")
    if not candidates:
        print("- <none>")
    for item in candidates:
        print(
            f"- {item['name']} "
            f"({item['kind']}, line {item['line']}, class {item['reference_class']}, "
            f"refs {item['non_definition_refs']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
