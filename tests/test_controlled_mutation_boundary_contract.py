from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledMutationBoundaryContractTest(unittest.TestCase):
    def _boundary(self, boundary_id: str = "mutation-boundary"):
        from core.runtime.controlled_mutation_boundary import ControlledMutationBoundary

        return ControlledMutationBoundary(boundary_id)

    def test_boundary_id_validation(self) -> None:
        from core.runtime.controlled_mutation_boundary import (
            ControlledMutationBoundary,
            ControlledMutationRejected,
        )

        with self.assertRaises(ControlledMutationRejected):
            ControlledMutationBoundary("")

    def test_mutation_id_validation(self) -> None:
        from core.runtime.controlled_mutation_boundary import ControlledMutationRejected

        with self.assertRaises(ControlledMutationRejected):
            self._boundary().plan_mutation("")

    def test_planned_apply_verify_rollback_failure_blocked_record_success(self) -> None:
        boundary = self._boundary()

        planned = boundary.plan_mutation(
            "mutation-1",
            metadata={"intent": "patch"},
            runtime_args={"mode": "dry"},
            evidence_refs={"plan": "evidence-1"},
            rollback_refs={"inverse": "rollback-1"},
        )
        applied = boundary.record_apply("mutation-1", result={"ok": True})
        verified = boundary.record_verify("mutation-1", result={"verified": True})
        rollback_plan = boundary.record_rollback_plan(
            "mutation-1",
            reason={"reason": "verification_failed"},
            rollback_refs={"inverse": "rollback-1"},
        )
        rolled_back = boundary.record_rollback(
            "mutation-1",
            result={"rolled_back": True},
        )
        failed = boundary.record_failure(
            "mutation-2",
            error={"error": "apply_failed"},
        )
        blocked = boundary.record_blocked(
            "mutation-3",
            reason={"reason": "policy"},
        )

        self.assertEqual(planned.phase, "planned")
        self.assertEqual(applied.phase, "applied")
        self.assertEqual(verified.phase, "verified")
        self.assertEqual(rollback_plan.phase, "rollback_planned")
        self.assertEqual(rolled_back.phase, "rolled_back")
        self.assertEqual(failed.phase, "failed")
        self.assertEqual(blocked.phase, "blocked")
        self.assertEqual(planned.action.metadata, {"intent": "patch"})
        self.assertEqual(planned.action.runtime_args, {"mode": "dry"})
        self.assertEqual(planned.action.evidence_refs, {"plan": "evidence-1"})
        self.assertEqual(planned.action.rollback_refs, {"inverse": "rollback-1"})
        self.assertEqual(failed.action.error, {"error": "apply_failed"})
        self.assertEqual(blocked.action.reason, {"reason": "policy"})

    def test_deterministic_sequence(self) -> None:
        boundary = self._boundary()
        boundary.plan_mutation("mutation-1")
        boundary.record_apply("mutation-1")
        boundary.record_verify("mutation-1")
        boundary.record_rollback_plan("mutation-1")
        boundary.record_rollback("mutation-1")
        boundary.record_failure("mutation-2", {"error": "boom"})
        boundary.record_blocked("mutation-3", {"reason": "policy"})

        actions = boundary.list_actions()
        self.assertEqual([action.sequence for action in actions], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(
            [action.action_id for action in actions],
            [
                "mutation-boundary:mutation-1:planned:1",
                "mutation-boundary:mutation-1:applied:2",
                "mutation-boundary:mutation-1:verified:3",
                "mutation-boundary:mutation-1:rollback_planned:4",
                "mutation-boundary:mutation-1:rolled_back:5",
                "mutation-boundary:mutation-2:failed:6",
                "mutation-boundary:mutation-3:blocked:7",
            ],
        )

    def test_deterministic_action_fingerprint(self) -> None:
        first = self._boundary().plan_mutation(
            "mutation-1",
            metadata={"b": 2, "a": 1},
            runtime_args={"x": {"b": 2, "a": 1}},
        )
        second = self._boundary().plan_mutation(
            "mutation-1",
            metadata={"a": 1, "b": 2},
            runtime_args={"x": {"a": 1, "b": 2}},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.action_fingerprint, second.action_fingerprint)

    def test_deterministic_boundary_fingerprint(self) -> None:
        first = self._boundary()
        second = self._boundary()
        for boundary in (first, second):
            boundary.plan_mutation("mutation-1", metadata={"a": 1, "b": 2})
            boundary.record_apply("mutation-1", result={"ok": True})
            boundary.record_verify("mutation-1", result={"verified": True})

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_boundary import ControlledMutationAction

        first = ControlledMutationAction(
            "action-1",
            "boundary-1",
            "mutation-1",
            "planned",
            1,
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = ControlledMutationAction(
            "action-1",
            "boundary-1",
            "mutation-1",
            "planned",
            1,
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        action = self._boundary().plan_mutation(
            "mutation-1",
            metadata={"items": [{"id": "metadata"}]},
            runtime_args={"items": [{"id": "runtime"}]},
            evidence_refs={"items": [{"id": "evidence"}]},
            rollback_refs={"items": [{"id": "rollback"}]},
        ).action
        metadata = action.metadata
        runtime_args = action.runtime_args
        evidence_refs = action.evidence_refs
        rollback_refs = action.rollback_refs

        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"
        evidence_refs["items"][0]["id"] = "polluted"
        rollback_refs["items"][0]["id"] = "polluted"

        self.assertEqual(action.metadata, {"items": [{"id": "metadata"}]})
        self.assertEqual(action.runtime_args, {"items": [{"id": "runtime"}]})
        self.assertEqual(action.evidence_refs, {"items": [{"id": "evidence"}]})
        self.assertEqual(action.rollback_refs, {"items": [{"id": "rollback"}]})

    def test_list_actions_immutable_behavior(self) -> None:
        boundary = self._boundary()
        boundary.plan_mutation("mutation-1", metadata={"source": "contract"})
        actions = boundary.list_actions()
        actions[0]._metadata = {"polluted": True}
        actions.clear()

        current = boundary.list_actions()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].metadata, {"source": "contract"})

    def test_input_mutation_isolation(self) -> None:
        boundary = self._boundary()
        metadata = {"items": [{"id": "metadata"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        evidence_refs = {"items": [{"id": "evidence"}]}
        rollback_refs = {"items": [{"id": "rollback"}]}
        before = copy.deepcopy((metadata, runtime_args, evidence_refs, rollback_refs))

        boundary.plan_mutation(
            "mutation-1",
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"
        evidence_refs["items"][0]["id"] = "polluted"
        rollback_refs["items"][0]["id"] = "polluted"
        action = boundary.list_actions()[0]

        self.assertEqual((action.metadata, action.runtime_args, action.evidence_refs, action.rollback_refs), before)

    def test_boundary_is_record_only_and_does_not_execute_mutation(self) -> None:
        boundary = self._boundary()

        result = boundary.record_apply(
            "mutation-1",
            result={"would_write": "workspace/file.txt"},
            runtime_args={"patch": "*** pretend patch ***"},
        )

        self.assertEqual(result.phase, "applied")
        self.assertFalse(hasattr(boundary, "scheduler"))
        self.assertFalse(hasattr(boundary, "agent_loop"))
        self.assertFalse(hasattr(boundary, "step_executor"))
        self.assertFalse(hasattr(boundary, "persistence_backend"))


if __name__ == "__main__":
    unittest.main()
