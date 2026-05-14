from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledMutationEvidenceBundleContractTest(unittest.TestCase):
    def _components(
        self,
        mutation_id: str = "mutation-1",
        sandbox_id: str = "sandbox-1",
    ):
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

        mutation_boundary = ControlledMutationBoundary("mutation-boundary")
        mutation_boundary.plan_mutation(
            mutation_id,
            evidence_refs={"plan": "mutation-evidence-1"},
        )
        mutation_boundary.record_apply(
            mutation_id,
            result={"ok": True},
            evidence_refs={"apply": "mutation-evidence-2"},
        )
        mutation_boundary.record_verify(
            mutation_id,
            result={"ok": True},
            evidence_refs={"verify": "mutation-evidence-3"},
        )

        sandbox_plan = (
            ControlledMutationSandboxPlan.plan_workspace_copy(
                sandbox_id,
                mutation_id,
                ["b.py", "a.py"],
                evidence_refs={"copy": "plan-evidence-1"},
                metadata={"source": "contract"},
                runtime_args={"mode": "dry"},
            )
            .plan_patch_apply({"patch_id": "patch-1", "sha256": "abc"})
            .plan_verification({"type": "command", "command": "pytest"})
            .plan_rollback_strategy({"type": "reverse_patch"})
        )

        sandbox_executor = ControlledMutationSandboxExecutor(
            "sandbox-executor",
            sandbox_plan,
        )
        sandbox_executor.record_workspace_copy()
        sandbox_executor.record_patch_prepare()
        sandbox_executor.record_patch_apply()
        sandbox_executor.record_verification_prepare()
        sandbox_executor.record_verification_result({"ok": True})
        sandbox_executor.record_rollback_prepare()
        sandbox_executor.record_rollback_result({"ok": True})

        verification_boundary = ControlledMutationVerificationBoundary(
            "verification-boundary"
        )
        verification_boundary.record_verification_planned(
            "verification-1",
            sandbox_id,
            mutation_id,
            verification_strategy={"type": "command", "command": "pytest"},
        )
        verification_boundary.record_verification_started(
            "verification-1",
            sandbox_id,
            mutation_id,
        )
        verification_boundary.record_verification_passed(
            "verification-1",
            sandbox_id,
            mutation_id,
            {"ok": True},
        )

        rollback_boundary = ControlledMutationRollbackBoundary("rollback-boundary")
        rollback_boundary.record_rollback_planned(
            "rollback-1",
            sandbox_id,
            mutation_id,
            rollback_strategy={"type": "reverse_patch"},
        )
        rollback_boundary.record_rollback_started(
            "rollback-1",
            sandbox_id,
            mutation_id,
        )
        rollback_boundary.record_rollback_completed(
            "rollback-1",
            sandbox_id,
            mutation_id,
            {"ok": True},
        )

        return {
            "mutation_boundary": mutation_boundary,
            "sandbox_plan": sandbox_plan,
            "sandbox_executor": sandbox_executor,
            "verification_boundary": verification_boundary,
            "rollback_boundary": rollback_boundary,
        }

    def _bundle(self, **overrides):
        from core.runtime.controlled_mutation_evidence_bundle import (
            ControlledMutationEvidenceBundle,
        )

        components = self._components()
        components.update(overrides)
        return ControlledMutationEvidenceBundle(
            "bundle-1",
            components["mutation_boundary"],
            components["sandbox_plan"],
            components["sandbox_executor"],
            components["verification_boundary"],
            components["rollback_boundary"],
            evidence_refs={"bundle": "evidence-1"},
            metadata={"source": "contract"},
            runtime_args={"mode": "dry"},
        )

    def test_bundle_id_validation(self) -> None:
        from core.runtime.controlled_mutation_evidence_bundle import (
            ControlledMutationEvidenceBundle,
            ControlledMutationEvidenceBundleRejected,
        )

        components = self._components()
        with self.assertRaises(ControlledMutationEvidenceBundleRejected):
            ControlledMutationEvidenceBundle(
                "",
                components["mutation_boundary"],
                components["sandbox_plan"],
                components["sandbox_executor"],
                components["verification_boundary"],
                components["rollback_boundary"],
            )

    def test_identity_consistency_success(self) -> None:
        bundle = self._bundle()

        self.assertEqual(bundle.bundle_id, "bundle-1")
        self.assertEqual(bundle.mutation_id, "mutation-1")
        self.assertEqual(bundle.sandbox_id, "sandbox-1")
        self.assertTrue(bundle.created_at)

    def test_mutation_id_mismatch_reject(self) -> None:
        from core.runtime.controlled_mutation_evidence_bundle import (
            ControlledMutationEvidenceBundle,
            ControlledMutationEvidenceBundleRejected,
        )
        from core.runtime.controlled_mutation_verification_boundary import (
            ControlledMutationVerificationBoundary,
        )

        components = self._components()
        mismatched = ControlledMutationVerificationBoundary("verification-boundary")
        mismatched.record_verification_planned(
            "verification-1",
            "sandbox-1",
            "different-mutation",
        )

        with self.assertRaises(ControlledMutationEvidenceBundleRejected):
            ControlledMutationEvidenceBundle(
                "bundle-1",
                components["mutation_boundary"],
                components["sandbox_plan"],
                components["sandbox_executor"],
                mismatched,
                components["rollback_boundary"],
            )

    def test_sandbox_id_mismatch_reject(self) -> None:
        from core.runtime.controlled_mutation_evidence_bundle import (
            ControlledMutationEvidenceBundle,
            ControlledMutationEvidenceBundleRejected,
        )
        from core.runtime.controlled_mutation_rollback_boundary import (
            ControlledMutationRollbackBoundary,
        )

        components = self._components()
        mismatched = ControlledMutationRollbackBoundary("rollback-boundary")
        mismatched.record_rollback_planned(
            "rollback-1",
            "different-sandbox",
            "mutation-1",
        )

        with self.assertRaises(ControlledMutationEvidenceBundleRejected):
            ControlledMutationEvidenceBundle(
                "bundle-1",
                components["mutation_boundary"],
                components["sandbox_plan"],
                components["sandbox_executor"],
                components["verification_boundary"],
                mismatched,
            )

    def test_lifecycle_summary_correctness(self) -> None:
        summary = self._bundle().lifecycle_summary

        self.assertEqual(summary["boundary_id"], "mutation-boundary")
        self.assertEqual(summary["action_count"], 3)
        self.assertEqual(summary["phases"], ["planned", "applied", "verified"])
        self.assertEqual(len(summary["action_fingerprints"]), 3)

    def test_execution_summary_correctness(self) -> None:
        summary = self._bundle().execution_summary

        self.assertEqual(summary["executor_id"], "sandbox-executor")
        self.assertEqual(summary["record_count"], 7)
        self.assertEqual(
            summary["phases"],
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

    def test_verification_summary_correctness(self) -> None:
        summary = self._bundle().verification_summary

        self.assertEqual(summary["boundary_id"], "verification-boundary")
        self.assertEqual(summary["record_count"], 3)
        self.assertEqual(summary["phases"], ["planned", "started", "passed"])

    def test_rollback_summary_correctness(self) -> None:
        summary = self._bundle().rollback_summary

        self.assertEqual(summary["boundary_id"], "rollback-boundary")
        self.assertEqual(summary["record_count"], 3)
        self.assertEqual(summary["phases"], ["planned", "started", "completed"])

    def test_deterministic_fingerprint(self) -> None:
        first = self._bundle()
        second = self._bundle()

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_evidence_bundle import (
            ControlledMutationEvidenceBundle,
        )

        first_components = self._components()
        second_components = self._components()
        first = ControlledMutationEvidenceBundle(
            "bundle-1",
            first_components["mutation_boundary"],
            first_components["sandbox_plan"],
            first_components["sandbox_executor"],
            first_components["verification_boundary"],
            first_components["rollback_boundary"],
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = ControlledMutationEvidenceBundle(
            "bundle-1",
            second_components["mutation_boundary"],
            second_components["sandbox_plan"],
            second_components["sandbox_executor"],
            second_components["verification_boundary"],
            second_components["rollback_boundary"],
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_when_evidence_changes(self) -> None:
        from core.runtime.controlled_mutation_evidence_bundle import (
            ControlledMutationEvidenceBundle,
        )

        first_components = self._components()
        second_components = self._components()
        second_components["mutation_boundary"].record_blocked(
            "mutation-1",
            {"reason": "policy"},
        )

        first = ControlledMutationEvidenceBundle(
            "bundle-1",
            first_components["mutation_boundary"],
            first_components["sandbox_plan"],
            first_components["sandbox_executor"],
            first_components["verification_boundary"],
            first_components["rollback_boundary"],
        )
        second = ControlledMutationEvidenceBundle(
            "bundle-1",
            second_components["mutation_boundary"],
            second_components["sandbox_plan"],
            second_components["sandbox_executor"],
            second_components["verification_boundary"],
            second_components["rollback_boundary"],
        )

        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        bundle = self._bundle()
        evidence_refs = bundle.evidence_refs
        metadata = bundle.metadata
        runtime_args = bundle.runtime_args
        lifecycle_summary = bundle.lifecycle_summary

        evidence_refs["bundle"] = "polluted"
        metadata["source"] = "polluted"
        runtime_args["mode"] = "polluted"
        lifecycle_summary["phases"].append("polluted")

        self.assertEqual(bundle.evidence_refs, {"bundle": "evidence-1"})
        self.assertEqual(bundle.metadata, {"source": "contract"})
        self.assertEqual(bundle.runtime_args, {"mode": "dry"})
        self.assertEqual(
            bundle.lifecycle_summary["phases"],
            ["planned", "applied", "verified"],
        )

    def test_external_mutation_isolation(self) -> None:
        components = self._components()
        bundle = self._bundle(**components)
        fingerprint = bundle.fingerprint
        lifecycle_summary = bundle.lifecycle_summary

        components["mutation_boundary"].record_failure(
            "mutation-1",
            {"error": "late"},
        )
        components["sandbox_executor"].record_verification_result({"ok": False})
        components["verification_boundary"].record_verification_failed(
            "verification-2",
            "sandbox-1",
            "mutation-1",
            {"ok": False},
        )
        components["rollback_boundary"].record_rollback_failed(
            "rollback-2",
            "sandbox-1",
            "mutation-1",
            {"ok": False},
        )

        self.assertEqual(bundle.fingerprint, fingerprint)
        self.assertEqual(bundle.lifecycle_summary, lifecycle_summary)

    def test_bundle_is_aggregation_only_and_does_not_attach_runtime_executors(self) -> None:
        bundle = self._bundle()

        self.assertFalse(hasattr(bundle, "scheduler"))
        self.assertFalse(hasattr(bundle, "agent_loop"))
        self.assertFalse(hasattr(bundle, "step_executor"))
        self.assertFalse(hasattr(bundle, "persistence_backend"))


if __name__ == "__main__":
    unittest.main()
