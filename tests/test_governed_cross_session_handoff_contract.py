from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GovernedCrossSessionHandoffContractTest(unittest.TestCase):
    def _continuation(self) -> dict:
        return {
            "continuation_id": "continuation-1",
            "source_session_id": "session-a",
            "target_session_id": "session-b",
            "replay_session_id": "replay-a",
            "continuation_state": "continued",
            "lineage_chain": ["session-a", "replay-a", "session-b"],
            "data_only": True,
        }

    def _replay(self, *, state: str = "consistent") -> dict:
        return {
            "replay_session_id": "replay-a",
            "source_execution_session_id": "session-a",
            "replay_state": state,
            "timeline_replay_valid": state != "blocked",
            "checkpoint_replay_valid": state != "blocked",
            "reason_codes": [],
        }

    def _session(self, *, state: str = "checkpointed") -> dict:
        return {
            "execution_session_id": "session-a",
            "session_state": state,
            "reason_codes": [],
        }

    def _closure(self, *, ready: bool = True) -> dict:
        return {
            "governance_closure_id": "closure-1",
            "closure_ready": ready,
            "closure_state": "closed" if ready else "blocked",
            "runtime_governance_freeze_candidate": ready,
            "reason_codes": [],
        }

    def test_constants_are_stable(self) -> None:
        from core.runtime.governed_cross_session_handoff_contract import (
            governed_cross_session_handoff_required_fields,
            governed_cross_session_handoff_states,
        )

        self.assertEqual(
            governed_cross_session_handoff_states(),
            ["ready", "accepted", "rejected", "blocked"],
        )
        self.assertEqual(
            governed_cross_session_handoff_required_fields(),
            [
                "handoff_id",
                "handoff_state",
                "source_session_id",
                "target_session_id",
                "source_replay_session_id",
                "source_continuation_id",
                "parent_governance_chain_valid",
                "lineage_valid",
                "handoff_acceptance_ready",
                "handoff_payload",
                "blocking_issues",
                "reason_codes",
            ],
        )

    def test_builds_ready_handoff_contract(self) -> None:
        from core.runtime.governed_cross_session_handoff_contract import (
            build_governed_cross_session_handoff_contract,
            validate_governed_cross_session_handoff_contract,
        )

        report = build_governed_cross_session_handoff_contract(
            continuation_record=self._continuation(),
            replay_session_report=self._replay(),
            execution_session_report=self._session(),
            governance_closure_report=self._closure(),
        )
        validation = validate_governed_cross_session_handoff_contract(report)

        self.assertTrue(report["handoff_id"].startswith("governed-cross-session-handoff-"))
        self.assertEqual(report["handoff_state"], "ready")
        self.assertEqual(report["source_session_id"], "session-a")
        self.assertEqual(report["target_session_id"], "session-b")
        self.assertTrue(report["parent_governance_chain_valid"])
        self.assertTrue(report["lineage_valid"])
        self.assertTrue(report["handoff_acceptance_ready"])
        self.assertEqual(report["blocking_issues"], [])
        self.assertTrue(validation["ok"])

    def test_acceptance_context_marks_handoff_accepted(self) -> None:
        from core.runtime.governed_cross_session_handoff_contract import build_governed_cross_session_handoff_contract

        report = build_governed_cross_session_handoff_contract(
            continuation_record=self._continuation(),
            replay_session_report=self._replay(),
            execution_session_report=self._session(),
            governance_closure_report=self._closure(),
            acceptance_context={"accepted": True},
        )

        self.assertEqual(report["handoff_state"], "accepted")
        self.assertTrue(report["handoff_acceptance_ready"])

    def test_invalid_parent_governance_blocks_handoff(self) -> None:
        from core.runtime.governed_cross_session_handoff_contract import build_governed_cross_session_handoff_contract

        report = build_governed_cross_session_handoff_contract(
            continuation_record=self._continuation(),
            replay_session_report=self._replay(),
            execution_session_report=self._session(),
            governance_closure_report=self._closure(ready=False),
        )

        self.assertEqual(report["handoff_state"], "blocked")
        self.assertFalse(report["parent_governance_chain_valid"])
        self.assertIn("parent_governance_chain_invalid", report["reason_codes"])

    def test_invalid_lineage_blocks_handoff(self) -> None:
        from core.runtime.governed_cross_session_handoff_contract import build_governed_cross_session_handoff_contract

        continuation = self._continuation()
        continuation["lineage_chain"] = ["session-a", "session-b"]

        report = build_governed_cross_session_handoff_contract(
            continuation_record=continuation,
            replay_session_report=self._replay(),
            execution_session_report=self._session(),
            governance_closure_report=self._closure(),
        )

        self.assertEqual(report["handoff_state"], "blocked")
        self.assertFalse(report["lineage_valid"])
        self.assertIn("handoff_lineage_invalid", report["reason_codes"])

    def test_invalid_replay_blocks_handoff(self) -> None:
        from core.runtime.governed_cross_session_handoff_contract import build_governed_cross_session_handoff_contract

        report = build_governed_cross_session_handoff_contract(
            continuation_record=self._continuation(),
            replay_session_report=self._replay(state="blocked"),
            execution_session_report=self._session(),
            governance_closure_report=self._closure(),
        )

        self.assertEqual(report["handoff_state"], "blocked")
        self.assertIn("replay_session_invalid", report["reason_codes"])

    def test_rejected_acceptance_blocks_handoff(self) -> None:
        from core.runtime.governed_cross_session_handoff_contract import build_governed_cross_session_handoff_contract

        report = build_governed_cross_session_handoff_contract(
            continuation_record=self._continuation(),
            replay_session_report=self._replay(),
            execution_session_report=self._session(),
            governance_closure_report=self._closure(),
            acceptance_context={"acceptance_state": "rejected"},
        )

        self.assertEqual(report["handoff_state"], "blocked")
        self.assertFalse(report["handoff_acceptance_ready"])
        self.assertIn("handoff_acceptance_not_ready", report["reason_codes"])

    def test_summary_is_deterministic_and_does_not_mutate_inputs(self) -> None:
        from core.runtime.governed_cross_session_handoff_contract import (
            build_governed_cross_session_handoff_contract,
            build_governed_cross_session_handoff_summary,
        )

        continuation = self._continuation()
        replay = self._replay()
        session = self._session()
        closure = self._closure()
        before = (copy.deepcopy(continuation), copy.deepcopy(replay), copy.deepcopy(session), copy.deepcopy(closure))

        first = build_governed_cross_session_handoff_contract(
            continuation_record=continuation,
            replay_session_report=replay,
            execution_session_report=session,
            governance_closure_report=closure,
        )
        second = build_governed_cross_session_handoff_contract(
            continuation_record=continuation,
            replay_session_report=replay,
            execution_session_report=session,
            governance_closure_report=closure,
        )
        summary = build_governed_cross_session_handoff_summary(first)

        self.assertEqual(first, second)
        self.assertEqual((continuation, replay, session, closure), before)
        self.assertEqual(summary["handoff_id"], first["handoff_id"])
        self.assertEqual(summary["handoff_state"], first["handoff_state"])


if __name__ == "__main__":
    unittest.main()
