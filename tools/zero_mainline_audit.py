from __future__ import annotations

"""
ZERO Mainline Audit

Purpose:
- Inventory legacy runtime/status/authority bypass patterns.
- Produce machine-readable JSON and human-readable Markdown reports.
- Does not modify source files.
- Designed for Windows PowerShell from repo root: E:\zero_ai

Non-Mainline Issue Reporting:
- Findings outside the current closure target are still reported.
- The tool does not silently skip non-mainline issues; it records them under
  "non_mainline_issue_report" when they are suspicious but not directly fatal.
"""

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_INCLUDE_DIRS = ("core", "cli", "tests", "tools")
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "env",
    "node_modules",
    "workspace",
    "runtime",
    "dist",
    "build",
}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml"}


@dataclass(frozen=True)
class AuditPattern:
    category: str
    name: str
    severity: str
    regex: str
    note: str
    non_mainline: bool = False


@dataclass
class Finding:
    category: str
    name: str
    severity: str
    path: str
    line: int
    text: str
    note: str
    non_mainline: bool = False


@dataclass
class FileShape:
    path: str
    lines: int
    functions: int = 0
    classes: int = 0
    max_function_lines: int = 0
    large_file: bool = False
    giant_file: bool = False


@dataclass
class AuditReport:
    generated_at: str
    repo_root: str
    scanned_files: int
    scanned_lines: int
    findings: list[Finding] = field(default_factory=list)
    file_shapes: list[FileShape] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "scanned_files": self.scanned_files,
            "scanned_lines": self.scanned_lines,
            "findings": [asdict(f) for f in self.findings],
            "file_shapes": [asdict(s) for s in self.file_shapes],
            "summary": summarize_findings(self.findings, self.file_shapes),
            "non_mainline_issue_report": [
                asdict(f) for f in self.findings if f.non_mainline
            ],
        }


PATTERNS: tuple[AuditPattern, ...] = (
    AuditPattern(
        "runtime_status_alias",
        "legacy_success_status",
        "medium",
        r"""(?<!["'])\bsuccess\b(?!["'])|["']success["']""",
        "Found legacy status value 'success'. Prefer canonical runtime status such as finished/completed only where the contract explicitly allows it.",
    ),
    AuditPattern(
        "runtime_status_alias",
        "legacy_error_status",
        "medium",
        r"""(?<!["'])\berror\b(?!["'])|["']error["']""",
        "Found legacy status value 'error'. Verify canonical status mapping and ownership.",
    ),
    AuditPattern(
        "runtime_status_alias",
        "legacy_done_status",
        "low",
        r"""(?<!["'])\bdone\b(?!["'])|["']done["']""",
        "Found legacy status value 'done'. Verify it is not a runtime state alias leaking into mainline.",
        non_mainline=True,
    ),
    AuditPattern(
        "authority_bypass",
        "direct_file_write",
        "high",
        r"""\.(write_text|write_bytes|open)\s*\(""",
        "Direct file write/open detected. Verify it is test/tool-only or routed through governed mutation authority.",
    ),
    AuditPattern(
        "authority_bypass",
        "raw_open_write_mode",
        "high",
        r"""open\s*\([^,\n]+,\s*["'][wa+x]""",
        "Raw open() write/append mode detected. Verify this is not a runtime authority bypass.",
    ),
    AuditPattern(
        "authority_bypass",
        "subprocess_or_os_system",
        "high",
        r"""\b(subprocess\.(run|Popen|call|check_call|check_output)|os\.system)\s*\(""",
        "Command execution detected. Verify execution authority/capability is checked.",
    ),
    AuditPattern(
        "authority_bypass",
        "shell_true",
        "critical",
        r"""shell\s*=\s*True""",
        "shell=True detected. This needs explicit justification and authority guard.",
    ),
    AuditPattern(
        "dispatcher_bypass",
        "direct_step_executor_call",
        "medium",
        r"""\bstep_executor\.(execute|run|dispatch|execute_step)\s*\(""",
        "Direct StepExecutor call detected. Verify it flows through runtime dispatcher/governed endpoint.",
    ),
    AuditPattern(
        "dispatcher_bypass",
        "direct_task_runner_call",
        "medium",
        r"""\btask_runner\.(run|execute|dispatch)\s*\(""",
        "Direct TaskRunner call detected. Verify owner and capability propagation.",
    ),
    AuditPattern(
        "legacy_route",
        "monkey_patch_reference",
        "high",
        r"""monkey[_ -]?patch|MonkeyPatch|setattr\s*\(""",
        "Monkey patch or dynamic setattr detected. Verify it is test-only or documented legacy bridge.",
    ),
    AuditPattern(
        "legacy_route",
        "deprecated_reference",
        "low",
        r"""deprecated|legacy|compat|fallback""",
        "Legacy/deprecated/fallback reference found. Inventory whether this path is still reachable.",
        non_mainline=True,
    ),
    AuditPattern(
        "evidence_gap",
        "todo_fixme",
        "low",
        r"""\b(TODO|FIXME|HACK|XXX)\b""",
        "Unresolved engineering marker found.",
        non_mainline=True,
    ),
    AuditPattern(
        "identity_lineage_gap",
        "manual_session_id_assignment",
        "medium",
        r"""["']?(session_id|runtime_session_id|goal_lineage_id)["']?\s*[:=]\s*["']""",
        "Manual identity/lineage assignment detected. Verify canonical lineage contract is used.",
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iter_source_files(root: Path, include_dirs: Iterable[str]) -> Iterable[Path]:
    include_roots = [root / item for item in include_dirs]
    for include_root in include_roots:
        if not include_root.exists():
            continue
        if include_root.is_file():
            yield include_root
            continue
        for path in include_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part in DEFAULT_EXCLUDE_DIRS for part in path.parts):
                continue
            yield path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def is_test_or_tool(path: Path) -> bool:
    parts = set(path.parts)
    return "tests" in parts or "tools" in parts


def adjusted_finding(pattern: AuditPattern, path: Path, rel: str, line_no: int, line: str) -> Finding:
    severity = pattern.severity
    non_mainline = pattern.non_mainline

    if is_test_or_tool(path) and pattern.category in {"authority_bypass", "dispatcher_bypass", "legacy_route"}:
        severity = "info"
        non_mainline = True

    return Finding(
        category=pattern.category,
        name=pattern.name,
        severity=severity,
        path=rel,
        line=line_no,
        text=line.strip()[:260],
        note=pattern.note,
        non_mainline=non_mainline,
    )


def scan_patterns(root: Path, path: Path, text: str) -> list[Finding]:
    rel = str(path.relative_to(root)).replace("\\", "/")
    findings: list[Finding] = []
    lines = text.splitlines()
    compiled = [(p, re.compile(p.regex, re.IGNORECASE)) for p in PATTERNS]

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") and "TODO" not in stripped and "FIXME" not in stripped:
            continue
        for pattern, rx in compiled:
            if rx.search(line):
                findings.append(adjusted_finding(pattern, path, rel, i, line))
    return findings


def shape_file(root: Path, path: Path, text: str) -> FileShape:
    rel = str(path.relative_to(root)).replace("\\", "/")
    lines = len(text.splitlines())
    shape = FileShape(
        path=rel,
        lines=lines,
        large_file=lines >= 1000,
        giant_file=lines >= 5000,
    )

    if path.suffix.lower() != ".py":
        return shape

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return shape

    function_lengths: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            shape.functions += 1
            if hasattr(node, "end_lineno") and node.end_lineno:
                function_lengths.append(max(0, node.end_lineno - node.lineno + 1))
        elif isinstance(node, ast.ClassDef):
            shape.classes += 1

    shape.max_function_lines = max(function_lengths or [0])
    return shape


def summarize_findings(findings: list[Finding], shapes: list[FileShape]) -> dict:
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_file: dict[str, int] = {}

    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
        by_category[finding.category] = by_category.get(finding.category, 0) + 1
        by_file[finding.path] = by_file.get(finding.path, 0) + 1

    return {
        "total_findings": len(findings),
        "by_severity": dict(sorted(by_severity.items())),
        "by_category": dict(sorted(by_category.items())),
        "top_files": sorted(by_file.items(), key=lambda item: item[1], reverse=True)[:25],
        "large_files": [asdict(s) for s in shapes if s.large_file],
        "giant_files": [asdict(s) for s in shapes if s.giant_file],
    }


def render_markdown(report: AuditReport) -> str:
    data = report.to_dict()
    summary = data["summary"]
    findings = report.findings

    critical_high = [f for f in findings if f.severity in {"critical", "high"}]
    non_mainline = [f for f in findings if f.non_mainline]

    lines: list[str] = []
    lines.append("# ZERO Mainline Audit Report")
    lines.append("")
    lines.append(f"- Generated at: `{report.generated_at}`")
    lines.append(f"- Repo root: `{report.repo_root}`")
    lines.append(f"- Scanned files: `{report.scanned_files}`")
    lines.append(f"- Scanned lines: `{report.scanned_lines}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total findings: `{summary['total_findings']}`")
    lines.append(f"- Severity: `{json.dumps(summary['by_severity'], ensure_ascii=False)}`")
    lines.append(f"- Category: `{json.dumps(summary['by_category'], ensure_ascii=False)}`")
    lines.append("")

    lines.append("## Critical / High Findings")
    lines.append("")
    if not critical_high:
        lines.append("No critical/high findings detected by this static audit.")
    else:
        lines.append("| Severity | Category | File | Line | Finding |")
        lines.append("|---|---|---:|---:|---|")
        for f in critical_high[:200]:
            safe_text = f.text.replace("|", "\\|")
            lines.append(f"| {f.severity} | {f.category} | `{f.path}` | {f.line} | {f.name}: {safe_text} |")
        if len(critical_high) > 200:
            lines.append(f"\nTruncated: {len(critical_high) - 200} additional critical/high findings are in JSON.")

    lines.append("")
    lines.append("## Large File Inventory")
    lines.append("")
    large = summary["large_files"]
    if not large:
        lines.append("No files >= 1000 lines.")
    else:
        lines.append("| File | Lines | Functions | Classes | Max Function Lines |")
        lines.append("|---|---:|---:|---:|---:|")
        for item in sorted(large, key=lambda x: x["lines"], reverse=True):
            lines.append(
                f"| `{item['path']}` | {item['lines']} | {item['functions']} | {item['classes']} | {item['max_function_lines']} |"
            )

    lines.append("")
    lines.append("## Top Finding Files")
    lines.append("")
    top_files = summary["top_files"]
    if not top_files:
        lines.append("No findings.")
    else:
        lines.append("| File | Findings |")
        lines.append("|---|---:|")
        for path, count in top_files:
            lines.append(f"| `{path}` | {count} |")

    lines.append("")
    lines.append("## Non-Mainline Issue Report")
    lines.append("")
    if not non_mainline:
        lines.append("No non-mainline issues detected by this static audit.")
    else:
        lines.append("| Severity | Category | File | Line | Finding |")
        lines.append("|---|---|---:|---:|---|")
        for f in non_mainline[:200]:
            safe_text = f.text.replace("|", "\\|")
            lines.append(f"| {f.severity} | {f.category} | `{f.path}` | {f.line} | {f.name}: {safe_text} |")
        if len(non_mainline) > 200:
            lines.append(f"\nTruncated: {len(non_mainline) - 200} additional non-mainline findings are in JSON.")

    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("This audit is intentionally conservative. A finding is not automatically a bug.")
    lines.append("Use it to decide which legacy paths require tests, removal, or explicit documentation.")
    lines.append("")
    lines.append("Recommended next action:")
    lines.append("")
    lines.append("1. Review all critical/high findings outside `tests/` and `tools/`.")
    lines.append("2. For each real runtime bypass, either route through the governed authority path or document why it is safe.")
    lines.append("3. For each legacy status alias, confirm it is canonicalized before it reaches RuntimeState/ExecutionResult.")
    lines.append("4. Keep non-mainline findings visible instead of silently skipping them.")
    lines.append("")
    return "\n".join(lines)


def run_audit(root: Path, include_dirs: Iterable[str]) -> AuditReport:
    files = sorted(set(iter_source_files(root, include_dirs)))
    findings: list[Finding] = []
    shapes: list[FileShape] = []
    scanned_lines = 0

    for path in files:
        text = read_text(path)
        scanned_lines += len(text.splitlines())
        shapes.append(shape_file(root, path, text))
        findings.extend(scan_patterns(root, path, text))

    findings.sort(key=lambda f: (severity_order(f.severity), f.path, f.line, f.category, f.name))
    shapes.sort(key=lambda s: (-s.lines, s.path))

    return AuditReport(
        generated_at=utc_now(),
        repo_root=str(root),
        scanned_files=len(files),
        scanned_lines=scanned_lines,
        findings=findings,
        file_shapes=shapes,
    )


def severity_order(value: str) -> int:
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return order.get(value, 99)


def main() -> int:
    parser = argparse.ArgumentParser(description="ZERO mainline static audit")
    parser.add_argument("--root", default=".", help="Repository root. Default: current directory.")
    parser.add_argument(
        "--include",
        nargs="*",
        default=list(DEFAULT_INCLUDE_DIRS),
        help="Directories/files to scan. Default: core cli tests tools",
    )
    parser.add_argument(
        "--out-dir",
        default="docs/architecture/mainline_audit",
        help="Output directory for audit reports.",
    )
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Exit 2 if critical findings are detected outside tests/tools.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_dir = (root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report = run_audit(root, args.include)
    data = report.to_dict()

    json_path = out_dir / "zero_mainline_audit_report.json"
    md_path = out_dir / "zero_mainline_audit_report.md"

    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"ZERO Mainline Audit complete")
    print(f"Scanned files : {report.scanned_files}")
    print(f"Scanned lines : {report.scanned_lines}")
    print(f"Findings      : {len(report.findings)}")
    print(f"JSON          : {json_path}")
    print(f"Markdown      : {md_path}")

    if args.fail_on_critical:
        critical_runtime = [
            f for f in report.findings
            if f.severity == "critical" and not is_test_or_tool(root / f.path)
        ]
        if critical_runtime:
            print(f"Critical runtime findings: {len(critical_runtime)}")
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
