from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeReplayReconstructionReportTest(unittest.TestCase):
    def _records(self):
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
                "status": "running",
                "engineering_continuity": {
                    "session_id": "child",
                    "parent_session_id": "root",
                    "replay_id": "replay-1",
                    "repair_chain_id": "repair-1",
                    "execution_chain_depth": 1,
                },
            },
        ]

    def _divergent_records(self):
        return [
            {
                "status": "running",
                "engineering_continuity": {
                    "session_id": "a",
                    "replay_id": "replay-diverged",
                    "repair_chain_id": "repair-a",
                    "execution_chain_depth": 0,
                },
            },
            {
                "status": "running",
                "engineering_continuity": {
                    "session_id": "b",
                    "replay_id": "replay-diverged",
                    "repair_chain_id": "repair-b",
                    "execution_chain_depth": 0,
                },
            },
        ]

    def test_builds_unified_replay_reconstruction_report(self) -> None:
        from core.runtime.runtime_replay_reconstruction_report import (
            build_runtime_replay_reconstruction_report,
        )

        report = build_runtime_replay_reconstruction_report(self._records())

        self.assertEqual(report["schema_version"], "runtime_replay_reconstruction_report.v1")
        self.assertTrue(report["report_id"].startswith("replay-reconstruction-"))
        self.assertEqual(report["session_count"], 2)
        self.assertEqual(report["replay_count"], 1)
        self.assertEqual(report["repair_chain_count"], 1)
        self.assertEqual(report["chain_break_count"], 1)
        self.assertEqual(len(report["timeline_entries"]), 2)
        self.assertEqual(report["evidence_bundle"]["schema_version"], "runtime_timeline_evidence.v1")
        self.assertIn("integrity_summary", report)
        self.assertIn("analyzer_results", report)

    def test_report_id_is_stable_and_inputs_are_not_mutated(self) -> None:
        from core.runtime.runtime_replay_reconstruction_report import (
            build_runtime_replay_reconstruction_report,
        )

        records = self._records()
        before = copy.deepcopy(records)

        first = build_runtime_replay_reconstruction_report(records)
        second = build_runtime_replay_reconstruction_report(records)

        self.assertEqual(records, before)
        self.assertEqual(first["report_id"], second["report_id"])

    def test_embeds_replay_divergence_hints(self) -> None:
        from core.runtime.runtime_replay_reconstruction_report import (
            build_runtime_replay_reconstruction_report,
        )

        report = build_runtime_replay_reconstruction_report(self._divergent_records())

        self.assertEqual(report["replay_divergence_count"], 1)
        self.assertEqual(report["replay_divergence_hints"][0]["replay_id"], "replay-diverged")
        self.assertEqual(
            report["affected_repair_chain_ids"],
            ["repair-a", "repair-b"],
        )

    def test_groups_reports_by_repair_chain_id(self) -> None:
        from core.runtime.runtime_replay_reconstruction_report import (
            build_runtime_replay_reconstruction_report,
            group_replay_reconstruction_reports_by_repair_chain_id,
        )

        report = build_runtime_replay_reconstruction_report(self._divergent_records())

        groups = group_replay_reconstruction_reports_by_repair_chain_id([report])

        self.assertEqual(
            [group["repair_chain_id"] for group in groups],
            ["repair-a", "repair-b"],
        )
        self.assertEqual(groups[0]["report_ids"], [report["report_id"]])

    def test_generates_stable_forensic_snapshot(self) -> None:
        from core.runtime.runtime_replay_reconstruction_report import (
            build_runtime_replay_reconstruction_report,
            generate_replay_reconstruction_forensic_snapshot,
        )

        report = build_runtime_replay_reconstruction_report(self._records())

        first = generate_replay_reconstruction_forensic_snapshot(report)
        second = generate_replay_reconstruction_forensic_snapshot(report)

        self.assertEqual(first, second)
        self.assertEqual(
            first["schema_version"],
            "runtime_replay_reconstruction_forensic_snapshot.v1",
        )
        self.assertEqual(first["report_id"], report["report_id"])
        self.assertTrue(first["snapshot_hash"])

    def test_produces_lightweight_summary_views(self) -> None:
        from core.runtime.runtime_replay_reconstruction_report import (
            build_runtime_replay_reconstruction_report,
            summarize_replay_reconstruction_report,
            summarize_replay_reconstruction_reports,
        )

        report = build_runtime_replay_reconstruction_report(self._divergent_records())

        single = summarize_replay_reconstruction_report(report)
        aggregate = summarize_replay_reconstruction_reports([report])

        self.assertEqual(single["report_id"], report["report_id"])
        self.assertEqual(single["replay_divergence_count"], 1)
        self.assertEqual(aggregate["report_count"], 1)
        self.assertEqual(aggregate["affected_repair_chain_ids"], ["repair-a", "repair-b"])


if __name__ == "__main__":
    unittest.main()
