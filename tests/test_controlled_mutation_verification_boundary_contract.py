from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ControlledMutationVerificationBoundaryContractTest(unittest.TestCase):
    def _boundary(self, boundary_id: str = "verification-boundary"):
        from core.runtime.controlled_mutation_verification_boundary import (
            ControlledMutationVerificationBoundary,
        )

        return ControlledMutationVerificationBoundary(boundary_id)

    def test_boundary_id_validation(self) -> None:
        from core.runtime.controlled_mutation_verification_boundary import (
            ControlledMutationVerificationBoundary,
            ControlledMutationVerificationRejected,
        )

        with self.assertRaises(ControlledMutationVerificationRejected):
            ControlledMutationVerificationBoundary("")

    def test_verification_id_validation(self) -> None:
        from core.runtime.controlled_mutation_verification_boundary import (
            ControlledMutationVerificationRejected,
        )

        with self.assertRaises(ControlledMutationVerificationRejected):
            self._boundary().record_verification_planned(
                "",
                "sandbox-1",
                "mutation-1",
            )

    def test_planned_record_success(self) -> None:
        record = self._boundary().record_verification_planned(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            verification_strategy={"type": "command", "command": "pytest"},
            evidence_refs={"plan": "evidence-1"},
            metadata={"source": "contract"},
            runtime_args={"mode": "dry"},
        )

        self.assertEqual(record.verification_phase, "planned")
        self.assertEqual(record.verification_strategy, {"type": "command", "command": "pytest"})
        self.assertEqual(record.evidence_refs, {"plan": "evidence-1"})
        self.assertEqual(record.metadata, {"source": "contract"})
        self.assertEqual(record.runtime_args, {"mode": "dry"})

    def test_started_record_success(self) -> None:
        record = self._boundary().record_verification_started(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            verification_summary={"status": "started"},
        )

        self.assertEqual(record.verification_phase, "started")
        self.assertEqual(record.verification_summary, {"status": "started"})

    def test_passed_record_success(self) -> None:
        record = self._boundary().record_verification_passed(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            {"ok": True, "tests": 12},
            evidence_refs={"verify": "evidence-2"},
        )

        self.assertEqual(record.verification_phase, "passed")
        self.assertEqual(record.verification_summary, {"ok": True, "tests": 12})
        self.assertEqual(record.evidence_refs, {"verify": "evidence-2"})

    def test_failed_record_success(self) -> None:
        record = self._boundary().record_verification_failed(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            {"ok": False, "error": "assertion failed"},
        )

        self.assertEqual(record.verification_phase, "failed")
        self.assertEqual(record.verification_summary, {"ok": False, "error": "assertion failed"})

    def test_blocked_record_success(self) -> None:
        record = self._boundary().record_verification_blocked(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            {"reason": "policy"},
            metadata={"blocked": True},
        )

        self.assertEqual(record.verification_phase, "blocked")
        self.assertEqual(record.verification_summary, {"reason": "policy"})
        self.assertEqual(record.metadata, {"blocked": True})

    def test_deterministic_record_id_sequence(self) -> None:
        boundary = self._boundary()
        boundary.record_verification_planned("verification-1", "sandbox-1", "mutation-1")
        boundary.record_verification_started("verification-1", "sandbox-1", "mutation-1")
        boundary.record_verification_passed(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            {"ok": True},
        )
        boundary.record_verification_failed(
            "verification-2",
            "sandbox-1",
            "mutation-1",
            {"ok": False},
        )
        boundary.record_verification_blocked(
            "verification-3",
            "sandbox-1",
            "mutation-2",
            {"reason": "policy"},
        )

        self.assertEqual(
            [record.record_id for record in boundary.list_records()],
            [
                "verification-boundary:verification-1:sandbox-1:mutation-1:planned:1",
                "verification-boundary:verification-1:sandbox-1:mutation-1:started:2",
                "verification-boundary:verification-1:sandbox-1:mutation-1:passed:3",
                "verification-boundary:verification-2:sandbox-1:mutation-1:failed:4",
                "verification-boundary:verification-3:sandbox-1:mutation-2:blocked:5",
            ],
        )
        self.assertEqual(
            [record.sequence for record in boundary.list_records()],
            [1, 2, 3, 4, 5],
        )

    def test_deterministic_record_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_verification_boundary import (
            ControlledMutationVerificationRecord,
        )

        first = ControlledMutationVerificationRecord(
            "record-1",
            "boundary-1",
            "verification-1",
            "sandbox-1",
            "mutation-1",
            "planned",
            1,
            verification_strategy={"b": 2, "a": 1},
        )
        second = ControlledMutationVerificationRecord(
            "record-1",
            "boundary-1",
            "verification-1",
            "sandbox-1",
            "mutation-1",
            "planned",
            1,
            verification_strategy={"a": 1, "b": 2},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_deterministic_boundary_fingerprint(self) -> None:
        first = self._boundary()
        second = self._boundary()
        first.record_verification_planned(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            metadata={"b": 2, "a": 1},
        )
        first.record_verification_passed(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            {"ok": True},
        )
        second.record_verification_planned(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            metadata={"a": 1, "b": 2},
        )
        second.record_verification_passed(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            {"ok": True},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        from core.runtime.controlled_mutation_verification_boundary import (
            ControlledMutationVerificationRecord,
        )

        first = ControlledMutationVerificationRecord(
            "record-1",
            "boundary-1",
            "verification-1",
            "sandbox-1",
            "mutation-1",
            "planned",
            1,
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = ControlledMutationVerificationRecord(
            "record-1",
            "boundary-1",
            "verification-1",
            "sandbox-1",
            "mutation-1",
            "planned",
            1,
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_copy_on_read_immutable_behavior(self) -> None:
        record = self._boundary().record_verification_passed(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            {"items": [{"id": "summary"}]},
            verification_strategy={"items": [{"id": "strategy"}]},
            evidence_refs={"items": [{"id": "evidence"}]},
            metadata={"items": [{"id": "metadata"}]},
            runtime_args={"items": [{"id": "runtime"}]},
        )
        verification_strategy = record.verification_strategy
        verification_summary = record.verification_summary
        evidence_refs = record.evidence_refs
        metadata = record.metadata
        runtime_args = record.runtime_args

        verification_strategy["items"][0]["id"] = "polluted"
        verification_summary["items"][0]["id"] = "polluted"
        evidence_refs["items"][0]["id"] = "polluted"
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"

        self.assertEqual(record.verification_strategy, {"items": [{"id": "strategy"}]})
        self.assertEqual(record.verification_summary, {"items": [{"id": "summary"}]})
        self.assertEqual(record.evidence_refs, {"items": [{"id": "evidence"}]})
        self.assertEqual(record.metadata, {"items": [{"id": "metadata"}]})
        self.assertEqual(record.runtime_args, {"items": [{"id": "runtime"}]})

    def test_list_records_immutable_behavior(self) -> None:
        boundary = self._boundary()
        boundary.record_verification_planned(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            metadata={"source": "contract"},
        )
        records = boundary.list_records()
        records[0]._metadata = {"polluted": True}
        records.clear()

        current = boundary.list_records()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].metadata, {"source": "contract"})

    def test_input_mutation_isolation(self) -> None:
        verification_strategy = {"items": [{"id": "strategy"}]}
        verification_summary = {"items": [{"id": "summary"}]}
        evidence_refs = {"items": [{"id": "evidence"}]}
        metadata = {"items": [{"id": "metadata"}]}
        runtime_args = {"items": [{"id": "runtime"}]}
        before = copy.deepcopy(
            (
                verification_strategy,
                verification_summary,
                evidence_refs,
                metadata,
                runtime_args,
            )
        )

        record = self._boundary().record_verification_passed(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            verification_summary,
            verification_strategy=verification_strategy,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        verification_strategy["items"][0]["id"] = "polluted"
        verification_summary["items"][0]["id"] = "polluted"
        evidence_refs["items"][0]["id"] = "polluted"
        metadata["items"][0]["id"] = "polluted"
        runtime_args["items"][0]["id"] = "polluted"

        self.assertEqual(
            (
                record.verification_strategy,
                record.verification_summary,
                record.evidence_refs,
                record.metadata,
                record.runtime_args,
            ),
            before,
        )

    def test_boundary_is_record_only_and_does_not_attach_runtime_executors(self) -> None:
        boundary = self._boundary()

        boundary.record_verification_started(
            "verification-1",
            "sandbox-1",
            "mutation-1",
            runtime_args={"command": "pytest"},
        )

        self.assertFalse(hasattr(boundary, "scheduler"))
        self.assertFalse(hasattr(boundary, "agent_loop"))
        self.assertFalse(hasattr(boundary, "step_executor"))
        self.assertFalse(hasattr(boundary, "persistence_backend"))


if __name__ == "__main__":
    unittest.main()
