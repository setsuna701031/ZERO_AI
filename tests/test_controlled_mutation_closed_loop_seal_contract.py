from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledMutationClosedLoopSealContractTest(unittest.TestCase):
    def _run_closed_loop(self, workspace_root: Path | None = None) -> dict[str, Any]:
        from core.runtime.controlled_mutation_adapter import ControlledMutationAdapter
        from core.runtime.controlled_mutation_boundary import ControlledMutationBoundary
        from core.runtime.controlled_mutation_evidence_bundle import (
            ControlledMutationEvidenceBundle,
        )
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

        mutation_id = "closed-loop-mutation"
        sandbox_id = "closed-loop-sandbox"
        target_path = (
            str(workspace_root / "observed_target.py")
            if workspace_root is not None
            else "observed_target.py"
        )
        patch_identity = {
            "patch_id": "patch-observed-only",
            "sha256": "stable-patch-fingerprint",
        }
        verification_strategy = {
            "mode": "observational",
            "command": "pytest tests/test_observed_target.py",
        }
        rollback_strategy = {
            "mode": "observational",
            "type": "reverse_patch_plan",
        }

        mutation_boundary = ControlledMutationBoundary("closed-loop-boundary")
        adapter = ControlledMutationAdapter(
            "closed-loop-adapter",
            mutation_boundary,
        )
        adapter.emit_planned(
            mutation_id,
            metadata={"stage": "plan"},
            runtime_args={"dry_run": True},
            evidence_refs={"artifact": "plan-record"},
        )
        adapter.emit_applied(
            mutation_id,
            metadata={"stage": "apply-observed"},
            runtime_args={"dry_run": True},
            evidence_refs={"artifact": "apply-record"},
        )
        adapter.emit_verified(
            mutation_id,
            metadata={"stage": "verify-observed"},
            runtime_args={"dry_run": True},
            evidence_refs={"artifact": "verify-record"},
        )
        adapter.emit_rollback_plan(
            mutation_id,
            metadata={"stage": "rollback-plan"},
            runtime_args={"dry_run": True},
            evidence_refs={"artifact": "rollback-plan-record"},
        )
        adapter.emit_rolled_back(
            mutation_id,
            metadata={"stage": "rollback-observed"},
            runtime_args={"dry_run": True},
            evidence_refs={"artifact": "rollback-record"},
        )

        sandbox_plan = (
            ControlledMutationSandboxPlan.plan_workspace_copy(
                sandbox_id,
                mutation_id,
                [target_path],
                evidence_refs={"artifact": "workspace-copy-plan"},
                metadata={"seal": "closed-loop"},
                runtime_args={"dry_run": True},
            )
            .plan_patch_apply(patch_identity)
            .plan_verification(verification_strategy)
            .plan_rollback_strategy(rollback_strategy)
        )

        sandbox_executor = ControlledMutationSandboxExecutor(
            "closed-loop-executor",
            sandbox_plan,
        )
        sandbox_executor.record_workspace_copy()
        sandbox_executor.record_patch_prepare()
        sandbox_executor.record_patch_apply()
        sandbox_executor.record_verification_prepare()
        sandbox_executor.record_verification_result(
            {"status": "passed", "executed": False}
        )
        sandbox_executor.record_rollback_prepare()
        sandbox_executor.record_rollback_result(
            {"status": "completed", "executed": False}
        )

        verification_boundary = ControlledMutationVerificationBoundary(
            "closed-loop-verification"
        )
        verification_boundary.record_verification_planned(
            "verification-closed-loop",
            sandbox_id,
            mutation_id,
            verification_strategy=verification_strategy,
        )
        verification_boundary.record_verification_started(
            "verification-closed-loop",
            sandbox_id,
            mutation_id,
            verification_strategy=verification_strategy,
            verification_summary={"executed": False},
        )
        verification_boundary.record_verification_passed(
            "verification-closed-loop",
            sandbox_id,
            mutation_id,
            verification_summary={"status": "passed", "executed": False},
            verification_strategy=verification_strategy,
        )

        rollback_boundary = ControlledMutationRollbackBoundary(
            "closed-loop-rollback"
        )
        rollback_boundary.record_rollback_planned(
            "rollback-closed-loop",
            sandbox_id,
            mutation_id,
            rollback_strategy=rollback_strategy,
        )
        rollback_boundary.record_rollback_started(
            "rollback-closed-loop",
            sandbox_id,
            mutation_id,
            rollback_strategy=rollback_strategy,
            rollback_summary={"executed": False},
        )
        rollback_boundary.record_rollback_completed(
            "rollback-closed-loop",
            sandbox_id,
            mutation_id,
            rollback_summary={"status": "completed", "executed": False},
            rollback_strategy=rollback_strategy,
        )

        bundle = ControlledMutationEvidenceBundle(
            "closed-loop-bundle",
            mutation_boundary,
            sandbox_plan,
            sandbox_executor,
            verification_boundary,
            rollback_boundary,
            evidence_refs={"artifact": "closed-loop-seal"},
            metadata={"seal_version": "v1"},
            runtime_args={"dry_run": True},
        )

        return {
            "mutation_id": mutation_id,
            "sandbox_id": sandbox_id,
            "target_path": target_path,
            "mutation_boundary": mutation_boundary,
            "adapter": adapter,
            "sandbox_plan": sandbox_plan,
            "sandbox_executor": sandbox_executor,
            "verification_boundary": verification_boundary,
            "rollback_boundary": rollback_boundary,
            "bundle": bundle,
            "fingerprints": {
                "actions": [action.fingerprint for action in mutation_boundary.list_actions()],
                "plan": sandbox_plan.fingerprint,
                "executor": sandbox_executor.fingerprint,
                "verification": verification_boundary.fingerprint,
                "rollback": rollback_boundary.fingerprint,
                "bundle": bundle.fingerprint,
                "adapter": adapter.fingerprint,
            },
        }

    def test_closed_loop_flow_success(self) -> None:
        flow = self._run_closed_loop()
        bundle = flow["bundle"]

        self.assertEqual(bundle.bundle_id, "closed-loop-bundle")
        self.assertEqual(bundle.mutation_id, "closed-loop-mutation")
        self.assertEqual(bundle.sandbox_id, "closed-loop-sandbox")
        self.assertEqual(bundle.lifecycle_summary["action_count"], 5)
        self.assertEqual(bundle.execution_summary["record_count"], 7)
        self.assertEqual(bundle.verification_summary["record_count"], 3)
        self.assertEqual(bundle.rollback_summary["record_count"], 3)

    def test_lifecycle_ordering_deterministic(self) -> None:
        flow = self._run_closed_loop()

        self.assertEqual(
            flow["bundle"].lifecycle_summary["phases"],
            [
                "planned",
                "applied",
                "verified",
                "rollback_planned",
                "rolled_back",
            ],
        )
        self.assertEqual(
            [action.sequence for action in flow["mutation_boundary"].list_actions()],
            [1, 2, 3, 4, 5],
        )

    def test_execution_verification_rollback_ordering_deterministic(self) -> None:
        flow = self._run_closed_loop()
        bundle = flow["bundle"]

        self.assertEqual(
            bundle.execution_summary["phases"],
            [
                "workspace_copy",
                "patch_prepare",
                "patch_apply",
                "verification_prepare",
                "verification_result",
                "rollback_prepare",
                "rollback_result",
            ],
        )
        self.assertEqual(
            bundle.verification_summary["phases"],
            ["planned", "started", "passed"],
        )
        self.assertEqual(
            bundle.rollback_summary["phases"],
            ["planned", "started", "completed"],
        )

    def test_cross_layer_identity_consistency(self) -> None:
        flow = self._run_closed_loop()
        mutation_id = flow["mutation_id"]
        sandbox_id = flow["sandbox_id"]

        self.assertTrue(
            all(
                action.mutation_id == mutation_id
                for action in flow["mutation_boundary"].list_actions()
            )
        )
        self.assertTrue(
            all(
                record.mutation_id == mutation_id and record.sandbox_id == sandbox_id
                for record in flow["sandbox_executor"].list_records()
            )
        )
        self.assertTrue(
            all(
                record.mutation_id == mutation_id and record.sandbox_id == sandbox_id
                for record in flow["verification_boundary"].list_records()
            )
        )
        self.assertTrue(
            all(
                record.mutation_id == mutation_id and record.sandbox_id == sandbox_id
                for record in flow["rollback_boundary"].list_records()
            )
        )

    def test_repeated_closed_loop_produces_same_fingerprints(self) -> None:
        first = self._run_closed_loop()
        second = self._run_closed_loop()

        self.assertEqual(first["fingerprints"], second["fingerprints"])

    def test_bundle_deterministic_fingerprint(self) -> None:
        first = self._run_closed_loop()["bundle"]
        second = self._run_closed_loop()["bundle"]

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_evidence_isolation_after_mutation(self) -> None:
        flow = self._run_closed_loop()
        bundle = flow["bundle"]
        fingerprint = bundle.fingerprint
        lifecycle_summary = bundle.lifecycle_summary
        execution_summary = bundle.execution_summary

        flow["mutation_boundary"].record_failure(
            flow["mutation_id"],
            {"late": "failure"},
        )
        flow["sandbox_plan"].plan_patch_apply({"patch_id": "late-change"})
        flow["sandbox_executor"].record_patch_apply(
            patch_identity={"patch_id": "late-change"}
        )
        flow["verification_boundary"].record_verification_failed(
            "verification-late",
            flow["sandbox_id"],
            flow["mutation_id"],
            {"status": "failed", "executed": False},
        )
        flow["rollback_boundary"].record_rollback_failed(
            "rollback-late",
            flow["sandbox_id"],
            flow["mutation_id"],
            {"status": "failed", "executed": False},
        )

        self.assertEqual(bundle.fingerprint, fingerprint)
        self.assertEqual(bundle.lifecycle_summary, lifecycle_summary)
        self.assertEqual(bundle.execution_summary, execution_summary)

    def test_copy_on_read_immutable_behavior(self) -> None:
        bundle = self._run_closed_loop()["bundle"]
        lifecycle_summary = bundle.lifecycle_summary
        execution_summary = bundle.execution_summary
        evidence_refs = bundle.evidence_refs
        metadata = bundle.metadata
        runtime_args = bundle.runtime_args

        lifecycle_summary["phases"].append("polluted")
        execution_summary["phases"].append("polluted")
        evidence_refs["artifact"] = "polluted"
        metadata["seal_version"] = "polluted"
        runtime_args["dry_run"] = False

        self.assertEqual(
            bundle.lifecycle_summary["phases"],
            [
                "planned",
                "applied",
                "verified",
                "rollback_planned",
                "rolled_back",
            ],
        )
        self.assertEqual(
            bundle.execution_summary["phases"],
            [
                "workspace_copy",
                "patch_prepare",
                "patch_apply",
                "verification_prepare",
                "verification_result",
                "rollback_prepare",
                "rollback_result",
            ],
        )
        self.assertEqual(bundle.evidence_refs, {"artifact": "closed-loop-seal"})
        self.assertEqual(bundle.metadata, {"seal_version": "v1"})
        self.assertEqual(bundle.runtime_args, {"dry_run": True})

    def test_evidence_aggregation_does_not_modify_source_records(self) -> None:
        flow = self._run_closed_loop()
        source_before = {
            "actions": [action.fingerprint for action in flow["mutation_boundary"].list_actions()],
            "executor": [
                record.fingerprint for record in flow["sandbox_executor"].list_records()
            ],
            "verification": [
                record.fingerprint
                for record in flow["verification_boundary"].list_records()
            ],
            "rollback": [
                record.fingerprint for record in flow["rollback_boundary"].list_records()
            ],
        }

        self.assertTrue(flow["bundle"].fingerprint)

        source_after = {
            "actions": [action.fingerprint for action in flow["mutation_boundary"].list_actions()],
            "executor": [
                record.fingerprint for record in flow["sandbox_executor"].list_records()
            ],
            "verification": [
                record.fingerprint
                for record in flow["verification_boundary"].list_records()
            ],
            "rollback": [
                record.fingerprint for record in flow["rollback_boundary"].list_records()
            ],
        }
        self.assertEqual(source_after, source_before)

    def test_no_real_workspace_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            workspace_root = Path(tmp_name)
            flow = self._run_closed_loop(workspace_root)

            self.assertFalse(Path(flow["target_path"]).exists())
            self.assertEqual(list(workspace_root.iterdir()), [])
            self.assertTrue(flow["bundle"].fingerprint)


if __name__ == "__main__":
    unittest.main()
