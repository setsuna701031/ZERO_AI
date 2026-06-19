from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.runtime.mutation_approval import (
    MutationApprovalDecision,
    MutationApprovalResult,
    evaluate_approval,
    enforce_approval_result,
    write_approval_result,
)
from core.runtime.mutation_audit import (
    MutationAuditRecord,
    build_mutation_audit_record,
    write_audit_record,
)
from core.runtime.mutation_patch_apply import (
    MutationPatchApplyResult,
    MutationPatchPlan,
    apply_patch_plan,
    create_patch_plan,
    write_patch_plan,
)
from core.runtime.mutation_session import (
    MutationSession,
    write_mutation_session,
)
from core.runtime.mutation_verification import (
    MutationVerificationCheck,
    MutationVerificationResult,
    enforce_verification_result,
    verify_patch_plan,
    write_verification_result,
)
from core.runtime.runtime_evidence_chain import (
    build_runtime_evidence_record,
    validate_runtime_evidence_record,
)
from core.runtime.runtime_mutation_authority import (
    CANONICAL_MUTATION_AUTHORITY,
    MUTATION_PERSISTENCE_ROLE,
    issue_runtime_mutation_capability,
)

try:
    from core.runtime.runtime_freeze import RuntimeFreezeAuthority
except Exception:  # pragma: no cover - compatibility while runtime surface is evolving
    RuntimeFreezeAuthority = None  # type: ignore[assignment]

try:
    from core.runtime.runtime_legality import RuntimeLegalityEngine
except Exception:  # pragma: no cover - compatibility while runtime surface is evolving
    RuntimeLegalityEngine = None  # type: ignore[assignment]


@dataclass(frozen=True)
class MutationRuntimePipelineResult:
    session_id: str
    completed: bool
    dry_run: bool
    patch_plan: MutationPatchPlan
    verification: MutationVerificationResult
    approval: MutationApprovalResult
    apply_result: MutationPatchApplyResult | None
    audit_record: MutationAuditRecord
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "completed": self.completed,
            "dry_run": self.dry_run,
            "patch_plan": self.patch_plan.to_dict(),
            "verification": self.verification.to_dict(),
            "approval": self.approval.to_dict(),
            "apply_result": self.apply_result.to_dict() if self.apply_result else None,
            "audit_record": self.audit_record.to_dict(),
            "artifact_paths": self.artifact_paths,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)



def _risk_level_text(value: Any) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return "unknown"
    text = str(raw).strip().lower()
    return text or "unknown"


def _decision_to_dict(decision: Any) -> dict[str, Any]:
    if decision is None:
        return {}

    to_dict = getattr(decision, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return dict(payload)

    payload: dict[str, Any] = {}
    for key in (
        "allowed",
        "requires_review",
        "blocked",
        "decision",
        "reason",
        "violated_rules",
        "action_type",
        "risk_level",
        "governance_id",
        "constitution_version",
    ):
        if hasattr(decision, key):
            payload[key] = getattr(decision, key)

    if "decision" not in payload:
        if bool(payload.get("blocked")):
            payload["decision"] = "BLOCK"
        elif bool(payload.get("requires_review")):
            payload["decision"] = "REVIEW"
        elif bool(payload.get("allowed")):
            payload["decision"] = "ALLOW"
        else:
            payload["decision"] = "UNKNOWN"

    return payload


def _enforce_mutation_pipeline_freeze(
    *,
    freeze_state: Any,
    action_type: str,
) -> None:
    if RuntimeFreezeAuthority is None:
        return

    decision = RuntimeFreezeAuthority().evaluate(
        freeze_state=freeze_state,
        action_type=action_type,
    )

    if not bool(getattr(decision, "denied", False)):
        return

    payload = decision.to_dict() if hasattr(decision, "to_dict") else {}
    raise PermissionError(
        "mutation_runtime_pipeline_frozen: "
        + str(payload.get("reason") or "runtime is frozen; mutation pipeline denied")
    )


def _enforce_mutation_pipeline_legality(
    *,
    action_type: str,
    risk_level: str,
    governance_snapshot: Any,
    constitution: Any,
) -> None:
    if constitution is None or RuntimeLegalityEngine is None:
        return

    decision = RuntimeLegalityEngine().evaluate_action(
        action_type=action_type,
        risk_level=risk_level,
        governance_snapshot=governance_snapshot,
        constitution=constitution,
    )

    if not (
        bool(getattr(decision, "blocked", False))
        or bool(getattr(decision, "requires_review", False))
    ):
        return

    payload = _decision_to_dict(decision)
    decision_name = str(payload.get("decision") or "UNKNOWN").upper()

    if decision_name == "BLOCK":
        raise PermissionError(
            "mutation_runtime_pipeline_blocked: "
            + str(payload.get("reason") or "runtime constitution blocked mutation pipeline")
        )

    raise PermissionError(
        "mutation_runtime_pipeline_requires_review: "
        + str(payload.get("reason") or "runtime constitution requires review for mutation pipeline")
    )



def run_mutation_runtime_pipeline(
    *,
    session: MutationSession,
    relative_paths: list[str],
    workspace_root: str | Path,
    sandbox_source_root: str | Path,
    rollback_root: str | Path,
    report_root: str | Path,
    operations: list[dict[str, Any]] | None = None,
    sandbox_files: dict[str, Any] | None = None,
    verification_checks: list[MutationVerificationCheck] | None = None,
    approval_decisions: list[MutationApprovalDecision] | None = None,
    dry_run: bool = False,
    metadata: dict[str, Any] | None = None,
    freeze_state: Any = None,
    governance_snapshot: Any = None,
    constitution: Any = None,
    enforce_freeze: bool = True,
    enforce_legality: bool = True,
    legality_action_type: str = "mutation_runtime_pipeline",
) -> MutationRuntimePipelineResult:
    """
    Run one governed mutation transaction.

    This pipeline intentionally does not mutate files until:
    1. patch plan passes scope validation
    2. verification passes
    3. approval passes

    Only after those gates does controlled apply run.
    """

    pipeline_metadata = dict(metadata or {})
    resolved_freeze_state = (
        freeze_state
        if freeze_state is not None
        else pipeline_metadata.get("runtime_freeze")
        or pipeline_metadata.get("freeze_state")
        or pipeline_metadata.get("runtime_frozen")
    )
    resolved_governance_snapshot = (
        governance_snapshot
        if governance_snapshot is not None
        else pipeline_metadata.get("governance_snapshot")
    )
    resolved_constitution = (
        constitution
        if constitution is not None
        else pipeline_metadata.get("constitution")
    )

    if enforce_freeze:
        _enforce_mutation_pipeline_freeze(
            freeze_state=resolved_freeze_state,
            action_type=legality_action_type,
        )

    if enforce_legality:
        _enforce_mutation_pipeline_legality(
            action_type=legality_action_type,
            risk_level=_risk_level_text(getattr(session, "risk_level", None)),
            governance_snapshot=resolved_governance_snapshot,
            constitution=resolved_constitution,
        )

    reports = Path(report_root)
    reports.mkdir(parents=True, exist_ok=True)

    evidence_record = build_runtime_evidence_record(
        transaction_id=session.session_id,
        execution_intent=session.intent,
        boundary_state="governed_mutation_runtime_pipeline",
        approval_chain_id=session.approval_mode.value,
        capability_grant_id="mutation_scope",
        verification_state=session.verification.value,
        rollback_state="rollback_ready",
        seal_state="evidence_sealed",
        source_execution_id=session.session_id,
        execution_session_id=str(
            pipeline_metadata.get("governed_runtime_execution_session_id")
            or pipeline_metadata.get("execution_session_id")
            or session.session_id
        ),
        replay_session_id=str(
            pipeline_metadata.get("governed_runtime_replay_session_id")
            or pipeline_metadata.get("replay_session_id")
            or pipeline_metadata.get("replay_id")
            or f"replay:{session.session_id}"
        ),
        mutation_transaction_id=str(pipeline_metadata.get("transaction_id") or ""),
        mutation_request_id=str(pipeline_metadata.get("mutation_request_id") or ""),
        authority_metadata={
            "initiator": session.initiator,
            "risk_level": session.risk_level.value,
            "approval_mode": session.approval_mode.value,
            "repair_authority_governance": pipeline_metadata.get("repair_authority_governance", {}),
            "authorization": pipeline_metadata.get("authorization", {}),
            "scope_gate": pipeline_metadata.get("scope_gate", {}),
        },
        audit_lineage={
            "session_id": session.session_id,
            "initiator": session.initiator,
            "source": pipeline_metadata.get("source", ""),
            "transaction_id": pipeline_metadata.get("transaction_id", ""),
            "mutation_transaction_id": pipeline_metadata.get("mutation_transaction_id", pipeline_metadata.get("transaction_id", "")),
            "mutation_request_id": pipeline_metadata.get("mutation_request_id", ""),
            "task_id": pipeline_metadata.get("task_id", ""),
            "proposal_id": pipeline_metadata.get("proposal_id", ""),
            "replay_id": pipeline_metadata.get("replay_id", ""),
            "audit_id": pipeline_metadata.get("audit_id", ""),
            "lineage": pipeline_metadata.get("lineage", {}),
        },
        mutation_lineage={
            "relative_paths": list(relative_paths),
            "operation_count": len(operations or []),
            "mutation_transaction_id": pipeline_metadata.get("mutation_transaction_id", pipeline_metadata.get("transaction_id", "")),
            "mutation_request_id": pipeline_metadata.get("mutation_request_id", ""),
            "lineage": pipeline_metadata.get("lineage", {}),
        },
    )
    _assert_canonical_runtime_evidence_for_pipeline(
        evidence_record,
        metadata=pipeline_metadata,
    )
    pipeline_metadata.update(
        {
            "runtime_evidence_record": evidence_record,
            "runtime_evidence_id": evidence_record["evidence_id"],
            "runtime_audit_metadata": {
                "audit_id": str(pipeline_metadata.get("audit_id") or f"audit:{session.session_id}"),
                "evidence_id": evidence_record["evidence_id"],
                "evidence_hash": evidence_record["evidence_hash"],
                "session_id": session.session_id,
                "execution_session_id": evidence_record.get("execution_session_id", ""),
                "replay_session_id": evidence_record.get("replay_session_id", ""),
                "replay_id": pipeline_metadata.get("replay_id", ""),
                "mutation_transaction_id": pipeline_metadata.get("transaction_id", ""),
                "mutation_request_id": pipeline_metadata.get("mutation_request_id", ""),
                "task_id": pipeline_metadata.get("task_id", ""),
                "proposal_id": pipeline_metadata.get("proposal_id", ""),
                "authority": evidence_record.get("authority_metadata", {}),
                "lineage": evidence_record["audit_lineage"],
            },
        }
    )

    artifact_paths: dict[str, str] = {}

    session_path = write_mutation_session(
        session,
        reports,
    )
    artifact_paths["session"] = str(session_path)

    patch_plan = create_patch_plan(
        session=session,
        relative_paths=relative_paths,
        operations=operations,
        sandbox_files=sandbox_files,
        metadata=pipeline_metadata,
    )
    patch_plan_path = write_patch_plan(
        patch_plan,
        reports,
    )
    artifact_paths["patch_plan"] = str(patch_plan_path)

    verification = verify_patch_plan(
        session=session,
        plan=patch_plan,
        checks=verification_checks,
        metadata=pipeline_metadata,
    )
    verification_path = write_verification_result(
        verification,
        reports,
    )
    artifact_paths["verification"] = str(verification_path)

    enforce_verification_result(verification)

    approval = evaluate_approval(
        session=session,
        verification=verification,
        decisions=approval_decisions,
        metadata=pipeline_metadata,
    )
    approval_path = write_approval_result(
        approval,
        reports,
    )
    artifact_paths["approval"] = str(approval_path)

    enforce_approval_result(approval)

    mutation_capability = issue_runtime_mutation_capability(
        issuer=CANONICAL_MUTATION_AUTHORITY,
        source="mutation_runtime_pipeline",
        request_id=session.session_id,
        operation_type="patch_plan_apply",
        target_path="*",
        role=MUTATION_PERSISTENCE_ROLE,
        allowed_operations=("replace", "write_file", "patch_file", "patch_plan_apply"),
        allowed_targets=tuple(item.relative_path for item in patch_plan.items) or ("*",),
        provenance={"session_id": session.session_id},
        metadata={"gateway": CANONICAL_MUTATION_AUTHORITY, "pipeline_role": "request_client"},
    )

    apply_result = apply_patch_plan(
        workspace_root=workspace_root,
        sandbox_source_root=sandbox_source_root,
        rollback_root=rollback_root,
        report_root=reports,
        session=session,
        plan=patch_plan,
        dry_run=dry_run,
        mutation_capability=mutation_capability,
    )

    if apply_result.report_path:
        artifact_paths["apply_report"] = apply_result.report_path

    audit_record = build_mutation_audit_record(
        session=session,
        patch_plan=patch_plan,
        verification=verification,
        approval=approval,
        apply_result=apply_result,
        metadata=pipeline_metadata,
    )
    audit_path = write_audit_record(
        audit_record,
        reports,
    )
    artifact_paths["audit"] = str(audit_path)

    result = MutationRuntimePipelineResult(
        session_id=session.session_id,
        completed=True,
        dry_run=dry_run,
        patch_plan=patch_plan,
        verification=verification,
        approval=approval,
        apply_result=apply_result,
        audit_record=audit_record,
        artifact_paths=artifact_paths,
    )

    result_path = reports / "mutation_runtime_pipeline_result.json"
    result_path.write_text(result.to_json(), encoding="utf-8")
    artifact_paths["pipeline_result"] = str(result_path)

    return result


def write_pipeline_result(
    result: MutationRuntimePipelineResult,
    directory: str | Path,
    filename: str = "mutation_runtime_pipeline_result.json",
) -> Path:
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / filename
    target_path.write_text(result.to_json(), encoding="utf-8")
    return target_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_canonical_runtime_evidence_for_pipeline(
    evidence_record: dict[str, Any],
    *,
    metadata: dict[str, Any],
) -> None:
    validation = validate_runtime_evidence_record(evidence_record)
    if not validation.get("ok"):
        raise ValueError(f"canonical_runtime_evidence_invalid:{validation}")

    if not _repair_authority_seal_required(metadata):
        return

    missing: list[str] = []
    for field in (
        "evidence_id",
        "execution_session_id",
        "replay_session_id",
        "mutation_transaction_id",
        "mutation_request_id",
    ):
        if not str(evidence_record.get(field) or "").strip():
            missing.append(field)

    authority = evidence_record.get("authority_metadata")
    if not isinstance(authority, dict) or not authority:
        missing.append("authority_metadata")
    elif not isinstance(authority.get("repair_authority_governance"), dict):
        missing.append("repair_authority_governance")

    audit_lineage = evidence_record.get("audit_lineage")
    if not isinstance(audit_lineage, dict) or not audit_lineage:
        missing.append("audit_lineage")
    else:
        for field in ("transaction_id", "mutation_request_id", "session_id", "replay_id", "audit_id"):
            if not str(audit_lineage.get(field) or "").strip():
                missing.append(f"audit_lineage.{field}")

    if missing:
        raise ValueError(
            "repair_transaction_authority_evidence_incomplete:"
            + ",".join(sorted(set(missing)))
        )


def _repair_authority_seal_required(metadata: dict[str, Any]) -> bool:
    source = str(metadata.get("source") or "").strip()
    if source.startswith("runtime_repair"):
        return True
    if metadata.get("repair_authority_governance") is not None:
        return True
    lineage = metadata.get("lineage")
    return isinstance(lineage, dict) and str(lineage.get("source") or "").strip() == "runtime_repair_transaction"
