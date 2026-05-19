from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeForensicStackContractTest(unittest.TestCase):
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

    def test_required_field_helpers_are_stable_lists(self) -> None:
        from core.runtime.runtime_forensic_stack_contract import (
            forensic_comparison_required_fields,
            forensic_report_required_fields,
            forensic_snapshot_required_fields,
            forensic_summary_required_fields,
            seal_metadata_required_fields,
        )

        self.assertIn("timeline_entries", forensic_report_required_fields())
        self.assertIn("forensic_snapshot", forensic_snapshot_required_fields())
        self.assertIn("seal_comparison", forensic_comparison_required_fields())
        self.assertIn("snapshot_seal_id", forensic_summary_required_fields())
        self.assertIn("hashes", seal_metadata_required_fields())

    def test_validates_runtime_forensic_report_snapshot_comparison_and_summary(self) -> None:
        from core.runtime.runtime_forensic_stack import (
            build_runtime_forensic_report,
            build_runtime_forensic_snapshot,
            compare_runtime_forensic_snapshots,
            summarize_runtime_forensic_stack,
        )
        from core.runtime.runtime_forensic_stack_contract import (
            validate_runtime_forensic_stack_contracts,
        )

        report = build_runtime_forensic_report(self._records())
        snapshot = build_runtime_forensic_snapshot(self._records())
        candidate = build_runtime_forensic_snapshot(self._records(status="running"))
        comparison = compare_runtime_forensic_snapshots(snapshot, candidate)
        summary = summarize_runtime_forensic_stack(report)
        seal_metadata = snapshot["seal_metadata"]

        result = validate_runtime_forensic_stack_contracts(
            report=report,
            snapshot=snapshot,
            comparison=comparison,
            summary=summary,
            seal_metadata=seal_metadata,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["validations"]["report"]["ok"])
        self.assertTrue(result["validations"]["snapshot"]["ok"])
        self.assertTrue(result["validations"]["comparison"]["ok"])
        self.assertTrue(result["validations"]["summary"]["ok"])
        self.assertTrue(result["validations"]["seal_metadata"]["ok"])

    def test_validation_reports_missing_fields_without_exceptions(self) -> None:
        from core.runtime.runtime_forensic_stack_contract import (
            validate_forensic_report_contract,
        )

        result = validate_forensic_report_contract({"stack_version": "runtime_forensic_stack.v1"})

        self.assertFalse(result["ok"])
        self.assertIn("report_id", result["missing_fields"])
        self.assertEqual(result["unexpected_type"], "")

    def test_validation_reports_unexpected_type_without_exceptions(self) -> None:
        from core.runtime.runtime_forensic_stack_contract import (
            validate_forensic_snapshot_contract,
        )

        result = validate_forensic_snapshot_contract(["not", "a", "dict"])

        self.assertFalse(result["ok"])
        self.assertEqual(result["unexpected_type"], "list")
        self.assertIn("report_id", result["missing_fields"])

    def test_aggregate_validator_skips_omitted_shapes(self) -> None:
        from core.runtime.runtime_forensic_stack import build_runtime_forensic_report
        from core.runtime.runtime_forensic_stack_contract import (
            validate_runtime_forensic_stack_contracts,
        )

        report = build_runtime_forensic_report(self._records())

        result = validate_runtime_forensic_stack_contracts(report=report)

        self.assertTrue(result["ok"])
        self.assertTrue(result["validations"]["snapshot"]["skipped"])
        self.assertTrue(result["validations"]["report"]["ok"])


if __name__ == "__main__":
    unittest.main()
