from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.runtime.controlled_mutation_boundary import ControlledMutationBoundary
from core.runtime.controlled_mutation_rollback_boundary import (
    ControlledMutationRollbackBoundary,
)
from core.runtime.controlled_mutation_sandbox_executor import (
    ControlledMutationSandboxExecutor,
)
from core.runtime.controlled_mutation_sandbox_plan import (
    ControlledMutationSandboxPlan,
)
from core.runtime.controlled_mutation_verification_boundary import (
    ControlledMutationVerificationBoundary,
)


class ControlledMutationEvidenceBundleRejected(RuntimeError):
    pass


class ControlledMutationEvidenceBundle:
    def __init__(
        self,
        bundle_id: str,
        mutation_boundary: ControlledMutationBoundary,
        sandbox_plan: ControlledMutationSandboxPlan,
        sandbox_executor: ControlledMutationSandboxExecutor,
        verification_boundary: ControlledMutationVerificationBoundary,
        rollback_boundary: ControlledMutationRollbackBoundary,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self.bundle_id = self._validate_text("bundle_id", bundle_id)
        self._require_type(
            "mutation_boundary",
            mutation_boundary,
            ControlledMutationBoundary,
        )
        self._require_type(
            "sandbox_plan",
            sandbox_plan,
            ControlledMutationSandboxPlan,
        )
        self._require_type(
            "sandbox_executor",
            sandbox_executor,
            ControlledMutationSandboxExecutor,
        )
        self._require_type(
            "verification_boundary",
            verification_boundary,
            ControlledMutationVerificationBoundary,
        )
        self._require_type(
            "rollback_boundary",
            rollback_boundary,
            ControlledMutationRollbackBoundary,
        )

        self.mutation_id = sandbox_plan.mutation_id
        self.sandbox_id = sandbox_plan.sandbox_id
        self._validate_identity(
            mutation_boundary=mutation_boundary,
            sandbox_plan=sandbox_plan,
            sandbox_executor=sandbox_executor,
            verification_boundary=verification_boundary,
            rollback_boundary=rollback_boundary,
        )

        self._lifecycle_summary = self._build_lifecycle_summary(mutation_boundary)
        self._sandbox_plan_summary = self._build_sandbox_plan_summary(sandbox_plan)
        self._execution_summary = self._build_execution_summary(sandbox_executor)
        self._verification_summary = self._build_verification_summary(
            verification_boundary
        )
        self._rollback_summary = self._build_rollback_summary(rollback_boundary)
        self._fingerprint_inputs = {
            "lifecycle_action_fingerprints": copy.deepcopy(
                self._lifecycle_summary["action_fingerprints"]
            ),
            "sandbox_plan_fingerprint": sandbox_plan.fingerprint,
            "sandbox_executor_fingerprint": sandbox_executor.fingerprint,
            "verification_boundary_fingerprint": verification_boundary.fingerprint,
            "rollback_boundary_fingerprint": rollback_boundary.fingerprint,
        }
        self._evidence_refs = copy.deepcopy(evidence_refs)
        self._metadata = copy.deepcopy(metadata)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @property
    def lifecycle_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._lifecycle_summary)

    @property
    def sandbox_plan_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._sandbox_plan_summary)

    @property
    def execution_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._execution_summary)

    @property
    def verification_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._verification_summary)

    @property
    def rollback_summary(self) -> dict[str, Any]:
        return copy.deepcopy(self._rollback_summary)

    @property
    def evidence_refs(self) -> Any:
        return copy.deepcopy(self._evidence_refs)

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def created_at(self) -> str:
        return self._created_at

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self._fingerprint_payload(),
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _fingerprint_payload(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "mutation_id": self.mutation_id,
            "sandbox_id": self.sandbox_id,
            "lifecycle_action_fingerprints": self._fingerprint_inputs[
                "lifecycle_action_fingerprints"
            ],
            "sandbox_plan_fingerprint": self._fingerprint_inputs[
                "sandbox_plan_fingerprint"
            ],
            "sandbox_executor_fingerprint": self._fingerprint_inputs[
                "sandbox_executor_fingerprint"
            ],
            "verification_boundary_fingerprint": self._fingerprint_inputs[
                "verification_boundary_fingerprint"
            ],
            "rollback_boundary_fingerprint": self._fingerprint_inputs[
                "rollback_boundary_fingerprint"
            ],
            "evidence_refs": self._evidence_refs,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
        }

    def _build_lifecycle_summary(
        self,
        mutation_boundary: ControlledMutationBoundary,
    ) -> dict[str, Any]:
        actions = mutation_boundary.list_actions()
        return {
            "boundary_id": mutation_boundary.boundary_id,
            "action_count": len(actions),
            "phases": [action.phase for action in actions],
            "action_ids": [action.action_id for action in actions],
            "action_fingerprints": [action.fingerprint for action in actions],
            "boundary_fingerprint": mutation_boundary.fingerprint,
        }

    def _build_sandbox_plan_summary(
        self,
        sandbox_plan: ControlledMutationSandboxPlan,
    ) -> dict[str, Any]:
        return {
            "sandbox_id": sandbox_plan.sandbox_id,
            "mutation_id": sandbox_plan.mutation_id,
            "target_paths": sandbox_plan.target_paths,
            "patch_identity": sandbox_plan.patch_identity,
            "verification_strategy": sandbox_plan.verification_strategy,
            "rollback_strategy": sandbox_plan.rollback_strategy,
            "fingerprint": sandbox_plan.fingerprint,
        }

    def _build_execution_summary(
        self,
        sandbox_executor: ControlledMutationSandboxExecutor,
    ) -> dict[str, Any]:
        records = sandbox_executor.list_records()
        return {
            "executor_id": sandbox_executor.executor_id,
            "record_count": len(records),
            "phases": [record.execution_phase for record in records],
            "record_ids": [record.record_id for record in records],
            "record_fingerprints": [record.fingerprint for record in records],
            "executor_fingerprint": sandbox_executor.fingerprint,
        }

    def _build_verification_summary(
        self,
        verification_boundary: ControlledMutationVerificationBoundary,
    ) -> dict[str, Any]:
        records = verification_boundary.list_records()
        return {
            "boundary_id": verification_boundary.boundary_id,
            "record_count": len(records),
            "phases": [record.verification_phase for record in records],
            "record_ids": [record.record_id for record in records],
            "record_fingerprints": [record.fingerprint for record in records],
            "boundary_fingerprint": verification_boundary.fingerprint,
        }

    def _build_rollback_summary(
        self,
        rollback_boundary: ControlledMutationRollbackBoundary,
    ) -> dict[str, Any]:
        records = rollback_boundary.list_records()
        return {
            "boundary_id": rollback_boundary.boundary_id,
            "record_count": len(records),
            "phases": [record.rollback_phase for record in records],
            "record_ids": [record.record_id for record in records],
            "record_fingerprints": [record.fingerprint for record in records],
            "boundary_fingerprint": rollback_boundary.fingerprint,
        }

    def _validate_identity(
        self,
        mutation_boundary: ControlledMutationBoundary,
        sandbox_plan: ControlledMutationSandboxPlan,
        sandbox_executor: ControlledMutationSandboxExecutor,
        verification_boundary: ControlledMutationVerificationBoundary,
        rollback_boundary: ControlledMutationRollbackBoundary,
    ) -> None:
        expected_mutation_id = sandbox_plan.mutation_id
        expected_sandbox_id = sandbox_plan.sandbox_id

        if sandbox_executor.plan.mutation_id != expected_mutation_id:
            self._reject_identity("mutation_id", sandbox_executor.plan.mutation_id)
        if sandbox_executor.plan.sandbox_id != expected_sandbox_id:
            self._reject_identity("sandbox_id", sandbox_executor.plan.sandbox_id)

        for action in mutation_boundary.list_actions():
            if action.mutation_id != expected_mutation_id:
                self._reject_identity("mutation_id", action.mutation_id)

        for record in sandbox_executor.list_records():
            if record.mutation_id != expected_mutation_id:
                self._reject_identity("mutation_id", record.mutation_id)
            if record.sandbox_id != expected_sandbox_id:
                self._reject_identity("sandbox_id", record.sandbox_id)

        for record in verification_boundary.list_records():
            if record.mutation_id != expected_mutation_id:
                self._reject_identity("mutation_id", record.mutation_id)
            if record.sandbox_id != expected_sandbox_id:
                self._reject_identity("sandbox_id", record.sandbox_id)

        for record in rollback_boundary.list_records():
            if record.mutation_id != expected_mutation_id:
                self._reject_identity("mutation_id", record.mutation_id)
            if record.sandbox_id != expected_sandbox_id:
                self._reject_identity("sandbox_id", record.sandbox_id)

    def _reject_identity(self, field_name: str, value: Any) -> None:
        raise ControlledMutationEvidenceBundleRejected(
            f"controlled mutation evidence bundle {field_name} mismatch: {value!r}"
        )

    def _require_type(self, field_name: str, value: Any, expected_type: type) -> None:
        if not isinstance(value, expected_type):
            raise ControlledMutationEvidenceBundleRejected(
                f"controlled mutation evidence bundle requires {field_name}"
            )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationEvidenceBundleRejected(
                f"controlled mutation evidence bundle {field_name} is required"
            )
        return value


__all__ = [
    "ControlledMutationEvidenceBundle",
    "ControlledMutationEvidenceBundleRejected",
]
