from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ExecutionLandingConsistencyTest(unittest.TestCase):
    def _landing(self, *, task_id: str = "task-1") -> dict:
        return {
            "task_id": task_id,
            "session_id": "session-1",
            "status": "finished",
            "execution_result": {"ok": True},
            "verification_result": {"ok": True},
            "rollback_result": {"ok": True, "needed": False},
            "audit_ref": "audit-1",
            "evidence_ref": "evidence-1",
        }

    def _contracts(self) -> dict:
        return {
            "self_edit": {
                **self._landing(task_id="self-edit-task"),
                "mutation_ref": "mutation-self-edit-1",
            },
            "repair": {
                **self._landing(task_id="repair-task"),
                "repair_chain_id": "repair-1",
            },
            "replay": {
                **self._landing(task_id="replay-task"),
                "replay_ref": "replay-1",
            },
            "mutation": {
                **self._landing(task_id="mutation-task"),
                "mutation_ref": "mutation-1",
            },
        }

    def test_required_and_optional_field_helpers_are_stable_lists(self) -> None:
        from core.runtime.execution_landing_consistency import (
            execution_landing_optional_fields,
            execution_landing_required_fields,
        )

        self.assertEqual(
            execution_landing_required_fields(),
            [
                "task_id",
                "session_id",
                "status",
                "execution_result",
                "verification_result",
                "rollback_result",
                "audit_ref",
                "evidence_ref",
            ],
        )
        self.assertEqual(
            execution_landing_optional_fields(),
            ["mutation_ref", "replay_ref", "repair_chain_id"],
        )

    def test_collects_execution_landing_contract_shapes(self) -> None:
        from core.runtime.execution_landing_consistency import (
            collect_execution_landing_contract_shapes,
        )

        shapes = collect_execution_landing_contract_shapes(self._contracts())

        self.assertEqual(
            list(shapes),
            ["mutation", "repair", "replay", "self_edit"],
        )
        self.assertEqual(shapes["repair"]["fields"]["status"], "str")
        self.assertEqual(shapes["repair"]["fields"]["verification_result"], "dict")
        self.assertIn("repair_chain_id", shapes["repair"]["field_names"])

    def test_validates_required_landing_fields_without_exceptions(self) -> None:
        from core.runtime.execution_landing_consistency import (
            validate_required_landing_fields,
        )

        valid = validate_required_landing_fields(self._landing())
        missing = validate_required_landing_fields({"task_id": "task-1"})
        invalid_type = validate_required_landing_fields("not a landing")

        self.assertTrue(valid["ok"])
        self.assertFalse(missing["ok"])
        self.assertEqual(
            missing["missing_fields"],
            [
                "session_id",
                "status",
                "execution_result",
                "verification_result",
                "rollback_result",
                "audit_ref",
                "evidence_ref",
            ],
        )
        self.assertEqual(invalid_type["unexpected_type"], "str")

    def test_report_marks_compatible_landing_shapes(self) -> None:
        from core.runtime.execution_landing_consistency import (
            build_execution_landing_consistency_report,
            validate_execution_landing_consistency,
        )

        report = build_execution_landing_consistency_report(self._contracts())
        validation = validate_execution_landing_consistency(self._contracts())

        self.assertTrue(report["report_id"].startswith("execution-landing-consistency-"))
        self.assertEqual(
            report["checked_contracts"],
            ["mutation", "repair", "replay", "self_edit"],
        )
        self.assertEqual(report["missing_fields"]["self_edit"], [])
        self.assertEqual(report["incompatible_fields"], [])
        self.assertTrue(report["status_compatible"])
        self.assertTrue(report["verification_compatible"])
        self.assertTrue(report["rollback_compatible"])
        self.assertTrue(report["audit_compatible"])
        self.assertTrue(report["evidence_compatible"])
        self.assertEqual(report["consistency_score"], 1.0)
        self.assertEqual(report["blocking_issues"], [])
        self.assertTrue(validation["ok"])

    def test_detects_missing_landing_fields(self) -> None:
        from core.runtime.execution_landing_consistency import (
            build_execution_landing_consistency_report,
        )

        contracts = self._contracts()
        del contracts["replay"]["verification_result"]
        del contracts["mutation"]["audit_ref"]

        report = build_execution_landing_consistency_report(contracts)

        self.assertEqual(report["missing_fields"]["replay"], ["verification_result"])
        self.assertEqual(report["missing_fields"]["mutation"], ["audit_ref"])
        self.assertFalse(report["verification_compatible"])
        self.assertLess(report["consistency_score"], 1.0)
        self.assertIn(
            {
                "kind": "missing_required_fields",
                "contract": "mutation",
                "fields": ["audit_ref"],
            },
            report["blocking_issues"],
        )

    def test_detects_incompatible_status_verification_rollback_audit_and_evidence_fields(self) -> None:
        from core.runtime.execution_landing_consistency import (
            build_execution_landing_consistency_report,
            collect_execution_landing_contract_shapes,
            detect_incompatible_rollback_audit_fields,
            detect_incompatible_status_fields,
            detect_incompatible_verification_fields,
        )

        contracts = self._contracts()
        contracts["repair"]["status"] = {"state": "finished"}
        contracts["replay"]["verification_result"] = "verified"
        contracts["mutation"]["rollback_result"] = "not-needed"
        contracts["mutation"]["audit_ref"] = {"audit_id": "audit-1"}
        contracts["self_edit"]["evidence_ref"] = {"bundle_id": "evidence-1"}

        shapes = collect_execution_landing_contract_shapes(contracts)
        report = build_execution_landing_consistency_report(contracts)

        self.assertEqual(detect_incompatible_status_fields(shapes)[0]["field"], "status")
        self.assertEqual(
            detect_incompatible_verification_fields(shapes)[0]["field"],
            "verification_result",
        )
        rollback_audit_fields = [
            item["field"]
            for item in detect_incompatible_rollback_audit_fields(shapes)
        ]
        self.assertEqual(rollback_audit_fields, ["rollback_result", "audit_ref"])
        incompatible_fields = [item["field"] for item in report["incompatible_fields"]]
        self.assertEqual(
            incompatible_fields,
            [
                "status",
                "verification_result",
                "rollback_result",
                "audit_ref",
                "evidence_ref",
            ],
        )
        self.assertFalse(report["status_compatible"])
        self.assertFalse(report["verification_compatible"])
        self.assertFalse(report["rollback_compatible"])
        self.assertFalse(report["audit_compatible"])
        self.assertFalse(report["evidence_compatible"])

    def test_accepts_explicit_field_shapes_and_ignores_missing_optional_refs(self) -> None:
        from core.runtime.execution_landing_consistency import (
            build_execution_landing_consistency_report,
            collect_execution_landing_contract_shapes,
        )

        fields = {
            "task_id": "str",
            "session_id": "str",
            "status": "str",
            "execution_result": "dict",
            "verification_result": "dict",
            "rollback_result": "dict",
            "audit_ref": "str",
            "evidence_ref": "str",
        }
        shapes = collect_execution_landing_contract_shapes(
            {
                "self_edit": {"fields": fields},
                "repair": {"fields": {**fields, "repair_chain_id": "str"}},
                "replay": {"fields": {**fields, "replay_ref": "str"}},
                "mutation": {"fields": {**fields, "mutation_ref": "str"}},
            }
        )
        report = build_execution_landing_consistency_report(shapes)

        self.assertEqual(report["missing_fields"]["self_edit"], [])
        self.assertEqual(report["incompatible_fields"], [])
        self.assertEqual(report["consistency_score"], 1.0)

    def test_consistency_report_is_stable_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.execution_landing_consistency import (
            build_execution_landing_consistency_report,
        )

        contracts = self._contracts()
        before = copy.deepcopy(contracts)

        first = build_execution_landing_consistency_report(contracts)
        second = build_execution_landing_consistency_report(contracts)

        self.assertEqual(first, second)
        self.assertEqual(contracts, before)


if __name__ == "__main__":
    unittest.main()
