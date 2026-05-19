from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeTimelineEvidenceExportTest(unittest.TestCase):
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

    def test_builds_stable_evidence_bundle_from_runtime_records(self) -> None:
        from core.runtime.runtime_timeline_evidence_export import (
            build_runtime_timeline_evidence_bundle,
        )

        bundle = build_runtime_timeline_evidence_bundle(self._records())

        self.assertEqual(bundle["schema_version"], "runtime_timeline_evidence.v1")
        self.assertEqual(bundle["source_record_count"], 2)
        self.assertEqual(bundle["timeline_entry_count"], 2)
        self.assertNotIn("generated_at", bundle)
        self.assertEqual(
            set(bundle["timeline"][0]),
            {
                "session_id",
                "parent_session_id",
                "replay_id",
                "repair_chain_id",
                "execution_chain_depth",
                "event_type",
                "status",
                "missing_refs",
                "chain_break_count",
                "source_record_count",
            },
        )

    def test_marks_broken_chain_without_mutating_records(self) -> None:
        from core.runtime.runtime_timeline_evidence_export import (
            build_runtime_timeline_evidence_bundle,
        )

        records = self._records()
        before = copy.deepcopy(records)

        bundle = build_runtime_timeline_evidence_bundle(records)

        child = bundle["timeline"][1]
        self.assertEqual(records, before)
        self.assertTrue(child["missing_refs"]["missing_previous_runtime_state_ref"])
        self.assertEqual(child["chain_break_count"], 1)
        self.assertEqual(bundle["chain_break_count"], 1)

    def test_groups_exported_evidence_by_repair_chain_id(self) -> None:
        from core.runtime.runtime_timeline_evidence_export import (
            build_runtime_timeline_evidence_bundle,
            group_timeline_evidence_by_repair_chain_id,
        )

        bundle = build_runtime_timeline_evidence_bundle(self._records())

        groups = group_timeline_evidence_by_repair_chain_id(bundle)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["repair_chain_id"], "repair-1")
        self.assertEqual(groups[0]["session_ids"], ["child"])
        self.assertEqual(groups[0]["replay_ids"], ["replay-1"])
        self.assertEqual(groups[0]["chain_break_count"], 1)

    def test_detects_broken_timeline_chains_from_exported_evidence(self) -> None:
        from core.runtime.runtime_timeline_evidence_export import (
            build_runtime_timeline_evidence_bundle,
            detect_broken_timeline_chains,
        )

        bundle = build_runtime_timeline_evidence_bundle(self._records())

        broken = detect_broken_timeline_chains(bundle)

        self.assertEqual(broken["chain_break_count"], 1)
        self.assertEqual(broken["missing_parent_refs"], [])
        self.assertEqual(
            broken["missing_previous_runtime_refs"],
            [
                {
                    "session_id": "child",
                    "execution_chain_depth": 1,
                    "event_type": "session_continuity",
                }
            ],
        )

    def test_returns_summary_counts_without_side_effects(self) -> None:
        from core.runtime.runtime_timeline_evidence_export import (
            build_runtime_timeline_evidence_bundle,
            summarize_timeline_evidence_counts,
        )

        bundle = build_runtime_timeline_evidence_bundle(self._records())
        before = copy.deepcopy(bundle)

        counts = summarize_timeline_evidence_counts(bundle)

        self.assertEqual(bundle, before)
        self.assertEqual(
            counts,
            {
                "timeline_entry_count": 2,
                "source_record_count": 2,
                "session_count": 2,
                "replay_count": 1,
                "repair_chain_count": 1,
                "chain_break_count": 1,
                "missing_parent_ref_count": 0,
                "missing_previous_runtime_ref_count": 1,
            },
        )

    def test_can_include_generated_at_when_requested(self) -> None:
        from core.runtime.runtime_timeline_evidence_export import (
            build_runtime_timeline_evidence_bundle,
        )

        bundle = build_runtime_timeline_evidence_bundle(
            self._records(),
            include_generated_at=True,
        )

        self.assertTrue(bundle["generated_at"])


if __name__ == "__main__":
    unittest.main()
