from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGET_SUFFIXES = {".py"}
IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".test_tmp",
    "workspace",
    "zero_ai_clone",
    "zero_ai_target",
}

KEYWORDS = [
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "os.system",
    "shell=True",
    "ExecutionGuard",
    "command_tool",
    "step_executor",
    "task_runner",
]


def should_skip(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def scan_keywords(path: Path, text: str) -> list[str]:
    hits: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for keyword in KEYWORDS:
            if keyword in line:
                hits.append(f"- `{path.relative_to(ROOT)}`:{lineno} — `{keyword}` — `{line.strip()}`")
    return hits


def scan_shell_true_ast(path: Path, text: str) -> list[str]:
    hits: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return hits

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    hits.append(f"- `{path.relative_to(ROOT)}`:{node.lineno} — AST detected `shell=True`")
    return hits


def main() -> None:
    files = [
        p for p in ROOT.rglob("*")
        if p.is_file()
        and p.suffix in TARGET_SUFFIXES
        and not should_skip(p.relative_to(ROOT))
    ]

    keyword_hits: list[str] = []
    shell_hits: list[str] = []

    for path in sorted(files):
        text = read_text(path)
        keyword_hits.extend(scan_keywords(path, text))
        shell_hits.extend(scan_shell_true_ast(path, text))

    out = ROOT / "docs" / "execution_gateway_preflight_audit.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    content = [
        "# Execution Gateway Preflight Audit",
        "",
        "## Scope",
        "",
        "This audit only scans execution-related entrypoints and command execution patterns.",
        "",
        "No runtime behavior was changed.",
        "",
        "## Keyword Hits",
        "",
        *(keyword_hits or ["No keyword hits found."]),
        "",
        "## AST shell=True Hits",
        "",
        *(shell_hits or ["No AST shell=True hits found."]),
        "",
        "## Risk Classification",
        "",
        "| Area | Risk | Notes |",
        "|---|---:|---|",
        "| Direct subprocess usage | High | Should eventually route through a governed execution gateway. |",
        "| shell=True | High | Requires policy, audit, path safety, and explicit command boundary. |",
        "| command_tool.py | Medium | Candidate gateway or adapter target. |",
        "| step_executor.py | High | Runtime execution path; do not change without contract tests. |",
        "| task_runner.py | High | May bridge scheduler/runtime execution. |",
        "| ExecutionGuard | Low/Medium | Should remain policy boundary, not become executor. |",
        "",
        "## Suggested Consolidation Order",
        "",
        "1. Identify existing safe execution helper, if any.",
        "2. Route low-risk command utility calls through one adapter.",
        "3. Add audit metadata around command execution.",
        "4. Add policy checks before shell execution.",
        "5. Only later migrate step executor command paths.",
        "6. Do not touch scheduler dispatch/tick paths during this phase.",
        "",
        "## Freeze Rule",
        "",
        "This file is diagnostic only. It does not authorize runtime behavior changes.",
        "",
    ]

    out.write_text("\n".join(content), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()