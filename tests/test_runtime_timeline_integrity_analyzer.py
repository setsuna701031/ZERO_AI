from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeTimelineIntegrityAnalyzerTest(unittest.TestCase):
    def _evidence_entries(self):
        return [
            {
                "session_id": "root",
                "parent_session_id": "",
                "replay_id": "",
                "repair_chain_id": "",
                "execution_chain_depth": 0,
                "event_type": "session_continuity",
                "status": "finished",
                "missing_refs": {
                    "missing_parent_ref": False,
                    "missing_previous_runtime_state_ref": False,
                    "has_chain_break": False,
                },
                "chain_break_count": 0,
                "source_record_count": 6,
            },
            {
                "session_id": "orphan",
                "parent_session_id": "",
                "replay_id": "",
                "repair_chain_id": "repair-orphan",
                "execution_chain_depth": 2,
                "event_type": "session_continuity",
                "status": "running",
                "missing_refs": {
                    "missing_parent_ref": False,
                    "missing_previous_runtime_state_ref": True,
                    "has_chain_break": True,
                },
                "chain_break_count": 1,
                "source_record_count": 6,
            },
            {
                "session_id": "missing-parent",
                "parent_session_id": "ghost",
                "replay_id": "",
                "repair_chain_id": "repair-missing",
                "execution_chain_depth": 1,
                "event_type": "session_continuity",
                "status": "running",
                "missing_refs": {
                    "missing_parent_ref": True,
                    "missing_previous_runtime_state_ref": False,
                    "has_chain_break": True,
                },
                "chain_break_count": 1,
                "source_record_count": 6,
            },
            {
                "session_id": "cycle-a",
                "parent_session_id": "cycle-b",
                "replay_id": "replay-diverged",
                "repair_chain_id": "repair-cycle",
                "execution_chain_depth": 1,
                "event_type": "session_continuity",
                "status": "running",
                "missing_refs": {
                    "missing_parent_ref": False,
                    "missing_previous_runtime_state_ref": False,
                    "has_chain_break": False,
                },
                "chain_break_count": 0,
                "source_record_count": 6,
            },
            {
                "session_id": "cycle-b",
                "parent_session_id": "cycle-a",
                "replay_id": "replay-diverged",
                "repair_chain_id": "repair-cycle-2",
                "execution_chain_depth": 1,
                "event_type": "session_continuity",
                "status": "running",
                "missing_refs": {
                    "missing_parent_ref": False,
                    "missing_previous_runtime_state_ref": False,
                    "has_chain_break": False,
                },
                "chain_break_count": 0,
                "source_record_count": 6,
            },
            {
                "session_id": "bad-depth",
                "parent_session_id": "root",
                "replay_id": "",
                "repair_chain_id": "repair-depth",
                "execution_chain_depth": 3,
                "event_type": "session_continuity",
                "status": "running",
                "missing_refs": {
                    "missing_parent_ref": False,
                    "missing_previous_runtime_state_ref": False,
                    "has_chain_break": False,
                },
                "chain_break_count": 0,
                "source_record_count": 6,
            },
        ]

    def test_detects_orphan_sessions(self) -> None:
        from core.runtime.runtime_timeline_integrity_analyzer import detect_orphan_sessions

        orphans = detect_orphan_sessions(self._evidence_entries())

        self.assertEqual(
            orphans,
            [
                {
                    "session_id": "orphan",
                    "execution_chain_depth": 2,
                    "repair_chain_id": "repair-orphan",
                    "reason": "non_root_session_missing_parent",
                }
            ],
        )

    def test_detects_impossible_parent_refs(self) -> None:
        from core.runtime.runtime_timeline_integrity_analyzer import (
            detect_impossible_parent_session_refs,
        )

        broken = detect_impossible_parent_session_refs(self._evidence_entries())

        self.assertEqual(
            broken,
            [
                {
                    "session_id": "missing-parent",
                    "parent_session_id": "ghost",
                    "repair_chain_id": "repair-missing",
                    "reason": "parent_session_id_not_found",
                }
            ],
        )

    def test_detects_circular_parent_linkage(self) -> None:
        from core.runtime.runtime_timeline_integrity_analyzer import (
            detect_circular_parent_linkage,
        )

        cycles = detect_circular_parent_linkage(self._evidence_entries())

        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0]["session_ids"], ["cycle-a", "cycle-b"])
        self.assertEqual(cycles[0]["reason"], "circular_parent_linkage")

    def test_detects_replay_divergence_and_hints(self) -> None:
        from core.runtime.runtime_timeline_integrity_analyzer import (
            detect_replay_divergence_chains,
            generate_replay_divergence_hints,
        )

        divergence = detect_replay_divergence_chains(self._evidence_entries())
        hints = generate_replay_divergence_hints(divergence)

        self.assertEqual(len(divergence), 1)
        self.assertEqual(divergence[0]["replay_id"], "replay-diverged")
        self.assertIn("multiple_repair_chains_in_replay", divergence[0]["reasons"])
        self.assertEqual(hints[0]["affected_sessions"], ["cycle-a", "cycle-b"])

    def test_detects_depth_anomalies(self) -> None:
        from core.runtime.runtime_timeline_integrity_analyzer import (
            detect_execution_chain_depth_anomalies,
        )

        anomalies = detect_execution_chain_depth_anomalies(self._evidence_entries())

        self.assertEqual(
            [item["session_id"] for item in anomalies],
            ["bad-depth", "cycle-a", "cycle-b", "orphan"],
        )
        self.assertEqual(anomalies[0]["reason"], "child_depth_must_follow_parent_depth")

    def test_generates_stable_integrity_report_without_side_effects(self) -> None:
        from core.runtime.runtime_timeline_integrity_analyzer import (
            analyze_runtime_timeline_evidence,
        )

        evidence = self._evidence_entries()
        before = copy.deepcopy(evidence)

        report = analyze_runtime_timeline_evidence(evidence)

        self.assertEqual(evidence, before)
        self.assertEqual(report["orphan_session_count"], 1)
        self.assertEqual(len(report["broken_parent_refs"]), 1)
        self.assertEqual(len(report["circular_chain_refs"]), 1)
        self.assertEqual(report["replay_divergence_count"], 1)
        self.assertEqual(report["depth_anomaly_count"], 4)
        self.assertEqual(report["chain_break_count"], 7)
        self.assertIn("repair-cycle", report["affected_repair_chain_ids"])
        self.assertIn("integrity_score", report)

    def test_builds_report_from_runtime_records(self) -> None:
        from core.runtime.runtime_timeline_integrity_analyzer import (
            build_runtime_timeline_integrity_report,
        )

        records = [
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
                    "repair_chain_id": "repair-1",
                    "execution_chain_depth": 1,
                },
            },
        ]

        report = build_runtime_timeline_integrity_report(records)

        self.assertEqual(report["source_record_count"], 2)
        self.assertEqual(report["timeline_entry_count"], 2)
        self.assertEqual(report["chain_break_count"], 1)
        self.assertEqual(report["affected_repair_chain_ids"], [])


if __name__ == "__main__":
    unittest.main()
