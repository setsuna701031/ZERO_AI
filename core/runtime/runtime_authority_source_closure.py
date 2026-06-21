from __future__ import annotations

"""Static runtime authority source closure audit helpers.

This module is intentionally audit-only. It does not grant authority, execute
runtime actions, mutate files, or replace RuntimeExecutionAuthorityPolicy.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CANONICAL_EXECUTION_AUTHORITY_SOURCE = "RuntimeExecutionAuthorityPolicy"

RUNTIME_AUTHORITY_SOURCE_CLOSURE_TARGETS = (
    "core/runtime/runtime_dispatcher.py",
    "core/runtime/task_runner.py",
    "core/runtime/task_runtime.py",
    "core/runtime/runtime_mutation_gateway.py",
    "core/runtime/governed_mutation_runtime.py",
    "core/runtime/runtime_execution_authority_policy.py",
    "core/runtime/runtime_capability_tokens.py",
)

FORBIDDEN_IMPLICIT_AUTHORITY_PATTERNS = (
    "if is_admin",
    "if trusted",
    "if privileged",
    "if runtime_zone ==",
    "if source ==",
    "authority_status\": \"allowed\"",
    "execution_authority_granted\": True",
    "can_execute_privileged_step\": True",
)

NON_MAINLINE_REPORTING_RULES = (
    "parallel authority system",
    "hidden capability source",
    "fallback authority",
    "wildcard authority",
    "ownership/authority mixed responsibility",
    "evidence/authority mixed responsibility",
)

OBSERVED_NON_MAINLINE_AUTHORITY_SURFACES = (
    {
        "surface": "core/runtime/runtime_mutation_gateway.py",
        "observation": "uses RuntimeAuthorityEvaluator for mutation authority scope, separate from execution authority policy",
        "classification": "mutation_authority_parallel_surface_to_track",
        "blocking": False,
    },
    {
        "surface": "core/runtime/runtime_dispatcher.py",
        "observation": "carries execution_authority metadata but must not be treated as the execution authority decision source",
        "classification": "dispatcher_authority_metadata_surface_to_track",
        "blocking": False,
    },
)


@dataclass(frozen=True)
class AuthoritySourceFinding:
    path: str
    pattern: str
    line_number: int
    line: str
    severity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "pattern": self.pattern,
            "line_number": self.line_number,
            "line": self.line,
            "severity": self.severity,
        }


def audit_runtime_authority_source_closure(
    *,
    root: str | Path = ".",
    targets: Iterable[str] = RUNTIME_AUTHORITY_SOURCE_CLOSURE_TARGETS,
) -> dict[str, object]:
    """Return a passive source-closure audit report.

    Findings are informational unless they prove a second execution-authority
    decision source. Metadata propagation alone is not treated as a blocker.
    """

    root_path = Path(root)
    findings: list[AuthoritySourceFinding] = []
    missing: list[str] = []

    for target in targets:
        path = root_path / target
        if not path.exists():
            missing.append(target)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            for pattern in FORBIDDEN_IMPLICIT_AUTHORITY_PATTERNS:
                if pattern in stripped:
                    findings.append(
                        AuthoritySourceFinding(
                            path=target,
                            pattern=pattern,
                            line_number=line_number,
                            line=stripped,
                            severity=_severity_for(target, stripped),
                        )
                    )

    blocking = [finding for finding in findings if finding.severity == "blocking"]
    return {
        "schema": "zero.runtime_authority_source_closure.audit.v1",
        "canonical_execution_authority_source": CANONICAL_EXECUTION_AUTHORITY_SOURCE,
        "targets": list(targets),
        "missing_targets": missing,
        "findings": [finding.to_dict() for finding in findings],
        "blocking_findings": [finding.to_dict() for finding in blocking],
        "observed_non_mainline_authority_surfaces": list(OBSERVED_NON_MAINLINE_AUTHORITY_SURFACES),
        "non_mainline_issue_reporting_required": True,
        "non_mainline_reporting_rules": list(NON_MAINLINE_REPORTING_RULES),
        "closed": not missing and not blocking,
    }


def _severity_for(path: str, line: str) -> str:
    if path.endswith("runtime_execution_authority_policy.py"):
        return "canonical_policy"
    if "execution_authority_granted" in line or "can_execute_privileged_step" in line:
        return "metadata_observation"
    if "authority_status\": \"allowed\"" in line:
        return "metadata_observation"
    return "blocking"


__all__ = [
    "CANONICAL_EXECUTION_AUTHORITY_SOURCE",
    "FORBIDDEN_IMPLICIT_AUTHORITY_PATTERNS",
    "NON_MAINLINE_REPORTING_RULES",
    "OBSERVED_NON_MAINLINE_AUTHORITY_SURFACES",
    "RUNTIME_AUTHORITY_SOURCE_CLOSURE_TARGETS",
    "AuthoritySourceFinding",
    "audit_runtime_authority_source_closure",
]
