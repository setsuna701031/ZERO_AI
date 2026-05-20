from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VerificationEvidenceBundle:
    bundle_id: str
    verification_route_id: str
    command: str
    status: str
    exit_code: int | None
    stdout_tail: str
    stderr_tail: str
    failure_classification: str
    retry_recommended: bool
    repair_eligible: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "verification_route_id": self.verification_route_id,
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "failure_classification": self.failure_classification,
            "retry_recommended": self.retry_recommended,
            "repair_eligible": self.repair_eligible,
            "metadata": dict(self.metadata),
        }


def build_verification_evidence_bundle(
    *,
    verification_route: dict[str, Any],
    exit_code: int | None,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
) -> VerificationEvidenceBundle:
    """Build a structured evidence bundle from a verification-only route result.

    This function does not execute commands, mutate files, apply patches, or claim
    governed runtime success. It only packages a verification result so a future
    retry/repair loop can reason about it.
    """

    route_metadata = dict(verification_route.get("metadata") or {})
    command = str(verification_route.get("command") or "").strip()
    route_id = str(
        verification_route.get("verification_route_id")
        or verification_route.get("route_id")
        or ""
    ).strip()

    if not route_id:
        raise ValueError("verification_route_id_required")
    if not command:
        raise ValueError("verification_command_required")
    if route_metadata.get("verification_only") is not True:
        raise ValueError("verification_route_must_be_verification_only")
    if route_metadata.get("execution_allowed") is True:
        raise ValueError("verification_route_must_not_grant_execution_authority")
    if route_metadata.get("mutation_allowed") is True:
        raise ValueError("verification_route_must_not_grant_mutation_authority")

    status = _status_from_result(exit_code=exit_code, timed_out=timed_out)
    failure_classification = _classify_failure(
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
    )
    retry_recommended = failure_classification in {
        "test_failure",
        "compile_failure",
        "lint_failure",
        "timeout",
        "runtime_error",
        "unknown_failure",
    }
    repair_eligible = failure_classification in {
        "test_failure",
        "compile_failure",
        "lint_failure",
        "runtime_error",
    }

    payload = {
        "verification_route_id": route_id,
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "stdout_tail": _tail(stdout),
        "stderr_tail": _tail(stderr),
        "failure_classification": failure_classification,
        "retry_recommended": retry_recommended,
        "repair_eligible": repair_eligible,
    }

    return VerificationEvidenceBundle(
        bundle_id="verification-evidence-" + _stable_hash(payload)[:16],
        verification_route_id=route_id,
        command=command,
        status=status,
        exit_code=exit_code,
        stdout_tail=payload["stdout_tail"],
        stderr_tail=payload["stderr_tail"],
        failure_classification=failure_classification,
        retry_recommended=retry_recommended,
        repair_eligible=repair_eligible,
        metadata={
            "verification_only": True,
            "read_only": True,
            "mutation_allowed": False,
            "execution_authority_granted": False,
            "patch_apply_allowed": False,
            "canonical_runtime_success": False,
            "feeds_retry_repair_loop": True,
            "source_route_metadata": route_metadata,
        },
    )


def validate_verification_evidence_contract(payload: dict[str, Any]) -> bool:
    required = {
        "bundle_id",
        "verification_route_id",
        "command",
        "status",
        "exit_code",
        "stdout_tail",
        "stderr_tail",
        "failure_classification",
        "retry_recommended",
        "repair_eligible",
        "metadata",
    }
    if not required.issubset(payload):
        return False

    metadata = payload.get("metadata") or {}
    if metadata.get("verification_only") is not True:
        return False
    if metadata.get("mutation_allowed") is not False:
        return False
    if metadata.get("execution_authority_granted") is not False:
        return False
    if metadata.get("canonical_runtime_success") is not False:
        return False

    forbidden_success_fields = {
        "runtime_evidence_id",
        "runtime_audit_metadata",
        "governed_mutation_lineage",
        "rollback_eligibility",
        "recovery_eligibility",
        "execution_summary",
        "canonical_success",
    }
    if forbidden_success_fields.intersection(payload):
        return False

    return True


def _status_from_result(*, exit_code: int | None, timed_out: bool) -> str:
    if timed_out:
        return "timeout"
    if exit_code == 0:
        return "passed"
    if exit_code is None:
        return "unknown"
    return "failed"


def _classify_failure(
    *,
    status: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    timed_out: bool,
) -> str:
    combined = f"{stdout}\n{stderr}".lower()

    if status == "passed":
        return "none"
    if timed_out:
        return "timeout"
    if "syntaxerror" in combined or "compile" in combined:
        return "compile_failure"
    if "assert" in combined or "failed" in combined or "pytest" in combined:
        return "test_failure"
    if "lint" in combined or "ruff" in combined or "flake8" in combined:
        return "lint_failure"
    if "traceback" in combined or "exception" in combined or "error" in combined:
        return "runtime_error"
    if exit_code is None:
        return "unknown_failure"
    return "unknown_failure"


def _tail(value: str, *, limit: int = 4000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
