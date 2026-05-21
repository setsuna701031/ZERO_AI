from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Any

from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


@dataclass(frozen=True)
class RuntimeBypassFinding:
    file_path: str
    line_number: int
    rule_id: str
    severity: str
    message: str
    line: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_bypass_finding",
            "file_path": self.file_path,
            "line_number": self.line_number,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
        }


@dataclass(frozen=True)
class RuntimeBypassRule:
    rule_id: str
    pattern: str
    message: str
    severity: str = "error"
    allowed_modules: tuple[str, ...] = ()

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_bypass_rule",
            "rule_id": self.rule_id,
            "pattern": self.pattern,
            "message": self.message,
            "severity": self.severity,
            "allowed_modules": list(self.allowed_modules),
        }


DEFAULT_BYPASS_RULES: tuple[RuntimeBypassRule, ...] = (
    RuntimeBypassRule(
        rule_id="direct_seal_verification",
        pattern=r"\bverify_runtime_seal\s*\(",
        message="seal verification must flow through RuntimeArtifactGate outside seal/gate tests",
        allowed_modules=("runtime_seal.py", "runtime_artifact_gate.py"),
    ),
    RuntimeBypassRule(
        rule_id="direct_abi_validation",
        pattern=r"\bvalidate_abi\s*\(",
        message="ABI validation must flow through RuntimeArtifactGate outside ABI/gate tests",
        allowed_modules=("runtime_abi.py", "runtime_artifact_gate.py"),
    ),
    RuntimeBypassRule(
        rule_id="direct_compatibility_check",
        pattern=r"\bcheck_runtime_compatibility\s*\(",
        message="compatibility checks must flow through RuntimeArtifactGate outside compatibility/gate tests",
        allowed_modules=("runtime_compatibility.py", "runtime_artifact_gate.py"),
    ),
    RuntimeBypassRule(
        rule_id="direct_replay_reconstruct",
        pattern=r"\.reconstruct\s*\(",
        message="runtime replay reconstruction should flow through RuntimeReconstructionPipeline outside replay/pipeline tests",
        allowed_modules=("runtime_replay_session.py", "runtime_reconstruction_pipeline.py"),
        severity="warning",
    ),
    RuntimeBypassRule(
        rule_id="manual_evidence_assignment",
        pattern=r"\bself\.evidence\s*=\s*\{",
        message="manual evidence assembly must be replaced by RuntimeEvidenceAuthority",
        allowed_modules=("runtime_evidence_authority.py",),
    ),
)


@dataclass(frozen=True)
class RuntimeBypassAuditReport:
    scanned_files: tuple[str, ...]
    findings: tuple[RuntimeBypassFinding, ...] = ()
    rules: tuple[RuntimeBypassRule, ...] = DEFAULT_BYPASS_RULES
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)

    @property
    def error_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_bypass_audit_report",
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "scanned_files": list(self.scanned_files),
            "findings": [finding.to_dict() for finding in self.findings],
            "rules": [rule.to_dict() for rule in self.rules],
            "metadata": dict(self.metadata),
        }


def _module_name(path: str | Path) -> str:
    return Path(path).name


def audit_runtime_texts(
    texts: Mapping[str, str],
    *,
    rules: Iterable[RuntimeBypassRule] = DEFAULT_BYPASS_RULES,
    allowed_modules: Iterable[str] = (),
    metadata: dict[str, Any] | None = None,
) -> RuntimeBypassAuditReport:
    rule_tuple = tuple(rules)
    global_allowed = set(allowed_modules)
    findings: list[RuntimeBypassFinding] = []

    for file_path, text in sorted(texts.items(), key=lambda item: item[0]):
        module = _module_name(file_path)
        lines = str(text or "").splitlines()
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for rule in rule_tuple:
                if module in global_allowed or module in rule.allowed_modules:
                    continue
                if rule.compiled().search(line):
                    findings.append(
                        RuntimeBypassFinding(
                            file_path=str(file_path),
                            line_number=line_number,
                            rule_id=rule.rule_id,
                            severity=rule.severity,
                            message=rule.message,
                            line=stripped,
                        )
                    )
    return RuntimeBypassAuditReport(
        scanned_files=tuple(sorted(str(path) for path in texts.keys())),
        findings=tuple(findings),
        rules=rule_tuple,
        metadata=dict(metadata or {}),
    )


def audit_runtime_paths(
    paths: Iterable[str | Path],
    *,
    rules: Iterable[RuntimeBypassRule] = DEFAULT_BYPASS_RULES,
    allowed_modules: Iterable[str] = (),
    metadata: dict[str, Any] | None = None,
) -> RuntimeBypassAuditReport:
    texts: dict[str, str] = {}
    for item in paths:
        path = Path(item)
        if path.is_dir():
            for child in sorted(path.rglob("*.py")):
                if "__pycache__" in child.parts:
                    continue
                texts[str(child)] = child.read_text(encoding="utf-8")
        elif path.exists() and path.suffix == ".py":
            texts[str(path)] = path.read_text(encoding="utf-8")
    return audit_runtime_texts(
        texts,
        rules=rules,
        allowed_modules=allowed_modules,
        metadata=metadata,
    )


__all__ = [
    "DEFAULT_BYPASS_RULES",
    "RuntimeBypassAuditReport",
    "RuntimeBypassFinding",
    "RuntimeBypassRule",
    "audit_runtime_paths",
    "audit_runtime_texts",
]
