from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeReplaySnapshotSealTest(unittest.TestCase):
    def _report(self, *, status: str = "finished"):
        from core.runtime.runtime_replay_reconstruction_report import (
            build_runtime_replay_reconstruction_report,
        )

        return build_runtime_replay_reconstruction_report(
            [
                {
                    "status": "finished",
                    "engineering_continuity": {
                        "session_id": "root",
                        "execution_chain_depth": 0,
                        "previous_runtime_state_ref": "state-root",
                    },
                },
                {
                    "status": status,
                    "engineering_continuity": {
                        "session_id": "child",
                        "parent_session_id": "root",
                        "replay_id": "replay-1",
                        "repair_chain_id": "repair-1",
                        "execution_chain_depth": 1,
                        "previous_runtime_state_ref": "state-child",
                    },
                },
            ]
        )

    def _diff(self):
        from core.runtime.runtime_replay_diff_comparator import (
            compare_replay_reconstruction_reports,
        )

        return compare_replay_reconstruction_reports(
            self._report(status="finished"),
            self._report(status="running"),
        )

    def test_seals_reconstruction_report_deterministically(self) -> None:
        from core.runtime.runtime_replay_snapshot_seal import (
            seal_replay_reconstruction_report,
        )

        report = self._report()

        first = seal_replay_reconstruction_report(report)
        second = seal_replay_reconstruction_report(report)

        self.assertEqual(first, second)
        self.assertTrue(first["snapshot_seal_id"].startswith("replay-snapshot-seal-"))
        self.assertEqual(first["report_id"], report["report_id"])
        self.assertEqual(first["repair_chain_ids"], ["repair-1"])
        self.assertEqual(first["seal_version"], "runtime_replay_snapshot_seal.v1")

    def test_generates_stable_replay_snapshot_hash(self) -> None:
        from core.runtime.runtime_replay_snapshot_seal import generate_replay_snapshot_hash

        left = {"b": [2, 1], "a": "value"}
        right = {"a": "value", "b": [2, 1]}

        self.assertEqual(
            generate_replay_snapshot_hash(left),
            generate_replay_snapshot_hash(right),
        )

    def test_seals_replay_diff_summary(self) -> None:
        from core.runtime.runtime_replay_snapshot_seal import seal_replay_diff_summary

        diff = self._diff()

        seal = seal_replay_diff_summary(diff)

        self.assertEqual(seal["report_id"], diff["comparison_id"])
        self.assertEqual(seal["repair_chain_ids"], ["repair-1"])
        self.assertTrue(seal["divergence_hash"])

    def test_compares_and_detects_seal_mismatches(self) -> None:
        from core.runtime.runtime_replay_snapshot_seal import (
            compare_replay_snapshot_seals,
            detect_replay_snapshot_seal_mismatches,
            seal_replay_reconstruction_report,
        )

        baseline = seal_replay_reconstruction_report(self._report(status="finished"))
        candidate = seal_replay_reconstruction_report(self._report(status="running"))

        mismatches = detect_replay_snapshot_seal_mismatches(baseline, candidate)
        comparison = compare_replay_snapshot_seals(baseline, candidate)

        self.assertTrue(mismatches)
        self.assertTrue(comparison["seal_mismatch"])
        self.assertIn("replay_hash", [item["field"] for item in mismatches])

    def test_generates_lightweight_metadata_and_groups_by_repair_chain(self) -> None:
        from core.runtime.runtime_replay_snapshot_seal import (
            generate_replay_snapshot_seal_metadata,
            group_replay_snapshot_seals_by_repair_chain_id,
            seal_replay_reconstruction_report,
        )

        seal = seal_replay_reconstruction_report(self._report())

        metadata = generate_replay_snapshot_seal_metadata(seal)
        groups = group_replay_snapshot_seals_by_repair_chain_id([seal])

        self.assertEqual(metadata["snapshot_seal_id"], seal["snapshot_seal_id"])
        self.assertEqual(metadata["repair_chain_ids"], ["repair-1"])
        self.assertEqual(groups[0]["repair_chain_id"], "repair-1")
        self.assertEqual(groups[0]["snapshot_seal_ids"], [seal["snapshot_seal_id"]])

    def test_generates_forensic_snapshot_seal(self) -> None:
        from core.runtime.runtime_replay_snapshot_seal import (
            generate_replay_forensic_snapshot_seal,
        )

        seal = generate_replay_forensic_snapshot_seal(self._report())

        self.assertEqual(seal["repair_chain_ids"], ["repair-1"])
        self.assertTrue(seal["replay_hash"])
        self.assertTrue(seal["integrity_hash"])

    def test_sealing_does_not_mutate_inputs(self) -> None:
        from core.runtime.runtime_replay_snapshot_seal import (
            seal_replay_diff_summary,
            seal_replay_reconstruction_report,
        )

        report = self._report()
        diff = self._diff()
        report_before = copy.deepcopy(report)
        diff_before = copy.deepcopy(diff)

        seal_replay_reconstruction_report(report)
        seal_replay_diff_summary(diff)

        self.assertEqual(report, report_before)
        self.assertEqual(diff, diff_before)


if __name__ == "__main__":
    unittest.main()
