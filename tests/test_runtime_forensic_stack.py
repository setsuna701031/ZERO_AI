from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeForensicStackTest(unittest.TestCase):
    def _records(self, *, status: str = "finished"):
        return [
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

    def test_builds_runtime_forensic_report(self) -> None:
        from core.runtime.runtime_forensic_stack import build_runtime_forensic_report

        report = build_runtime_forensic_report(self._records())

        self.assertEqual(report["stack_version"], "runtime_forensic_stack.v1")
        self.assertEqual(report["report_id"], report["reconstruction_report"]["report_id"])
        self.assertEqual(len(report["timeline_entries"]), 2)
        self.assertEqual(report["evidence_bundle"]["schema_version"], "runtime_timeline_evidence.v1")
        self.assertEqual(report["snapshot_seal"]["report_id"], report["report_id"])
        self.assertEqual(report["summary"]["repair_chain_ids"], ["repair-1"])

    def test_builds_runtime_forensic_snapshot_deterministically(self) -> None:
        from core.runtime.runtime_forensic_stack import build_runtime_forensic_snapshot

        first = build_runtime_forensic_snapshot(self._records())
        second = build_runtime_forensic_snapshot(self._records())

        self.assertEqual(first, second)
        self.assertEqual(first["stack_version"], "runtime_forensic_stack.v1")
        self.assertEqual(first["forensic_snapshot"]["report_id"], first["report_id"])
        self.assertEqual(first["seal_metadata"]["snapshot_seal_id"], first["snapshot_seal"]["snapshot_seal_id"])
        self.assertIn("reconstruction_report", first)

    def test_compares_runtime_forensic_snapshots(self) -> None:
        from core.runtime.runtime_forensic_stack import (
            build_runtime_forensic_snapshot,
            compare_runtime_forensic_snapshots,
        )

        baseline = build_runtime_forensic_snapshot(self._records(status="finished"))
        candidate = build_runtime_forensic_snapshot(self._records(status="running"))

        comparison = compare_runtime_forensic_snapshots(baseline, candidate)

        self.assertEqual(comparison["stack_version"], "runtime_forensic_stack.v1")
        self.assertTrue(comparison["seal_mismatch"])
        self.assertEqual(comparison["diff_summary"]["replay_drift_count"], 1)
        self.assertEqual(comparison["seal_by_repair_chain_id"][0]["repair_chain_id"], "repair-1")

    def test_summarizes_runtime_forensic_stack(self) -> None:
        from core.runtime.runtime_forensic_stack import (
            build_runtime_forensic_report,
            summarize_runtime_forensic_stack,
        )

        report = build_runtime_forensic_report(self._records())

        summary = summarize_runtime_forensic_stack(report)

        self.assertEqual(summary["report_id"], report["report_id"])
        self.assertEqual(summary["session_count"], 2)
        self.assertEqual(summary["replay_count"], 1)
        self.assertEqual(summary["repair_chain_count"], 1)
        self.assertEqual(summary["source_record_count"], 2)

    def test_facade_does_not_mutate_inputs(self) -> None:
        from core.runtime.runtime_forensic_stack import (
            build_runtime_forensic_report,
            build_runtime_forensic_snapshot,
        )

        records = self._records()
        before = copy.deepcopy(records)

        build_runtime_forensic_report(records)
        build_runtime_forensic_snapshot(records)

        self.assertEqual(records, before)


if __name__ == "__main__":
    unittest.main()
