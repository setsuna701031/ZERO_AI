from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeReplayDiffComparatorTest(unittest.TestCase):
    def _baseline_report(self):
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
                    "status": "finished",
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

    def _candidate_report(self):
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
                    "status": "running",
                    "engineering_continuity": {
                        "session_id": "child",
                        "parent_session_id": "root",
                        "replay_id": "replay-1",
                        "repair_chain_id": "repair-1",
                        "execution_chain_depth": 1,
                        "previous_runtime_state_ref": "state-child",
                    },
                },
                {
                    "status": "running",
                    "engineering_continuity": {
                        "session_id": "orphan",
                        "replay_id": "replay-1",
                        "repair_chain_id": "repair-2",
                        "execution_chain_depth": 2,
                    },
                },
            ]
        )

    def test_compares_replay_reconstruction_reports(self) -> None:
        from core.runtime.runtime_replay_diff_comparator import (
            compare_replay_reconstruction_reports,
        )

        comparison = compare_replay_reconstruction_reports(
            self._baseline_report(),
            self._candidate_report(),
        )

        self.assertEqual(comparison["schema_version"], "runtime_replay_diff_comparator.v1")
        self.assertTrue(comparison["comparison_id"].startswith("replay-diff-"))
        self.assertEqual(comparison["divergence_count"], 1)
        self.assertEqual(comparison["replay_drift_count"], 2)
        self.assertEqual(
            [item["session_id"] for item in comparison["new_orphan_sessions"]],
            ["orphan"],
        )
        self.assertTrue(comparison["new_chain_breaks"])
        self.assertEqual(comparison["severity_hint"]["level"], "high")

    def test_detects_replay_divergence_regions(self) -> None:
        from core.runtime.runtime_replay_diff_comparator import (
            detect_replay_divergence_regions,
        )

        regions = detect_replay_divergence_regions(
            self._baseline_report(),
            self._candidate_report(),
        )

        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["replay_id"], "replay-1")
        self.assertEqual(regions[0]["repair_chain_ids"], ["repair-1", "repair-2"])

    def test_compares_chain_break_and_integrity_deltas(self) -> None:
        from core.runtime.runtime_replay_diff_comparator import (
            compare_chain_break_deltas,
            compare_integrity_summaries,
        )

        baseline = self._baseline_report()
        candidate = self._candidate_report()

        chain_breaks = compare_chain_break_deltas(baseline, candidate)
        integrity = compare_integrity_summaries(baseline, candidate)

        self.assertGreater(chain_breaks["delta"], 0)
        self.assertTrue(chain_breaks["new_chain_breaks"])
        self.assertEqual(integrity["orphan_session_count"]["delta"], 1)
        self.assertGreater(integrity["chain_break_count"]["delta"], 0)

    def test_detects_new_orphans_and_replay_drift(self) -> None:
        from core.runtime.runtime_replay_diff_comparator import (
            detect_newly_introduced_orphan_sessions,
            detect_replay_drift,
        )

        baseline = self._baseline_report()
        candidate = self._candidate_report()

        orphans = detect_newly_introduced_orphan_sessions(baseline, candidate)
        drift = detect_replay_drift(baseline, candidate)

        self.assertEqual(orphans[0]["session_id"], "orphan")
        self.assertEqual(
            [item["reason"] for item in drift],
            ["changed_timeline_entry", "added_timeline_entry"],
        )

    def test_generates_stable_diff_summary_and_grouping(self) -> None:
        from core.runtime.runtime_replay_diff_comparator import (
            compare_replay_reconstruction_reports,
            generate_stable_diff_summary,
            group_replay_diffs_by_repair_chain_id,
        )

        comparison = compare_replay_reconstruction_reports(
            self._baseline_report(),
            self._candidate_report(),
        )

        first = generate_stable_diff_summary(comparison)
        second = generate_stable_diff_summary(comparison)
        groups = group_replay_diffs_by_repair_chain_id([comparison])

        self.assertEqual(first, second)
        self.assertEqual(first["comparison_id"], comparison["comparison_id"])
        self.assertEqual(
            [group["repair_chain_id"] for group in groups],
            ["repair-1", "repair-2"],
        )

    def test_comparison_does_not_mutate_inputs(self) -> None:
        from core.runtime.runtime_replay_diff_comparator import (
            compare_replay_reconstruction_reports,
        )

        baseline = self._baseline_report()
        candidate = self._candidate_report()
        before_baseline = copy.deepcopy(baseline)
        before_candidate = copy.deepcopy(candidate)

        compare_replay_reconstruction_reports(baseline, candidate)

        self.assertEqual(baseline, before_baseline)
        self.assertEqual(candidate, before_candidate)


if __name__ == "__main__":
    unittest.main()
