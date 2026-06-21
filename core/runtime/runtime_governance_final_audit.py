from __future__ import annotations

"""Passive final audit for the runtime governance closure stack.

This module does not grant authority, issue capability, mutate state, write
persistence, or repair runtime records.  It verifies that the closure packages
which make up the runtime governance graph are present, documented, and covered
by validation commands.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

RUNTIME_GOVERNANCE_FINAL_AUDIT_SCHEMA = "zero.runtime_governance_final_audit.v1"

GOVERNANCE_FLOW = (
    "execution_capability_unification",
    "authority_source_closure",
    "capability_propagation_closure",
    "identity_closure",
    "ownership_closure",
    "mutation_closure",
    "evidence_closure",
    "persistence_closure",
    "governance_graph_closure",
)

FINAL_AUDIT_REQUIRED_FILES = (
    "docs/architecture/runtime_execution_capability_unification.md",
    "tests/test_runtime_execution_capability_unification_audit.py",
    "docs/architecture/runtime_authority_source_closure.md",
    "tests/test_runtime_authority_source_closure.py",
    "docs/architecture/runtime_capability_propagation_closure.md",
    "tests/test_runtime_capability_propagation_closure.py",
    "docs/architecture/runtime_identity_closure.md",
    "tests/test_runtime_identity_closure.py",
    "docs/architecture/runtime_ownership_closure.md",
    "tests/test_runtime_ownership_closure.py",
    "docs/architecture/runtime_mutation_closure.md",
    "tests/test_runtime_mutation_closure.py",
    "docs/architecture/runtime_evidence_closure.md",
    "tests/test_runtime_evidence_closure.py",
    "docs/architecture/runtime_persistence_closure.md",
    "tests/test_runtime_persistence_closure.py",
    "docs/architecture/runtime_governance_graph_closure.md",
    "tests/test_runtime_governance_graph_closure.py",
)

BYPASS_MARKERS = (
    "parallel governance graph",
    "hidden governance source",
    "legacy governance path",
    "cross-layer drift",
    "resume drift",
    "continuation drift",
    "replan drift",
    "authority bypass",
    "capability bypass",
    "identity bypass",
    "ownership bypass",
    "mutation bypass",
    "evidence bypass",
    "persistence bypass",
)

_SENTINELS = ("unknown", "default", "legacy", "runtime", "system", "fallback", "wildcard", "unsealed")


@dataclass(frozen=True)
class RuntimeGovernanceAuditTarget:
    name: str
    doc_path: str
    test_path: str
    upstream: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "doc_path": self.doc_path,
            "test_path": self.test_path,
            "upstream": list(self.upstream),
        }


GOVERNANCE_COVERAGE_MATRIX: tuple[RuntimeGovernanceAuditTarget, ...] = (
    RuntimeGovernanceAuditTarget(
        "execution_capability_unification",
        "docs/architecture/runtime_execution_capability_unification.md",
        "tests/test_runtime_execution_capability_unification_audit.py",
    ),
    RuntimeGovernanceAuditTarget(
        "authority_source_closure",
        "docs/architecture/runtime_authority_source_closure.md",
        "tests/test_runtime_authority_source_closure.py",
        ("execution_capability_unification",),
    ),
    RuntimeGovernanceAuditTarget(
        "capability_propagation_closure",
        "docs/architecture/runtime_capability_propagation_closure.md",
        "tests/test_runtime_capability_propagation_closure.py",
        ("authority_source_closure",),
    ),
    RuntimeGovernanceAuditTarget(
        "identity_closure",
        "docs/architecture/runtime_identity_closure.md",
        "tests/test_runtime_identity_closure.py",
        ("capability_propagation_closure",),
    ),
    RuntimeGovernanceAuditTarget(
        "ownership_closure",
        "docs/architecture/runtime_ownership_closure.md",
        "tests/test_runtime_ownership_closure.py",
        ("identity_closure",),
    ),
    RuntimeGovernanceAuditTarget(
        "mutation_closure",
        "docs/architecture/runtime_mutation_closure.md",
        "tests/test_runtime_mutation_closure.py",
        ("ownership_closure",),
    ),
    RuntimeGovernanceAuditTarget(
        "evidence_closure",
        "docs/architecture/runtime_evidence_closure.md",
        "tests/test_runtime_evidence_closure.py",
        ("mutation_closure", "identity_closure"),
    ),
    RuntimeGovernanceAuditTarget(
        "persistence_closure",
        "docs/architecture/runtime_persistence_closure.md",
        "tests/test_runtime_persistence_closure.py",
        ("evidence_closure",),
    ),
    RuntimeGovernanceAuditTarget(
        "governance_graph_closure",
        "docs/architecture/runtime_governance_graph_closure.md",
        "tests/test_runtime_governance_graph_closure.py",
        (
            "execution_capability_unification",
            "authority_source_closure",
            "capability_propagation_closure",
            "identity_closure",
            "ownership_closure",
            "mutation_closure",
            "evidence_closure",
            "persistence_closure",
        ),
    ),
)

REGRESSION_COMMANDS = (
    "pytest -q tests/test_runtime_governance_graph_closure.py",
    "pytest -q tests/test_runtime_mutation_closure.py tests/test_runtime_ownership_closure.py tests/test_runtime_persistence_closure.py tests/test_runtime_evidence_closure.py tests/test_runtime_identity_closure.py tests/test_runtime_capability_propagation_closure.py tests/test_runtime_authority_source_closure.py tests/test_runtime_execution_capability_unification_audit.py",
    "python -m compileall core/runtime core/evidence core/goals core/tasks core/session core/adaptive tests",
    "git diff --check",
)


def governance_coverage_matrix() -> tuple[RuntimeGovernanceAuditTarget, ...]:
    return GOVERNANCE_COVERAGE_MATRIX


def _read_text(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    lower = text.lower()
    return any(marker.lower() in lower for marker in markers)


def run_runtime_governance_final_audit(root: str | Path = ".") -> dict[str, object]:
    """Return a passive final-audit report for the closure stack.

    The report intentionally separates hard failures from mandatory findings.
    Missing documents/tests are failures.  Missing non-mainline sections or
    sentinel-risk references are findings so they stay visible without turning
    the final audit into a repair layer.
    """

    root_path = Path(root)
    missing: list[str] = []
    sealed: list[str] = []
    findings: list[dict[str, str]] = []

    for target in GOVERNANCE_COVERAGE_MATRIX:
        doc_file = root_path / target.doc_path
        test_file = root_path / target.test_path
        if not doc_file.exists():
            missing.append(target.doc_path)
        if not test_file.exists():
            missing.append(target.test_path)
        if not doc_file.exists() or not test_file.exists():
            continue

        sealed.append(target.name)
        doc_text = doc_file.read_text(encoding="utf-8").lower()
        test_text = test_file.read_text(encoding="utf-8").lower()
        combined = doc_text + "\n" + test_text

        if "non-mainline" not in doc_text:
            findings.append({
                "target": target.name,
                "finding": "missing_explicit_non_mainline_section",
                "path": target.doc_path,
            })
        if not _contains_any(combined, ("drift", "bypass", "fallback", "parallel", "remint", "reissue")):
            findings.append({
                "target": target.name,
                "finding": "closure_lacks_visible_drift_or_bypass_terms",
                "path": target.test_path,
            })
        if not _contains_any(combined, _SENTINELS):
            findings.append({
                "target": target.name,
                "finding": "sentinel_identity_or_governance_values_not_visible",
                "path": target.doc_path,
            })

    flow_names = tuple(target.name for target in GOVERNANCE_COVERAGE_MATRIX)
    duplicate_names = sorted({name for name in flow_names if flow_names.count(name) > 1})
    if duplicate_names:
        findings.append({"target": "coverage_matrix", "finding": "duplicate_target_names", "path": ",".join(duplicate_names)})

    command_text = "\n".join(REGRESSION_COMMANDS)
    for target in GOVERNANCE_COVERAGE_MATRIX:
        if target.test_path not in command_text:
            findings.append({
                "target": target.name,
                "finding": "missing_from_regression_commands",
                "path": target.test_path,
            })

    return {
        "schema": RUNTIME_GOVERNANCE_FINAL_AUDIT_SCHEMA,
        "valid": not missing,
        "flow": list(GOVERNANCE_FLOW),
        "sealed_targets": sealed,
        "missing": missing,
        "findings": findings,
        "coverage_matrix": [target.to_dict() for target in GOVERNANCE_COVERAGE_MATRIX],
        "regression_commands": list(REGRESSION_COMMANDS),
        "non_mainline_watch_markers": list(BYPASS_MARKERS),
    }


def assert_runtime_governance_final_audit_closed(root: str | Path = ".") -> dict[str, object]:
    report = run_runtime_governance_final_audit(root)
    if not report["valid"]:
        missing = ", ".join(str(item) for item in report["missing"])
        raise ValueError(f"runtime_governance_final_audit_missing:{missing}")
    return report
