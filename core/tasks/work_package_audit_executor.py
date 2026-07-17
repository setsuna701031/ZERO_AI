from __future__ import annotations

"""
Read-only Work Package Audit Executor v1.

This executor is deliberately conservative:
- It reads only the declared scope files.
- It writes only the declared markdown report path.
- It never modifies scanned source files.
- It performs simple textual marker classification, not code transformation.

This is the first step toward Codex-like work package intake for ZERO without
opening mutation authority too early.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.tasks.work_package_contract import WorkPackageRequest


SCHEMA = "zero.work_package.readonly_audit_result.v1"


HIGH_RISK_MARKERS = (
    "except TypeError",
    "previous_result",
    "last_step_result",
    "llm_fallback",
    "legacy_enqueue",
    "legacy_tool_plan",
)

MEDIUM_RISK_MARKERS = (
    "fallback",
    "legacy",
    "compatibility",
)

LOW_RISK_MARKERS = (
    "adapter",
    "chat(",
    "generate(",
    "ask(",
)


@dataclass(frozen=True)
class AuditFinding:
    path: str
    line: int
    marker: str
    text: str
    risk: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "marker": self.marker,
            "text": self.text,
            "risk": self.risk,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WorkPackageAuditResult:
    ok: bool
    schema: str
    package_id: str
    report_path: str
    scanned_paths: tuple[str, ...]
    missing_paths: tuple[str, ...] = field(default_factory=tuple)
    findings: tuple[AuditFinding, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema": self.schema,
            "package_id": self.package_id,
            "report_path": self.report_path,
            "scanned_paths": list(self.scanned_paths),
            "missing_paths": list(self.missing_paths),
            "finding_count": len(self.findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _repo_path(repo_root: Path, relative_path: str) -> Path:
    root = repo_root.resolve()
    candidate = (root / relative_path).resolve()
    if root not in (candidate, *candidate.parents):
        raise ValueError(f"path_escapes_repo:{relative_path}")
    return candidate


def _risk_for_marker(marker: str, line_text: str) -> tuple[str, str]:
    lowered = line_text.lower()
    marker_lower = marker.lower()

    if marker in HIGH_RISK_MARKERS or marker_lower in lowered and marker in ("previous_result", "last_step_result"):
        return ("high", "possible active execution-state or contract-bypass path")

    if marker in MEDIUM_RISK_MARKERS:
        if "false" in lowered and "fallback_used" in lowered:
            return ("low", "status metadata records fallback state but does not prove fallback execution")
        if "comment" in lowered:
            return ("low", "comment-like marker; inspect manually only if nearby code is active")
        return ("medium", "possible historical compatibility or fallback path")

    if marker in LOW_RISK_MARKERS:
        return ("low", "adapter/tooling marker; verify boundary ownership if it appears in execution flow")

    return ("medium", "matched audit marker")


def _line_contains_marker(line: str, marker: str) -> bool:
    if marker.endswith("("):
        return marker in line
    return marker.lower() in line.lower()


def scan_work_package_scope(*, repo_root: Path, request: WorkPackageRequest) -> WorkPackageAuditResult:
    """Scan declared package files and return an in-memory audit result."""

    scanned: list[str] = []
    missing: list[str] = []
    findings: list[AuditFinding] = []

    for relative_path in request.scope_paths:
        path = _repo_path(repo_root, relative_path)
        if not path.exists():
            missing.append(relative_path)
            continue
        if not path.is_file():
            missing.append(relative_path)
            continue

        scanned.append(relative_path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for marker in request.markers:
                if not _line_contains_marker(line, marker):
                    continue
                risk, reason = _risk_for_marker(marker, line)
                findings.append(
                    AuditFinding(
                        path=relative_path,
                        line=line_no,
                        marker=marker,
                        text=line.strip(),
                        risk=risk,
                        reason=reason,
                    )
                )

    return WorkPackageAuditResult(
        ok=not missing,
        schema=SCHEMA,
        package_id=request.package_id,
        report_path=request.report_path,
        scanned_paths=tuple(scanned),
        missing_paths=tuple(missing),
        findings=tuple(findings),
    )


def _findings_by_risk(findings: tuple[AuditFinding, ...], risk: str) -> list[AuditFinding]:
    return [finding for finding in findings if finding.risk == risk]


def render_audit_report(*, request: WorkPackageRequest, result: WorkPackageAuditResult) -> str:
    """Render a markdown report for operator review."""

    high = _findings_by_risk(result.findings, "high")
    medium = _findings_by_risk(result.findings, "medium")
    low = _findings_by_risk(result.findings, "low")

    lines: list[str] = [
        f"# {request.title}",
        "",
        f"- Package ID: `{request.package_id}`",
        f"- Schema: `{request.to_dict().get('schema')}`",
        f"- Mode: `read-only audit`",
        f"- Mutation allowed: `false`",
        f"- Report path: `{request.report_path}`",
        "",
        "## Scope",
        "",
    ]

    for path in request.scope_paths:
        status = "missing" if path in result.missing_paths else "scanned"
        lines.append(f"- `{path}` — {status}")

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Scanned files: {len(result.scanned_paths)}",
            f"- Missing files: {len(result.missing_paths)}",
            f"- Findings: {len(result.findings)}",
            f"- High risk: {len(high)}",
            f"- Medium risk: {len(medium)}",
            f"- Low risk: {len(low)}",
            "",
            "## High-risk findings",
            "",
        ]
    )

    if high:
        for finding in high:
            lines.append(f"- `{finding.path}:{finding.line}` `{finding.marker}` — {finding.reason}")
            lines.append(f"  - `{finding.text}`")
    else:
        lines.append("- None.")

    lines.extend(["", "## Medium-risk findings", ""])

    if medium:
        for finding in medium:
            lines.append(f"- `{finding.path}:{finding.line}` `{finding.marker}` — {finding.reason}")
            lines.append(f"  - `{finding.text}`")
    else:
        lines.append("- None.")

    lines.extend(["", "## Low-risk / review-only findings", ""])

    if low:
        for finding in low:
            lines.append(f"- `{finding.path}:{finding.line}` `{finding.marker}` — {finding.reason}")
            lines.append(f"  - `{finding.text}`")
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Recommended next action",
            "",
        ]
    )

    if high:
        first = high[0]
        lines.append(f"Start with `{first.path}` around line {first.line}.")
        lines.append("Do not patch broadly; inspect whether this is active execution flow or state/reporting metadata.")
    elif medium:
        first = medium[0]
        lines.append(f"Review `{first.path}` around line {first.line}` first.")
    else:
        lines.append("No obvious active hidden-path marker was detected in this package.")

    if request.instructions:
        lines.extend(["", "## Operator instructions", "", request.instructions])

    lines.append("")
    return "\n".join(lines)


def execute_readonly_audit_package(*, repo_root: Path, request: WorkPackageRequest) -> WorkPackageAuditResult:
    """Execute a read-only audit package and write its report."""

    if request.kind != "readonly_audit":
        raise ValueError(f"unsupported_work_package_kind:{request.kind}")

    result = scan_work_package_scope(repo_root=repo_root, request=request)
    report = render_audit_report(request=request, result=result)

    report_path = _repo_path(repo_root, request.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    return result


__all__ = [
    "AuditFinding",
    "SCHEMA",
    "WorkPackageAuditResult",
    "execute_readonly_audit_package",
    "render_audit_report",
    "scan_work_package_scope",
]
