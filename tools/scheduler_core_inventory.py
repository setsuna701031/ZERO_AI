from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


ROOT = Path("core/tasks/scheduler_core")
FACADE_PREFIXES = ("install_", "sync_", "run_", "handle_")


@dataclass(frozen=True)
class FunctionInfo:
    file: str
    name: str
    line: int
    lines: int


@dataclass(frozen=True)
class FileInfo:
    file: str
    lines: int
    funcs: int
    max_function: str
    max_lines: int


def _line_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8-sig")
    if not text:
        return 0
    return len(text.splitlines())


def _function_lines(node: ast.AST) -> int:
    start = getattr(node, "lineno", 0)
    end = getattr(node, "end_lineno", start)
    return max(0, end - start + 1)


def _scan_file(path: Path) -> tuple[FileInfo, list[FunctionInfo]]:
    relative = path.as_posix()
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=relative)
    functions: list[FunctionInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(
                FunctionInfo(
                    file=relative,
                    name=node.name,
                    line=node.lineno,
                    lines=_function_lines(node),
                )
            )

    largest = max(functions, key=lambda item: item.lines, default=None)
    return (
        FileInfo(
            file=relative,
            lines=_line_count(path),
            funcs=len(functions),
            max_function=largest.name if largest else "",
            max_lines=largest.lines if largest else 0,
        ),
        functions,
    )


def _print_table(headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(str(value)))

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(str(value).ljust(widths[index]) for index, value in enumerate(row)))


def main() -> None:
    if not ROOT.exists():
        raise SystemExit(f"Missing scheduler core directory: {ROOT}")

    files: list[FileInfo] = []
    functions: list[FunctionInfo] = []

    for path in sorted(ROOT.glob("*.py")):
        file_info, function_info = _scan_file(path)
        files.append(file_info)
        functions.extend(function_info)

    print("Scheduler Core Inventory")
    print(f"Root: {ROOT.as_posix()}")
    print(f"Files: {len(files)}")
    print(f"Functions: {len(functions)}")
    print()

    print("Per-file Inventory")
    _print_table(
        ("file", "lines", "funcs", "max_function", "max_lines"),
        [(item.file, item.lines, item.funcs, item.max_function, item.max_lines) for item in files],
    )
    print()

    print("Top 20 Largest Files")
    _print_table(
        ("file", "lines", "funcs"),
        [(item.file, item.lines, item.funcs) for item in sorted(files, key=lambda item: item.lines, reverse=True)[:20]],
    )
    print()

    print("Top 20 Largest Functions")
    _print_table(
        ("file", "line", "function", "lines"),
        [
            (item.file, item.line, item.name, item.lines)
            for item in sorted(functions, key=lambda item: item.lines, reverse=True)[:20]
        ],
    )
    print()

    print("Facade Candidates")
    facade_candidates = [item for item in functions if item.name.startswith(FACADE_PREFIXES)]
    _print_table(
        ("file", "line", "function", "lines"),
        [(item.file, item.line, item.name, item.lines) for item in sorted(facade_candidates, key=lambda item: item.name)],
    )


if __name__ == "__main__":
    main()
