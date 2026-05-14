from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledMutationSandboxPlanContractTest(unittest.TestCase):
    def _plan(self):
        from core.runtime.controlled_mutation_sandbox_plan import (
            ControlledMutationSandboxPlan,
        )

        return ControlledMutationSandboxPlan.plan_workspace_copy(
            "sandbox-1",
            "mutation-1",
            ["b.py", "a.py"],
            evidence_refs={"copy": "evidence-1"},
            metadata={"source": "contract"},
            runtime_args={"mode": "dry"},
        )

    def test_sandbox_id_validation(self) -> None:
        from core.runtime.controlled_mutation_sandbox_plan import (
            ControlledMutationSandboxPlan,
            ControlledMutationSandboxPlanRejected,
        )

        with self.assertRaises(ControlledMutationSandboxPlanRejected):
            ControlledMutationSandboxPlan("", "mutation-1")

    def test_mutation_id_validation(self) -> None:
        from core.runtime.controlled_mutation_sandbox_plan import (
            ControlledMutationSandboxPlan,
            ControlledMutationSandboxPlanRejected,
        )

        with self.assertRaises(ControlledMutationSandboxPlanRejected):
            ControlledMutationSandboxPlan("sandbox-1", "")

    def test_workspace_copy_plan_success(self) -> None:
        plan = self._plan()

        self.assertEqual(plan.sandbox_id, "sandbox-1")
        self.assertEqual(plan.mutation_id, "mutation-1")
        self.assertEqual(plan.target_paths, ["a.py", "b.py"])
        self.assertEqual(plan.evidence_refs, {"copy": "evidence-1"})
        self.assertEqual(plan.metadata, {"source": "contract"})
        self.assertEqual(plan.runtime_args, {"mode": "dry"})
        self.assertTrue(plan.created_at)

    def test_patch_apply_plan_success(self) -> None:
        plan = self._plan().plan_patch_apply(
            {"patch_id": "patch-1", "sha256": "abc"},
            evidence_refs={"patch": "evidence-2"},
        )

        self.assertEqual(plan.patch_identity, {"patch_id": "patch-1", "sha256": "abc"})
        self.assertEqual(plan.evidence_refs, {"patch": "evidence-2"})

    def test_verification_plan_success(self) -> None:
        plan = self._plan().plan_verification(
            {"type": "command", "command": "pytest tests/unit.py"},
            runtime_args={"verify_timeout": 30},
        )

        self.assertEqual(
            plan.verification_strategy,
            {"type": "command", "command": "pytest tests/unit.py"},
        )
        self.assertEqual(plan.runtime_args, {"verify_timeout": 30})

    def test_rollback_strategy_plan_success(self) -> None:
        plan = self._plan().plan_rollback_strategy(
            {"type": "reverse_patch", "patch_id": "rollback-1"},
            metadata={"rollback": "planned"},
        )

        self.assertEqual(
            plan.rollback_strategy,
            {"type": "reverse_patch", "patch_id": "rollback-1"},
        )
        self.assertEqual(plan.metadata, {"rollback": "planned"})

    def test_deterministic_target_path_ordering(self) -> None:
        from core.runtime.controlled_mutation_sandbox_plan import (
            ControlledMutationSandboxPlan,
        )

        plan = ControlledMutationSandboxPlan.plan_workspace_copy(
            "sandbox-1",
            "mutation-1",
            ["z.py", "a.py", "z.py", "src/b.py"],
        )

        self.assertEqual(plan.target_paths, ["a.py", "src/b.py", "z.py"])

    def test_deterministic_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_sandbox_plan import (
            ControlledMutationSandboxPlan,
        )

        first = ControlledMutationSandboxPlan.plan_workspace_copy(
            "sandbox-1",
            "mutation-1",
            ["b.py", "a.py"],
            evidence_refs={"b": 2, "a": 1},
            metadata={"x": {"b": 2, "a": 1}},
            runtime_args={"mode": "dry"},
        ).plan_patch_apply({"sha256": "abc", "patch_id": "patch-1"})
        second = ControlledMutationSandboxPlan.plan_workspace_copy(
            "sandbox-1",
            "mutation-1",
            ["a.py", "b.py"],
            evidence_refs={"a": 1, "b": 2},
            metadata={"x": {"a": 1, "b": 2}},
            runtime_args={"mode": "dry"},
        ).plan_patch_apply({"patch_id": "patch-1", "sha256": "abc"})

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_after_plan_update(self) -> None:
        plan = self._plan()
        first = plan.fingerprint
        plan.plan_patch_apply({"patch_id": "patch-1"})
        second = plan.fingerprint
        plan.plan_verification({"type": "command", "command": "pytest"})
        third = plan.fingerprint
        plan.plan_rollback_strategy({"type": "reverse_patch"})
        fourth = plan.fingerprint

        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)
        self.assertNotEqual(third, fourth)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_sandbox_plan import (
            ControlledMutationSandboxPlan,
        )

        first = ControlledMutationSandboxPlan(
            "sandbox-1",
            "mutation-1",
            target_paths=["a.py"],
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = ControlledMutationSandboxPlan(
            "sandbox-1",
            "mutation-1",
            target_paths=["a.py"],
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        plan = self._plan().plan_patch_apply(
            {"items": [{"id": "patch"}]},
        )
        target_paths = plan.target_paths
        evidence_refs = plan.evidence_refs
        metadata = plan.metadata
        runtime_args = plan.runtime_args
        patch_identity = plan.patch_identity

        target_paths.append("polluted.py")
        evidence_refs["copy"] = "polluted"
        metadata["source"] = "polluted"
        runtime_args["mode"] = "polluted"
        patch_identity["items"][0]["id"] = "polluted"

        self.assertEqual(plan.target_paths, ["a.py", "b.py"])
        self.assertEqual(plan.evidence_refs, {"copy": "evidence-1"})
        self.assertEqual(plan.metadata, {"source": "contract"})
        self.assertEqual(plan.runtime_args, {"mode": "dry"})
        self.assertEqual(plan.patch_identity, {"items": [{"id": "patch"}]})

    def test_input_mutation_isolation(self) -> None:
        from core.runtime.controlled_mutation_sandbox_plan import (
            ControlledMutationSandboxPlan,
        )

        target_paths = ["b.py", "a.py"]
        evidence_refs = {"items": [{"id": "evidence"}]}
        metadata = {"items": [{"id": "metadata"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        patch_identity = {"items": [{"id": "patch"}]}
        verification_strategy = {"items": [{"id": "verify"}]}
        rollback_strategy = {"items": [{"id": "rollback"}]}
        before = copy.deepcopy(
            (
                ["a.py", "b.py"],
                evidence_refs,
                metadata,
                runtime_args,
                patch_identity,
                verification_strategy,
                rollback_strategy,
            )
        )

        plan = ControlledMutationSandboxPlan.plan_workspace_copy(
            "sandbox-1",
            "mutation-1",
            target_paths,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        plan.plan_patch_apply(patch_identity)
        plan.plan_verification(verification_strategy)
        plan.plan_rollback_strategy(rollback_strategy)

        target_paths.append("polluted.py")
        evidence_refs["items"][0]["id"] = "polluted"
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"
        patch_identity["items"][0]["id"] = "polluted"
        verification_strategy["items"][0]["id"] = "polluted"
        rollback_strategy["items"][0]["id"] = "polluted"

        self.assertEqual(
            (
                plan.target_paths,
                plan.evidence_refs,
                plan.metadata,
                plan.runtime_args,
                plan.patch_identity,
                plan.verification_strategy,
                plan.rollback_strategy,
            ),
            before,
        )

    def test_plan_is_data_only_and_does_not_attach_executors(self) -> None:
        plan = self._plan()

        self.assertFalse(hasattr(plan, "scheduler"))
        self.assertFalse(hasattr(plan, "agent_loop"))
        self.assertFalse(hasattr(plan, "step_executor"))
        self.assertFalse(hasattr(plan, "persistence_backend"))


if __name__ == "__main__":
    unittest.main()
