from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceQueryContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "query-contract"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _query(self):
        from core.runtime.runtime_evidence_query import RuntimeEvidenceQuery

        return RuntimeEvidenceQuery()

    def test_deterministic_query_output(self) -> None:
        query = self._query()
        first_seal = self._seal("deterministic-query")
        second_seal = self._seal("deterministic-query")

        first = {
            "sealed": query.sealed_state(first_seal),
            "execution": query.lookup_execution(first_seal, "step_executor.execute"),
            "lineage": query.replay_lineage(first_seal),
            "rollback": query.rollback_linkage(first_seal),
        }
        second = {
            "sealed": query.sealed_state(second_seal),
            "execution": query.lookup_execution(second_seal, "step_executor.execute"),
            "lineage": query.replay_lineage(second_seal),
            "rollback": query.rollback_linkage(second_seal),
        }

        self.assertEqual(first, second)
        self.assertEqual(
            first["execution"]["summary_fingerprint"],
            second["execution"]["summary_fingerprint"],
        )

    def test_missing_execution_safety(self) -> None:
        query = self._query()

        missing_source = query.lookup_execution(None, "missing.execute")
        missing_id = query.lookup_execution(self._seal(), "")
        missing_step = query.lookup_step(None, "step_executor.execute")

        self.assertFalse(missing_source["found"])
        self.assertFalse(missing_id["found"])
        self.assertFalse(missing_step["found"])
        self.assertEqual(missing_source["execution_id"], "missing.execute")

    def test_replay_lineage_lookup_behavior(self) -> None:
        seal = self._seal("lineage-query")
        lineage = self._query().replay_lineage(seal)

        self.assertTrue(lineage["found"])
        self.assertTrue(lineage["verified"])
        self.assertEqual(
            [node["type"] for node in lineage["lineage"]],
            ["plan", "snapshot", "replay", "audit", "bundle"],
        )
        self.assertEqual(lineage["lineage_ids"][0], "lineage-query:mainline-plan")
        self.assertEqual(lineage["lineage_ids"][-1], "lineage-query:runtime-evidence:bundle")

    def test_rollback_linkage_lookup_behavior(self) -> None:
        seal = self._seal("rollback-query")
        linkage = self._query().rollback_linkage(seal)

        self.assertTrue(linkage["found"])
        self.assertTrue(linkage["verified"])
        self.assertEqual(linkage["rollback_id"], "rollback-query:runtime-evidence:rollback")
        self.assertEqual(
            linkage["rollback_order"],
            ["step_executor.execute", "task_runtime.lifecycle", "scheduler.dispatch"],
        )
        self.assertEqual(linkage["rollback_step_count"], 3)

    def test_failed_step_extraction_from_step_events(self) -> None:
        query = self._query()
        summary = query.summary_from(self._seal("failed-step-query"))
        summary["events"]["step_executor"] = {
            "count": 3,
            "phases": ["before_step", "step_failure", "after_step"],
            "statuses": ["pending", "failed", "succeeded"],
            "fingerprints": ["fp-before", "fp-failed", "fp-after"],
        }

        failed = query.failed_steps(summary)

        self.assertTrue(failed["failed"])
        self.assertEqual(failed["failed_step_count"], 1)
        self.assertEqual(
            failed["failed_steps"],
            [
                {
                    "source": "step_executor_event",
                    "event_index": 1,
                    "phase": "step_failure",
                    "status": "failed",
                    "fingerprint": "fp-failed",
                }
            ],
        )

    def test_sealed_state_queries(self) -> None:
        query = self._query()
        sealed = query.sealed_state(self._seal("sealed-query"))
        unsealed = query.sealed_state(None)

        self.assertTrue(sealed["sealed"])
        self.assertTrue(sealed["complete"])
        self.assertEqual(sealed["reason"], "")
        self.assertFalse(unsealed["sealed"])
        self.assertFalse(unsealed["complete"])
        self.assertEqual(unsealed["reason"], "missing_evidence")
        self.assertEqual(
            unsealed["missing_records"],
            ["snapshot", "replay", "audit", "rollback", "bundle"],
        )

    def test_event_filtering_helpers(self) -> None:
        seal = self._seal("event-filter-query")
        seal.step_hook.before_step(
            task_id="task-1",
            step_id="step-1",
            step_type="respond",
        )
        seal.step_hook.after_step(
            task_id="task-1",
            step_id="step-1",
            step_type="respond",
            status="succeeded",
        )

        filtered = self._query().filter_events(
            seal,
            layer="step_executor",
            status="succeeded",
        )

        self.assertEqual(filtered["count"], 1)
        self.assertEqual(filtered["events"][0]["layer"], "step_executor")
        self.assertEqual(filtered["events"][0]["phase"], "after_step")
        self.assertEqual(filtered["events"][0]["status"], "succeeded")

    def test_queries_do_not_mutate_consumer_summary(self) -> None:
        query = self._query()
        summary = query.summary_from(self._seal("query-mutation"))
        before = copy.deepcopy(summary)

        execution = query.lookup_execution(summary, "scheduler.dispatch")
        execution["record_refs"]["bundle_id"] = "polluted"
        query.replay_lineage(summary)["lineage"].append({"type": "polluted", "id": "polluted"})
        query.rollback_linkage(summary)["rollback_order"].append("polluted")

        self.assertEqual(summary, before)


if __name__ == "__main__":
    unittest.main()
