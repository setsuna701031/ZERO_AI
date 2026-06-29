from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

TARGETS = [
    ROOT / "core" / "runtime" / "task_runner.py",
    ROOT / "core" / "runtime" / "runtime_dispatcher.py",
    ROOT / "core" / "runtime" / "runtime_execution_fabric.py",
    ROOT / "core" / "runtime" / "runtime_recovery_orchestrator.py",
    ROOT / "core" / "runtime" / "runtime_state_machine.py",
]

KEYWORDS = (
    "execute",
    "runtime",
    "dispatch",
    "replay",
    "repair",
    "recover",
    "tick",
    "registry",
    "admission",
    "owned_step",
)

REPORT = ROOT / "taskrunner_runtime_inventory_report.txt"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


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


def _iter_calls(node: ast.AST) -> list[str]:
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _name_of(child.func)
            if name:
                calls.append(name)
    return calls


def _looks_relevant(name: str, calls: list[str]) -> bool:
    text = " ".join([name, *calls]).lower()
    return any(key in text for key in KEYWORDS)


def _classify(name: str, calls: list[str]) -> dict[str, Any]:
    text = " ".join([name, *calls]).lower()

    return {
        "is_mainline_candidate": any(
            key in text
            for key in (
                "execute",
                "execute_owned_step",
                "tick",
                "runtime_dispatcher",
                "dispatch",
            )
        )
        and not any(key in name.lower() for key in ("legacy", "compat")),
        "is_legacy_or_compat": any(
            key in text for key in ("legacy", "compat", "fallback", "shim")
        ),
        "has_side_effect_hint": any(
            key in text
            for key in (
                "write",
                "append",
                "save",
                "delete",
                "remove",
                "mkdir",
                "open",
                "commit",
                "record",
                "mark_",
                "setattr",
                "registry",
            )
        ),
        "mentions_registry_admission": any(
            key in text
            for key in (
                "registry",
                "admission",
                "operator_registry",
                "registry_service",
            )
        ),
    }


def _inventory_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return [
            {
                "file": str(path.relative_to(ROOT)),
                "line": 0,
                "kind": "missing",
                "name": "<missing>",
                "calls": [],
                "classification": {},
            }
        ]

    tree = _safe_parse(path)
    if tree is None:
        return [
            {
                "file": str(path.relative_to(ROOT)),
                "line": 0,
                "kind": "syntax_error",
                "name": "<syntax_error>",
                "calls": [],
                "classification": {},
            }
        ]

    rows: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = _iter_calls(node)
            if not _looks_relevant(node.name, calls):
                continue

            rows.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "line": node.lineno,
                    "kind": "function",
                    "name": node.name,
                    "calls": sorted(set(calls)),
                    "classification": _classify(node.name, calls),
                }
            )

        elif isinstance(node, ast.ClassDef):
            if any(key in node.name.lower() for key in KEYWORDS):
                rows.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "line": node.lineno,
                        "kind": "class",
                        "name": node.name,
                        "calls": [],
                        "classification": _classify(node.name, []),
                    }
                )

    return sorted(rows, key=lambda item: (item["file"], item["line"], item["name"]))


def _write_report(rows: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append("TaskRunner Runtime Mainline Inventory")
    lines.append("")
    lines.append(f"repo_root: {ROOT}")
    lines.append(f"targets: {len(TARGETS)}")
    lines.append(f"entries: {len(rows)}")
    lines.append("")

    by_file: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_file.setdefault(row["file"], []).append(row)

    for file_name, file_rows in by_file.items():
        lines.append("=" * 80)
        lines.append(file_name)
        lines.append("=" * 80)

        for row in file_rows:
            cls = row["classification"]
            calls = row["calls"]

            lines.append("")
            lines.append(f"- line {row['line']}: {row['kind']} {row['name']}")
            lines.append(f"  mainline_candidate: {cls.get('is_mainline_candidate')}")
            lines.append(f"  legacy_or_compat: {cls.get('is_legacy_or_compat')}")
            lines.append(f"  side_effect_hint: {cls.get('has_side_effect_hint')}")
            lines.append(f"  registry_admission_hint: {cls.get('mentions_registry_admission')}")

            interesting_calls = [
                call
                for call in calls
                if any(key in call.lower() for key in KEYWORDS)
            ]
            lines.append("  relevant_calls:")
            if interesting_calls:
                for call in interesting_calls[:40]:
                    lines.append(f"    - {call}")
                if len(interesting_calls) > 40:
                    lines.append(f"    - ... truncated {len(interesting_calls) - 40}")
            else:
                lines.append("    - <none>")

    lines.append("")
    lines.append("=" * 80)
    lines.append("Non-mainline Issues")
    lines.append("=" * 80)
    lines.append("- Inventory only. No code behavior was changed.")
    lines.append("- Any entry marked legacy_or_compat=True should be reviewed in Package 32/33.")
    lines.append("- Any entry with side_effect_hint=True but registry_admission_hint=False should be reviewed before cleanup.")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    rows: list[dict[str, Any]] = []
    for target in TARGETS:
        rows.extend(_inventory_file(target))

    _write_report(rows)
    print(str(REPORT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())