from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass, field
from typing import Any, Iterable


DEFAULT_ALLOWED_COMMAND_PREFIXES = (
    "python -m pytest",
    "python -m compileall",
    "pytest",
)


@dataclass(frozen=True)
class VerificationCommand:
    command_id: str
    command: str
    purpose: str
    allowed: bool
    reason: str
    classification: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command": self.command,
            "purpose": self.purpose,
            "allowed": self.allowed,
            "reason": self.reason,
            "classification": self.classification,
        }


@dataclass(frozen=True)
class VerificationRoute:
    route_id: str
    source_profile_id: str
    proposal_id: str
    plan_id: str
    commands: tuple[VerificationCommand, ...]
    retry_eligible: bool
    repair_eligible: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "source_profile_id": self.source_profile_id,
            "proposal_id": self.proposal_id,
            "plan_id": self.plan_id,
            "commands": [item.to_dict() for item in self.commands],
            "retry_eligible": self.retry_eligible,
            "repair_eligible": self.repair_eligible,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class VerificationEvidence:
    evidence_id: str
    route_id: str
    command_results: tuple[dict[str, Any], ...]
    status: str
    retry_eligible: bool
    repair_eligible: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "route_id": self.route_id,
            "command_results": [dict(item) for item in self.command_results],
            "status": self.status,
            "retry_eligible": self.retry_eligible,
            "repair_eligible": self.repair_eligible,
            "metadata": dict(self.metadata),
        }


def build_verification_route(
    verification_profile: dict[str, Any],
    *,
    allowed_prefixes: Iterable[str] = DEFAULT_ALLOWED_COMMAND_PREFIXES,
) -> VerificationRoute:
    """Build a verification-only command route from a profile.

    This function does not execute commands. It only classifies the commands that a
    later governed execution layer may run.
    """

    profile_id = _require_text(verification_profile, "profile_id")
    proposal_id = _require_text(verification_profile, "proposal_id")
    plan_id = _require_text(verification_profile, "plan_id")
    raw_commands = verification_profile.get("commands") or verification_profile.get("verification_commands") or []

    if not isinstance(raw_commands, list):
        raise ValueError("verification_commands_must_be_list")

    command_records: list[VerificationCommand] = []
    for index, item in enumerate(raw_commands):
        command_text = _command_text(item)
        purpose = _command_purpose(item)
        allowed, reason, classification = classify_verification_command(
            command_text,
            allowed_prefixes=allowed_prefixes,
        )
        payload = {
            "profile_id": profile_id,
            "index": index,
            "command": command_text,
            "purpose": purpose,
            "allowed": allowed,
            "classification": classification,
        }
        command_records.append(
            VerificationCommand(
                command_id="verification-command-" + _stable_hash(payload)[:16],
                command=command_text,
                purpose=purpose,
                allowed=allowed,
                reason=reason,
                classification=classification,
            )
        )

    payload = {
        "source_profile_id": profile_id,
        "proposal_id": proposal_id,
        "plan_id": plan_id,
        "commands": [item.to_dict() for item in command_records],
    }
    return VerificationRoute(
        route_id="verification-route-" + _stable_hash(payload)[:16],
        source_profile_id=profile_id,
        proposal_id=proposal_id,
        plan_id=plan_id,
        commands=tuple(command_records),
        retry_eligible=True,
        repair_eligible=True,
        metadata={
            "verification_only": True,
            "read_only": True,
            "mutation_allowed": False,
            "patch_apply_allowed": False,
            "execution_authority_owned_by_runtime": True,
            "governed_runtime_required": True,
            "canonical_success": False,
        },
    )


def classify_verification_command(
    command: str,
    *,
    allowed_prefixes: Iterable[str] = DEFAULT_ALLOWED_COMMAND_PREFIXES,
) -> tuple[bool, str, str]:
    command_text = " ".join(str(command or "").strip().split())
    lowered = command_text.lower()

    if not command_text:
        return False, "empty command", "invalid"

    dangerous_tokens = (
        " rm ",
        " rmdir ",
        " del ",
        " remove-item ",
        " git push",
        " git commit",
        " git reset",
        " git clean",
        " pip install",
        " npm install",
        "curl ",
        "wget ",
        ">",
        ">>",
        "|",
        "&&",
        ";",
    )
    padded = f" {lowered} "
    if any(token in padded for token in dangerous_tokens):
        return False, "command contains mutation/network/shell-control token", "blocked"

    normalized_prefixes = tuple(" ".join(prefix.lower().split()) for prefix in allowed_prefixes)
    if any(lowered.startswith(prefix) for prefix in normalized_prefixes):
        return True, "allowed verification command prefix", "verification"

    return False, "command is not in allowed verification profile", "blocked"


def build_verification_evidence(
    route: VerificationRoute,
    command_results: Iterable[dict[str, Any]],
) -> VerificationEvidence:
    """Build verification evidence from externally supplied command results.

    This does not run commands and does not claim runtime canonical success. It is a
    verification-layer artifact for a future governed executor to seal.
    """

    results = tuple(dict(item) for item in command_results)
    allowed_command_ids = {item.command_id for item in route.commands}
    for result in results:
        command_id = result.get("command_id")
        if command_id not in allowed_command_ids:
            raise ValueError(f"command_result_not_in_route:{command_id}")

    all_passed = bool(results) and all(int(item.get("returncode", 1)) == 0 for item in results)
    status = "passed" if all_passed else "failed"

    payload = {
        "route_id": route.route_id,
        "results": results,
        "status": status,
    }
    return VerificationEvidence(
        evidence_id="verification-evidence-" + _stable_hash(payload)[:16],
        route_id=route.route_id,
        command_results=results,
        status=status,
        retry_eligible=status != "passed",
        repair_eligible=status != "passed",
        metadata={
            "verification_evidence_only": True,
            "runtime_evidence_required_for_canonical_success": True,
            "canonical_success": False,
            "mutation_allowed": False,
            "patch_apply_allowed": False,
        },
    )


def validate_verification_route_contract(payload: dict[str, Any]) -> bool:
    required_fields = {
        "route_id",
        "source_profile_id",
        "proposal_id",
        "plan_id",
        "commands",
        "retry_eligible",
        "repair_eligible",
        "metadata",
    }
    if not required_fields.issubset(payload):
        return False

    metadata = payload.get("metadata") or {}
    if metadata.get("verification_only") is not True:
        return False
    if metadata.get("mutation_allowed") is not False:
        return False
    if metadata.get("patch_apply_allowed") is not False:
        return False
    if metadata.get("execution_authority_owned_by_runtime") is not True:
        return False
    if metadata.get("canonical_success") is not False:
        return False

    commands = payload.get("commands")
    if not isinstance(commands, list) or not commands:
        return False
    if not all(item.get("allowed") is True for item in commands):
        return False

    forbidden_success_fields = {
        "runtime_evidence_id",
        "runtime_audit_metadata",
        "governed_mutation_lineage",
        "rollback_eligibility",
        "recovery_eligibility",
        "execution_summary",
        "canonical_execution_success",
    }
    if forbidden_success_fields.intersection(payload):
        return False

    return True


def _command_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("command") or "").strip()
    raise ValueError("unsupported_command_shape")


def _command_purpose(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("purpose") or "verification").strip()
    return "verification"


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key}_required")
    return value


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
