from __future__ import annotations

"""
ZERO Work Package Plan v3.

The plan object is intentionally non-mutating. It records what ZERO intends to do
for an operator package before execute authority is opened.
"""

from dataclasses import dataclass, field
from typing import Any

from core.tasks.work_package_contract import WorkPackageRequest
from core.tasks.work_package_mode import WorkPackageMode


SCHEMA = "zero.work_package.plan.v3"


@dataclass(frozen=True)
class WorkPackagePlan:
    package_id: str
    goal: str
    mode: str
    actions: tuple[str, ...] = field(default_factory=tuple)
    mutation_allowed: bool = False
    approval_required: bool = False
    blocked: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "package_id": self.package_id,
            "goal": self.goal,
            "mode": self.mode,
            "actions": list(self.actions),
            "mutation_allowed": self.mutation_allowed,
            "approval_required": self.approval_required,
            "blocked": self.blocked,
            "reason": self.reason,
        }


def build_work_package_plan(request: WorkPackageRequest) -> WorkPackagePlan:
    """Build the mode-aware plan for a work package."""

    if request.mode == WorkPackageMode.EXPLORE:
        return WorkPackagePlan(
            package_id=request.package_id,
            goal=request.title,
            mode=request.mode.value,
            actions=(
                "read_declared_scope_files",
                "scan_declared_markers",
                "write_readonly_audit_report",
            ),
            mutation_allowed=False,
            approval_required=False,
            blocked=False,
            reason="explore_mode_readonly",
        )

    if request.mode == WorkPackageMode.PLAN:
        return WorkPackagePlan(
            package_id=request.package_id,
            goal=request.title,
            mode=request.mode.value,
            actions=(
                "read_declared_scope_files",
                "summarize_findings",
                "propose_cleanup_boundaries",
                "write_plan_report",
            ),
            mutation_allowed=False,
            approval_required=False,
            blocked=False,
            reason="plan_mode_readonly",
        )

    if request.mode == WorkPackageMode.EXECUTE:
        approved = bool(request.approval)
        return WorkPackagePlan(
            package_id=request.package_id,
            goal=request.title,
            mode=request.mode.value,
            actions=(
                "require_operator_approval",
                "dispatch_controlled_edit_only_after_approval",
            ),
            mutation_allowed=approved,
            approval_required=not approved,
            blocked=not approved,
            reason="execute_requires_approval" if not approved else "execute_approved",
        )

    if request.mode == WorkPackageMode.VERIFY:
        return WorkPackagePlan(
            package_id=request.package_id,
            goal=request.title,
            mode=request.mode.value,
            actions=(
                "run_allowed_validation_commands",
                "collect_evidence",
                "write_verification_report",
            ),
            mutation_allowed=False,
            approval_required=False,
            blocked=False,
            reason="verify_mode_no_mutation",
        )

    return WorkPackagePlan(
        package_id=request.package_id,
        goal=request.title,
        mode=str(request.mode),
        actions=(),
        mutation_allowed=False,
        approval_required=False,
        blocked=True,
        reason="unsupported_mode",
    )


__all__ = ["SCHEMA", "WorkPackagePlan", "build_work_package_plan"]
