from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryAuditContractTest(unittest.TestCase):
    def _coordinator_with_verified_recovery(self):
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
        from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryCoordinator

        manager = RuntimeExecutionSessionManager()
        manager.create_session("source-1", "life-source-1")
        manager.start_session("source-1")
        manager.fail_session("source-1")
        coordinator = RuntimeRecoveryCoordinator(session_manager=manager)
        coordinator.create_recovery("recovery-1", "source-1")
        coordinator.run_recovery("recovery-1")
        coordinator.verify_recovery("recovery-1")
        return coordinator

    def test_empty_audit_id_rejected(self) -> None:
        from core.runtime.runtime_recovery_audit import (
            RuntimeRecoveryAudit,
            RuntimeRecoveryAuditRejected,
        )

        with self.assertRaises(RuntimeRecoveryAuditRejected):
            RuntimeRecoveryAudit().record_recovery("", "recovery-1")

    def test_duplicate_audit_id_rejected(self) -> None:
        from core.runtime.runtime_recovery_audit import (
            RuntimeRecoveryAudit,
            RuntimeRecoveryAuditRejected,
        )

        audit = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        )
        audit.record_recovery("audit-1", "recovery-1")

        with self.assertRaises(RuntimeRecoveryAuditRejected):
            audit.record_recovery("audit-1", "recovery-1")

    def test_missing_recovery_id_rejected(self) -> None:
        from core.runtime.runtime_recovery_audit import (
            RuntimeRecoveryAudit,
            RuntimeRecoveryAuditRejected,
        )

        with self.assertRaises(RuntimeRecoveryAuditRejected):
            RuntimeRecoveryAudit(
                recovery_coordinator=self._coordinator_with_verified_recovery()
            ).record_recovery("audit-1", "missing")

    def test_record_recovery_creates_audit(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        record = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        ).record_recovery("audit-1", "recovery-1")

        self.assertEqual(record.audit_id, "audit-1")
        self.assertEqual(record.sequence, 1)

    def test_audit_preserves_recovery_id(self) -> None:
        record = self._record_default_audit()

        self.assertEqual(record.recovery_id, "recovery-1")

    def test_audit_preserves_source_session_id(self) -> None:
        record = self._record_default_audit()

        self.assertEqual(record.source_session_id, "source-1")

    def test_audit_preserves_repair_session_id(self) -> None:
        record = self._record_default_audit()

        self.assertEqual(record.repair_session_id, "recovery-1:repair")

    def test_audit_preserves_replay_id(self) -> None:
        record = self._record_default_audit()

        self.assertEqual(record.replay_id, "recovery-1:replay")

    def test_audit_preserves_status(self) -> None:
        record = self._record_default_audit()

        self.assertEqual(record.status, "verified")

    def test_audit_preserves_verified(self) -> None:
        record = self._record_default_audit()

        self.assertTrue(record.verified)

    def test_audit_preserves_steps(self) -> None:
        record = self._record_default_audit()

        self.assertEqual(
            [step.step_type for step in record.steps],
            [
                "detect_failure",
                "create_repair_session",
                "mark_incident",
                "mark_repaired",
                "prepare_replay",
            ],
        )

    def test_audit_steps_are_copy(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        coordinator = self._coordinator_with_verified_recovery()
        original_plan = coordinator.get_recovery("recovery-1")
        record = RuntimeRecoveryAudit(
            recovery_coordinator=coordinator
        ).record_recovery("audit-1", "recovery-1")
        record.steps.clear()

        self.assertEqual(len(original_plan.steps), 5)
        self.assertEqual(len(coordinator.get_recovery("recovery-1").steps), 5)

    def test_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        audit = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        )
        first = audit.record_recovery("audit-1", "recovery-1")
        second = audit.record_recovery("audit-2", "recovery-1")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_get_audit_returns_copy(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        audit = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        )
        audit.record_recovery("audit-1", "recovery-1")
        record = audit.get_audit("audit-1")
        record.steps.clear()

        self.assertEqual(len(audit.get_audit("audit-1").steps), 5)

    def test_get_audits_returns_all_audits(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        audit = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        )
        audit.record_recovery("audit-1", "recovery-1")
        audit.record_recovery("audit-2", "recovery-1")

        self.assertEqual(
            [record.audit_id for record in audit.get_audits()],
            ["audit-1", "audit-2"],
        )

    def test_get_audits_filters_recovery_id(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        audit = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        )
        audit.record_recovery("audit-1", "recovery-1")

        self.assertEqual(
            [record.audit_id for record in audit.get_audits("recovery-1")],
            ["audit-1"],
        )
        self.assertEqual(audit.get_audits("missing"), [])

    def test_get_audits_returns_copy(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        audit = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        )
        audit.record_recovery("audit-1", "recovery-1")
        records = audit.get_audits()
        records[0].steps.clear()
        records.clear()

        self.assertEqual(len(audit.get_audits()), 1)
        self.assertEqual(len(audit.get_audits()[0].steps), 5)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        payload = {"audit": "recovery", "items": [1, 2]}

        record = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        ).record_recovery("audit-1", "recovery-1", payload=payload)

        self.assertIs(record.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        metadata = {"source": "contract", "attempt": 1}

        record = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        ).record_recovery("audit-1", "recovery-1", metadata=metadata)

        self.assertIs(record.metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        payload = {"items": [{"audit": "recovery"}]}
        before = copy.deepcopy(payload)

        RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        ).record_recovery("audit-1", "recovery-1", payload=payload)

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        ).record_recovery("audit-1", "recovery-1", metadata=metadata)

        self.assertEqual(metadata, before)

    def test_clear_resets_audit_store(self) -> None:
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        audit = RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        )
        audit.record_recovery("audit-1", "recovery-1")
        audit.clear()
        record = audit.record_recovery("audit-2", "recovery-1")

        self.assertEqual(record.sequence, 1)
        self.assertEqual([item.audit_id for item in audit.get_audits()], ["audit-2"])

    def test_coordinator_exception_wraps_runtime_recovery_audit_rejected(self) -> None:
        from core.runtime.runtime_recovery_audit import (
            RuntimeRecoveryAudit,
            RuntimeRecoveryAuditRejected,
        )

        original = ValueError("boom")

        class FailingCoordinator:
            def get_recovery(self, _recovery_id):
                raise original

        with self.assertRaises(RuntimeRecoveryAuditRejected) as context:
            RuntimeRecoveryAudit(
                recovery_coordinator=FailingCoordinator()
            ).record_recovery("audit-1", "recovery-1")

        self.assertIs(context.exception.original_exception, original)

    def _record_default_audit(self):
        from core.runtime.runtime_recovery_audit import RuntimeRecoveryAudit

        return RuntimeRecoveryAudit(
            recovery_coordinator=self._coordinator_with_verified_recovery()
        ).record_recovery("audit-1", "recovery-1")


if __name__ == "__main__":
    unittest.main()
