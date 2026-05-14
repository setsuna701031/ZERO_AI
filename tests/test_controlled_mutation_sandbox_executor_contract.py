from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledMutationSandboxExecutorContractTest(unittest.TestCase):
    def _plan(self):
        from core.runtime.controlled_mutation_sandbox_plan import (
            ControlledMutationSandboxPlan,
        )

        return (
            ControlledMutationSandboxPlan.plan_workspace_copy(
                "sandbox-1",
                "mutation-1",
                ["b.py", "a.py"],
                evidence_refs={"plan": "evidence-1"},
                metadata={"source": "contract"},
                runtime_args={"mode": "dry"},
            )
            .plan_patch_apply({"patch_id": "patch-1", "sha256": "abc"})
            .plan_verification({"type": "command", "command": "pytest"})
            .plan_rollback_strategy({"type": "reverse_patch"})
        )

    def _executor(self, executor_id: str = "executor-1", plan=None):
        from core.runtime.controlled_mutation_sandbox_executor import (
            ControlledMutationSandboxExecutor,
        )

        return ControlledMutationSandboxExecutor(
            executor_id,
            plan if plan is not None else self._plan(),
        )

    def test_executor_id_validation(self) -> None:
        from core.runtime.controlled_mutation_sandbox_executor import (
            ControlledMutationSandboxExecutor,
            ControlledMutationSandboxExecutorRejected,
        )

        with self.assertRaises(ControlledMutationSandboxExecutorRejected):
            ControlledMutationSandboxExecutor("", self._plan())

    def test_requires_controlled_mutation_sandbox_plan(self) -> None:
        from core.runtime.controlled_mutation_sandbox_executor import (
            ControlledMutationSandboxExecutor,
            ControlledMutationSandboxExecutorRejected,
        )

        with self.assertRaises(ControlledMutationSandboxExecutorRejected):
            ControlledMutationSandboxExecutor("executor-1", object())

    def test_workspace_copy_record_success(self) -> None:
        record = self._executor().record_workspace_copy(
            evidence_refs={"copy": "evidence-2"},
        )

        self.assertEqual(record.execution_phase, "workspace_copy")
        self.assertEqual(record.executor_id, "executor-1")
        self.assertEqual(record.sandbox_id, "sandbox-1")
        self.assertEqual(record.mutation_id, "mutation-1")
        self.assertEqual(record.target_paths, ["a.py", "b.py"])
        self.assertEqual(record.evidence_refs, {"copy": "evidence-2"})
        self.assertEqual(record.metadata, {"source": "contract"})
        self.assertEqual(record.runtime_args, {"mode": "dry"})

    def test_patch_prepare_record_success(self) -> None:
        record = self._executor().record_patch_prepare(
            metadata={"phase": "prepare"},
        )

        self.assertEqual(record.execution_phase, "patch_prepare")
        self.assertEqual(record.patch_identity, {"patch_id": "patch-1", "sha256": "abc"})
        self.assertEqual(record.metadata, {"phase": "prepare"})

    def test_patch_apply_record_success(self) -> None:
        record = self._executor().record_patch_apply(
            patch_identity={"patch_id": "patch-override"},
        )

        self.assertEqual(record.execution_phase, "patch_apply")
        self.assertEqual(record.patch_identity, {"patch_id": "patch-override"})

    def test_verification_prepare_record_success(self) -> None:
        record = self._executor().record_verification_prepare(
            runtime_args={"verify_timeout": 30},
        )

        self.assertEqual(record.execution_phase, "verification_prepare")
        self.assertEqual(record.runtime_args, {"verify_timeout": 30})

    def test_verification_result_record_success(self) -> None:
        record = self._executor().record_verification_result(
            {"ok": True, "command": "pytest"},
            evidence_refs={"verify": "evidence-3"},
        )

        self.assertEqual(record.execution_phase, "verification_result")
        self.assertEqual(record.verification_result, {"ok": True, "command": "pytest"})
        self.assertEqual(record.evidence_refs, {"verify": "evidence-3"})

    def test_rollback_prepare_record_success(self) -> None:
        record = self._executor().record_rollback_prepare(
            metadata={"rollback": "prepare"},
        )

        self.assertEqual(record.execution_phase, "rollback_prepare")
        self.assertEqual(record.metadata, {"rollback": "prepare"})

    def test_rollback_result_record_success(self) -> None:
        record = self._executor().record_rollback_result(
            {"ok": True, "strategy": "reverse_patch"},
            evidence_refs={"rollback": "evidence-4"},
        )

        self.assertEqual(record.execution_phase, "rollback_result")
        self.assertEqual(record.rollback_result, {"ok": True, "strategy": "reverse_patch"})
        self.assertEqual(record.evidence_refs, {"rollback": "evidence-4"})

    def test_deterministic_record_id_sequence(self) -> None:
        executor = self._executor()
        executor.record_workspace_copy()
        executor.record_patch_prepare()
        executor.record_patch_apply()
        executor.record_verification_prepare()
        executor.record_verification_result({"ok": True})
        executor.record_rollback_prepare()
        executor.record_rollback_result({"ok": True})

        self.assertEqual(
            [record.record_id for record in executor.list_records()],
            [
                "executor-1:sandbox-1:mutation-1:workspace_copy:1",
                "executor-1:sandbox-1:mutation-1:patch_prepare:2",
                "executor-1:sandbox-1:mutation-1:patch_apply:3",
                "executor-1:sandbox-1:mutation-1:verification_prepare:4",
                "executor-1:sandbox-1:mutation-1:verification_result:5",
                "executor-1:sandbox-1:mutation-1:rollback_prepare:6",
                "executor-1:sandbox-1:mutation-1:rollback_result:7",
            ],
        )
        self.assertEqual(
            [record.sequence for record in executor.list_records()],
            [1, 2, 3, 4, 5, 6, 7],
        )

    def test_deterministic_target_path_ordering(self) -> None:
        record = self._executor().record_workspace_copy(
            target_paths=["z.py", "a.py", "z.py", "src/b.py"],
        )

        self.assertEqual(record.target_paths, ["a.py", "src/b.py", "z.py"])

    def test_deterministic_record_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_sandbox_executor import (
            ControlledMutationSandboxExecutionRecord,
        )

        first = ControlledMutationSandboxExecutionRecord(
            "record-1",
            "executor-1",
            "sandbox-1",
            "mutation-1",
            "workspace_copy",
            1,
            target_paths=["b.py", "a.py"],
            metadata={"b": 2, "a": 1},
        )
        second = ControlledMutationSandboxExecutionRecord(
            "record-1",
            "executor-1",
            "sandbox-1",
            "mutation-1",
            "workspace_copy",
            1,
            target_paths=["a.py", "b.py"],
            metadata={"a": 1, "b": 2},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_deterministic_executor_fingerprint(self) -> None:
        first = self._executor()
        second = self._executor()
        first.record_workspace_copy(metadata={"b": 2, "a": 1})
        first.record_patch_prepare()
        second.record_workspace_copy(metadata={"a": 1, "b": 2})
        second.record_patch_prepare()

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_sandbox_executor import (
            ControlledMutationSandboxExecutionRecord,
        )

        first = ControlledMutationSandboxExecutionRecord(
            "record-1",
            "executor-1",
            "sandbox-1",
            "mutation-1",
            "workspace_copy",
            1,
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = ControlledMutationSandboxExecutionRecord(
            "record-1",
            "executor-1",
            "sandbox-1",
            "mutation-1",
            "workspace_copy",
            1,
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        record = self._executor().record_verification_result(
            {"items": [{"id": "verify"}]},
            target_paths=["b.py", "a.py"],
            evidence_refs={"items": [{"id": "evidence"}]},
            metadata={"items": [{"id": "metadata"}]},
            runtime_args={"items": [{"id": "runtime"}]},
        )
        target_paths = record.target_paths
        evidence_refs = record.evidence_refs
        metadata = record.metadata
        runtime_args = record.runtime_args
        verification_result = record.verification_result

        target_paths.append("polluted.py")
        evidence_refs["items"][0]["id"] = "polluted"
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"
        verification_result["items"][0]["id"] = "polluted"

        self.assertEqual(record.target_paths, ["a.py", "b.py"])
        self.assertEqual(record.evidence_refs, {"items": [{"id": "evidence"}]})
        self.assertEqual(record.metadata, {"items": [{"id": "metadata"}]})
        self.assertEqual(record.runtime_args, {"items": [{"id": "runtime"}]})
        self.assertEqual(record.verification_result, {"items": [{"id": "verify"}]})

    def test_list_records_immutable_behavior(self) -> None:
        executor = self._executor()
        executor.record_workspace_copy(metadata={"source": "contract"})
        records = executor.list_records()
        records[0]._metadata = {"polluted": True}
        records.clear()

        current = executor.list_records()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].metadata, {"source": "contract"})

    def test_input_mutation_isolation(self) -> None:
        target_paths = ["b.py", "a.py"]
        evidence_refs = {"items": [{"id": "evidence"}]}
        metadata = {"items": [{"id": "metadata"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        patch_identity = {"items": [{"id": "patch"}]}
        verification_result = {"items": [{"id": "verify"}]}
        rollback_result = {"items": [{"id": "rollback"}]}
        before = copy.deepcopy(
            (
                ["a.py", "b.py"],
                evidence_refs,
                metadata,
                runtime_args,
                patch_identity,
                verification_result,
                rollback_result,
            )
        )
        executor = self._executor()

        patch_record = executor.record_patch_apply(
            patch_identity=patch_identity,
            target_paths=target_paths,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        verification_record = executor.record_verification_result(
            verification_result,
            target_paths=target_paths,
        )
        rollback_record = executor.record_rollback_result(
            rollback_result,
            target_paths=target_paths,
        )

        target_paths.append("polluted.py")
        evidence_refs["items"][0]["id"] = "polluted"
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"
        patch_identity["items"][0]["id"] = "polluted"
        verification_result["items"][0]["id"] = "polluted"
        rollback_result["items"][0]["id"] = "polluted"

        self.assertEqual(
            (
                patch_record.target_paths,
                patch_record.evidence_refs,
                patch_record.metadata,
                patch_record.runtime_args,
                patch_record.patch_identity,
                verification_record.verification_result,
                rollback_record.rollback_result,
            ),
            before,
        )

    def test_executor_is_record_only_and_does_not_attach_runtime_executors(self) -> None:
        executor = self._executor()

        executor.record_workspace_copy(runtime_args={"copy": "planned-only"})

        self.assertFalse(hasattr(executor, "scheduler"))
        self.assertFalse(hasattr(executor, "agent_loop"))
        self.assertFalse(hasattr(executor, "step_executor"))
        self.assertFalse(hasattr(executor, "persistence_backend"))


if __name__ == "__main__":
    unittest.main()
