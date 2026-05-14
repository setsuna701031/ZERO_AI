from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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


def run_mutation_runtime_pipeline(
    *,
    session: MutationSession,
    relative_paths: list[str],
    workspace_root: str | Path,
    sandbox_source_root: str | Path,
    rollback_root: str | Path,
    report_root: str | Path,
    verification_checks: list[MutationVerificationCheck] | None = None,
    approval_decisions: list[MutationApprovalDecision] | None = None,
    dry_run: bool = False,
    metadata: dict[str, Any] | None = None,
) -> MutationRuntimePipelineResult:
    """
    Run one governed mutation transaction.

    This pipeline intentionally does not mutate files until:
    1. patch plan passes scope validation
    2. verification passes
    3. approval passes

    Only after those gates does controlled apply run.
    """

    reports = Path(report_root)
    reports.mkdir(parents=True, exist_ok=True)

    artifact_paths: dict[str, str] = {}

    session_path = write_mutation_session(
        session,
        reports,
    )
    artifact_paths["session"] = str(session_path)

    patch_plan = create_patch_plan(
        session=session,
        relative_paths=relative_paths,
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
        metadata=metadata,
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
        metadata=metadata,
    )
    approval_path = write_approval_result(
        approval,
        reports,
    )
    artifact_paths["approval"] = str(approval_path)

    enforce_approval_result(approval)

    apply_result = apply_patch_plan(
        workspace_root=workspace_root,
        sandbox_source_root=sandbox_source_root,
        rollback_root=rollback_root,
        report_root=reports,
        session=session,
        plan=patch_plan,
        dry_run=dry_run,
    )

    if apply_result.report_path:
        artifact_paths["apply_report"] = apply_result.report_path

    audit_record = build_mutation_audit_record(
        session=session,
        patch_plan=patch_plan,
        verification=verification,
        approval=approval,
        apply_result=apply_result,
        metadata=metadata,
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