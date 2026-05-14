from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledMutationAdapterContractTest(unittest.TestCase):
    def _boundary(self, boundary_id: str = "boundary-1"):
        from core.runtime.controlled_mutation_boundary import ControlledMutationBoundary

        return ControlledMutationBoundary(boundary_id)

    def _adapter(self, adapter_id: str = "adapter-1", boundary=None):
        from core.runtime.controlled_mutation_adapter import ControlledMutationAdapter

        return ControlledMutationAdapter(
            adapter_id,
            boundary if boundary is not None else self._boundary(),
        )

    def test_adapter_id_validation(self) -> None:
        from core.runtime.controlled_mutation_adapter import (
            ControlledMutationAdapter,
            ControlledMutationAdapterRejected,
        )

        with self.assertRaises(ControlledMutationAdapterRejected):
            ControlledMutationAdapter("", self._boundary())

    def test_requires_boundary_instance(self) -> None:
        from core.runtime.controlled_mutation_adapter import (
            ControlledMutationAdapter,
            ControlledMutationAdapterRejected,
        )

        with self.assertRaises(ControlledMutationAdapterRejected):
            ControlledMutationAdapter("adapter-1", object())

    def test_planned_emission(self) -> None:
        boundary = self._boundary()
        result = self._adapter(boundary=boundary).emit_planned(
            "mutation-1",
            metadata={"source": "contract"},
            runtime_args={"mode": "dry"},
            evidence_refs={"plan": "evidence-1"},
            rollback_refs={"inverse": "rollback-1"},
        )

        action = boundary.list_actions()[0]
        self.assertEqual(result.phase, "planned")
        self.assertEqual(action.phase, "planned")
        self.assertEqual(action.metadata, {"source": "contract"})
        self.assertEqual(action.runtime_args, {"mode": "dry"})
        self.assertEqual(action.evidence_refs, {"plan": "evidence-1"})
        self.assertEqual(action.rollback_refs, {"inverse": "rollback-1"})

    def test_applied_emission(self) -> None:
        boundary = self._boundary()
        result = self._adapter(boundary=boundary).emit_applied(
            "mutation-1",
            metadata={"phase": "apply"},
        )

        self.assertEqual(result.phase, "applied")
        self.assertEqual(boundary.list_actions()[0].phase, "applied")
        self.assertEqual(boundary.list_actions()[0].metadata, {"phase": "apply"})

    def test_verified_emission(self) -> None:
        boundary = self._boundary()
        result = self._adapter(boundary=boundary).emit_verified(
            "mutation-1",
            evidence_refs={"verify": "evidence-1"},
        )

        self.assertEqual(result.phase, "verified")
        self.assertEqual(boundary.list_actions()[0].phase, "verified")
        self.assertEqual(boundary.list_actions()[0].evidence_refs, {"verify": "evidence-1"})

    def test_rollback_plan_emission(self) -> None:
        boundary = self._boundary()
        result = self._adapter(boundary=boundary).emit_rollback_plan(
            "mutation-1",
            rollback_refs={"inverse": "rollback-1"},
        )

        self.assertEqual(result.phase, "rollback_planned")
        self.assertEqual(boundary.list_actions()[0].phase, "rollback_planned")
        self.assertEqual(boundary.list_actions()[0].rollback_refs, {"inverse": "rollback-1"})

    def test_rolled_back_emission(self) -> None:
        boundary = self._boundary()
        result = self._adapter(boundary=boundary).emit_rolled_back(
            "mutation-1",
            evidence_refs={"rollback": "evidence-1"},
        )

        self.assertEqual(result.phase, "rolled_back")
        self.assertEqual(boundary.list_actions()[0].phase, "rolled_back")
        self.assertEqual(boundary.list_actions()[0].evidence_refs, {"rollback": "evidence-1"})

    def test_failed_emission(self) -> None:
        boundary = self._boundary()
        result = self._adapter(boundary=boundary).emit_failed(
            "mutation-1",
            {"error": "apply_failed"},
            evidence_refs={"failure": "evidence-1"},
        )

        action = boundary.list_actions()[0]
        self.assertEqual(result.phase, "failed")
        self.assertEqual(action.phase, "failed")
        self.assertEqual(action.error, {"error": "apply_failed"})
        self.assertEqual(action.evidence_refs, {"failure": "evidence-1"})

    def test_blocked_emission(self) -> None:
        boundary = self._boundary()
        result = self._adapter(boundary=boundary).emit_blocked(
            "mutation-1",
            {"reason": "policy"},
            metadata={"source": "policy"},
        )

        action = boundary.list_actions()[0]
        self.assertEqual(result.phase, "blocked")
        self.assertEqual(action.phase, "blocked")
        self.assertEqual(action.reason, {"reason": "policy"})
        self.assertEqual(action.metadata, {"source": "policy"})

    def test_adapter_does_not_mutate_metadata_runtime_args_evidence_refs_rollback_refs(self) -> None:
        adapter = self._adapter()
        metadata = {"items": [{"id": "metadata"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        evidence_refs = {"items": [{"id": "evidence"}]}
        rollback_refs = {"items": [{"id": "rollback"}]}
        before = copy.deepcopy((metadata, runtime_args, evidence_refs, rollback_refs))

        adapter.emit_planned(
            "mutation-1",
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

        self.assertEqual((metadata, runtime_args, evidence_refs, rollback_refs), before)

    def test_adapter_fingerprint_deterministic(self) -> None:
        first = self._adapter()
        second = self._adapter()
        first.emit_planned(
            "mutation-1",
            metadata={"b": 2, "a": 1},
            runtime_args={"x": {"b": 2, "a": 1}},
        )
        second.emit_planned(
            "mutation-1",
            metadata={"a": 1, "b": 2},
            runtime_args={"x": {"a": 1, "b": 2}},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_adapter_event_order_follows_boundary(self) -> None:
        boundary = self._boundary()
        adapter = self._adapter(boundary=boundary)
        adapter.emit_planned("mutation-1")
        adapter.emit_applied("mutation-1")
        adapter.emit_verified("mutation-1")
        adapter.emit_rollback_plan("mutation-1")
        adapter.emit_rolled_back("mutation-1")
        adapter.emit_failed("mutation-2", {"error": "boom"})
        adapter.emit_blocked("mutation-3", {"reason": "policy"})

        self.assertEqual(
            [action.phase for action in boundary.list_actions()],
            [
                "planned",
                "applied",
                "verified",
                "rollback_planned",
                "rolled_back",
                "failed",
                "blocked",
            ],
        )

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        first = self._adapter()
        second = self._adapter()
        first.emit_planned("mutation-1")
        second.emit_planned("mutation-1")

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_adapter_is_thin_and_does_not_attach_runtime_executors(self) -> None:
        adapter = self._adapter()

        adapter.emit_applied("mutation-1", runtime_args={"patch": "*** pretend patch ***"})

        self.assertFalse(hasattr(adapter, "scheduler"))
        self.assertFalse(hasattr(adapter, "agent_loop"))
        self.assertFalse(hasattr(adapter, "step_executor"))
        self.assertFalse(hasattr(adapter, "persistence_backend"))


if __name__ == "__main__":
    unittest.main()
