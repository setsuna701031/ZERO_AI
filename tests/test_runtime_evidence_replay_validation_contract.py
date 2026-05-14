from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceReplayValidationContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "replay-validation"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _validator(self):
        from core.runtime.runtime_evidence_replay_validation import RuntimeEvidenceReplayValidator

        return RuntimeEvidenceReplayValidator()

    def _state_from_payload(self, payload):
        from core.runtime.runtime_evidence_replay_reconstruction import RuntimeEvidenceReplayState

        return RuntimeEvidenceReplayState(payload)

    def test_replay_integrity_validation(self) -> None:
        validator = self._validator()
        report = validator.validate(self._seal("integrity-validation"))

        self.assertTrue(report.ok)
        self.assertEqual(report.payload["issue_count"], 0)
        self.assertTrue(report.checks()["replay_integrity"]["ok"])
        self.assertTrue(report.checks()["sealed_replay"]["ok"])

    def test_ordering_validation_correctness(self) -> None:
        validator = self._validator()
        state = validator.reconstructor.reconstruct(self._seal("ordering-validation"))
        payload = state.payload
        payload["execution_replay"][1]["replay_order"] = 9
        bad_state = self._state_from_payload(payload)

        check = validator.validate_replay_integrity(bad_state)

        self.assertFalse(check["ok"])
        self.assertIn(
            "execution_replay_order_invalid",
            [issue["type"] for issue in check["issues"]],
        )

    def test_event_ordering_validation_correctness(self) -> None:
        validator = self._validator()
        summary = validator.reconstructor.snapshot_builder.registry.query.summary_from(
            self._seal("event-order-validation")
        )
        summary["events"]["step_executor"] = {
            "count": 2,
            "phases": ["before_step", "after_step"],
            "statuses": ["pending", "succeeded"],
            "fingerprints": ["fp-before", "fp-after"],
        }
        state = validator.reconstructor.reconstruct(summary)
        payload = state.payload
        payload["event_replay_order"][1]["replay_order"] = 9

        check = validator.validate_event_ordering(self._state_from_payload(payload))

        self.assertFalse(check["ok"])
        self.assertIn(
            "event_replay_order_invalid",
            [issue["type"] for issue in check["issues"]],
        )

    def test_lineage_validation_behavior(self) -> None:
        validator = self._validator()
        state = validator.reconstructor.reconstruct(self._seal("lineage-validation"))
        payload = state.payload
        payload["lineage_replay"][2]["lineage_type"] = "audit"

        check = validator.validate_lineage_consistency(self._state_from_payload(payload))

        self.assertFalse(check["ok"])
        self.assertIn(
            "lineage_type_order_invalid",
            [issue["type"] for issue in check["issues"]],
        )

    def test_rollback_linkage_validation(self) -> None:
        validator = self._validator()
        state = validator.reconstructor.reconstruct(self._seal("rollback-validation"))
        payload = state.payload
        payload["rollback_replay"]["rollback_steps"] = list(reversed(payload["rollback_replay"]["rollback_steps"]))

        check = validator.validate_rollback_linkage(self._state_from_payload(payload))

        self.assertFalse(check["ok"])
        self.assertIn(
            "rollback_order_mismatch",
            [issue["type"] for issue in check["issues"]],
        )

    def test_failed_replay_consistency_checks(self) -> None:
        validator = self._validator()
        summary = validator.reconstructor.snapshot_builder.registry.query.summary_from(
            self._seal("failed-validation")
        )
        summary["events"]["step_executor"] = {
            "count": 1,
            "phases": ["after_step"],
            "statuses": ["failed"],
            "fingerprints": ["fp-failed"],
        }
        state = validator.reconstructor.reconstruct(summary)
        good = validator.validate_failed_execution_consistency(state)
        payload = state.payload
        payload["failed_execution_replay"][0]["status"] = "succeeded"
        bad = validator.validate_failed_execution_consistency(self._state_from_payload(payload))

        self.assertTrue(good["ok"])
        self.assertFalse(bad["ok"])
        self.assertIn(
            "failed_status_invalid",
            [issue["type"] for issue in bad["issues"]],
        )

    def test_missing_evidence_safety(self) -> None:
        report = self._validator().validate(None)

        self.assertFalse(report.ok)
        self.assertIn("replay_unsealed", [issue["type"] for issue in report.issues()])
        self.assertIn("replay_incomplete", [issue["type"] for issue in report.issues()])
        self.assertFalse(report.checks()["sealed_replay"]["ok"])

    def test_validation_report_is_immutable_and_does_not_mutate_replay(self) -> None:
        validator = self._validator()
        state = validator.reconstructor.reconstruct(self._seal("immutable-validation"))
        before = copy.deepcopy(state.payload)
        report = validator.validate(state)
        report_payload = report.payload
        checks = report.checks()
        issues = report.issues()

        report_payload["ok"] = False
        checks["sealed_replay"]["ok"] = False
        issues.append({"type": "polluted"})

        self.assertEqual(state.payload, before)
        self.assertTrue(report.ok)
        self.assertTrue(report.checks()["sealed_replay"]["ok"])
        self.assertEqual(report.issues(), [])


if __name__ == "__main__":
    unittest.main()
