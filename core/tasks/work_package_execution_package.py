from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping


PROPOSAL_APPROVAL_SCHEMA = "zero.work_package.proposal_approval.v1"
EXECUTION_PACKAGE_SCHEMA = "zero.work_package.execution_package.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return f"{prefix}-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def proposal_id_for(proposal: Mapping[str, Any]) -> str:
    existing = str(proposal.get("proposal_id") or "").strip()
    if existing:
        return existing
    return _stable_id(
        "wp-proposal",
        {
            "package_id": proposal.get("package_id"),
            "objective": proposal.get("objective"),
            "proposed_steps": proposal.get("proposed_steps"),
            "validation_plan": proposal.get("validation_plan"),
        },
    )


def build_proposal_approval(
    proposal: Mapping[str, Any],
    *,
    approved_by: str = "operator",
    approval_scope: str = "execution_package_generation",
    approved: bool = True,
    mutation_allowed: bool = False,
    approved_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": PROPOSAL_APPROVAL_SCHEMA,
        "package_id": str(proposal.get("package_id") or ""),
        "proposal_id": proposal_id_for(proposal),
        "approved": bool(approved),
        "approved_by": str(approved_by or "operator"),
        "approved_at": approved_at or _now(),
        "approval_scope": str(approval_scope or "execution_package_generation"),
        "mutation_allowed": bool(mutation_allowed),
    }


def summarize_approval(approval: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(approval, Mapping):
        return {
            "approved": False,
            "proposal_id": None,
            "approved_by": None,
            "approved_at": None,
            "approval_scope": None,
            "mutation_allowed": False,
        }
    return {
        "approved": bool(approval.get("approved")),
        "proposal_id": approval.get("proposal_id"),
        "approved_by": approval.get("approved_by"),
        "approved_at": approval.get("approved_at"),
        "approval_scope": approval.get("approval_scope"),
        "mutation_allowed": bool(approval.get("mutation_allowed")),
    }


def build_execution_package(
    *,
    record: Mapping[str, Any],
    proposal: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    mutation_allowed = bool(approval.get("mutation_allowed"))
    executable_steps = copy.deepcopy(
        proposal.get("proposed_steps")
        if isinstance(proposal.get("proposed_steps"), list)
        else (record.get("planning_snapshot") or {}).get("executable_steps") or []
    )
    validation_plan = proposal.get("validation_plan") if isinstance(proposal.get("validation_plan"), Mapping) else {}
    return {
        "schema": EXECUTION_PACKAGE_SCHEMA,
        "package_id": str(record.get("package_id") or proposal.get("package_id") or ""),
        "objective": str(proposal.get("objective") or record.get("objective") or record.get("goal") or ""),
        "approved_proposal": {
            "proposal_id": proposal_id_for(proposal),
            "approval": copy.deepcopy(dict(approval)),
            "proposal_summary": copy.deepcopy(
                record.get("execution_proposal_summary")
                if isinstance(record.get("execution_proposal_summary"), Mapping)
                else proposal.get("proposal_summary") or {}
            ),
        },
        "executable_steps": executable_steps,
        "validation_commands": [
            str(item)
            for item in (
                validation_plan.get("commands")
                if isinstance(validation_plan.get("commands"), list)
                else record.get("validation_commands") or []
            )
            if str(item).strip()
        ],
        "mutation_allowed": mutation_allowed,
        "required_operator_approval": True,
        "non_mainline_reporting_enabled": bool(proposal.get("non_mainline_reporting_enabled", True)),
        "repo_mutation_performed_by_zero": False,
    }


def summarize_execution_package(execution_package: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(execution_package, Mapping):
        return {
            "created": False,
            "package_id": None,
            "step_count": 0,
            "validation_command_count": 0,
            "mutation_allowed": False,
            "required_operator_approval": True,
            "non_mainline_reporting_enabled": False,
        }
    return {
        "created": True,
        "package_id": execution_package.get("package_id"),
        "step_count": len(execution_package.get("executable_steps") or []),
        "validation_command_count": len(execution_package.get("validation_commands") or []),
        "mutation_allowed": bool(execution_package.get("mutation_allowed")),
        "required_operator_approval": bool(execution_package.get("required_operator_approval")),
        "non_mainline_reporting_enabled": bool(
            execution_package.get("non_mainline_reporting_enabled")
        ),
    }


__all__ = [
    "EXECUTION_PACKAGE_SCHEMA",
    "PROPOSAL_APPROVAL_SCHEMA",
    "build_execution_package",
    "build_proposal_approval",
    "proposal_id_for",
    "summarize_approval",
    "summarize_execution_package",
]
