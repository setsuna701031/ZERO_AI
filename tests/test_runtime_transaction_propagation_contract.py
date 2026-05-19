from __future__ import annotations

import unittest

from core.runtime.runtime_transaction_context import (
    RuntimeTransactionContext,
    clear_current_transaction,
    merge_current_transaction_metadata,
    set_current_transaction,
)


class RuntimeTransactionPropagationContractTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_current_transaction()

    def test_merge_current_transaction_metadata_adds_transaction_identity(self) -> None:
        set_current_transaction(
            RuntimeTransactionContext(
                transaction_id="tx:propagate",
                parent_transaction_id="tx:parent",
                lineage={"task_id": "task-1"},
                provenance={"source": "transaction_scope"},
                authority_metadata={"identity_id": "human:1"},
            )
        )

        metadata = merge_current_transaction_metadata({"operation": "write_runtime_state"})

        self.assertEqual(metadata["transaction_id"], "tx:propagate")
        self.assertEqual(metadata["parent_transaction_id"], "tx:parent")
        self.assertEqual(metadata["runtime_transaction"]["transaction_id"], "tx:propagate")
        self.assertEqual(metadata["runtime_transaction"]["authority"]["identity_id"], "human:1")
        self.assertEqual(metadata["lineage"]["task_id"], "task-1")
        self.assertEqual(metadata["provenance"]["source"], "transaction_scope")
        self.assertEqual(metadata["operation"], "write_runtime_state")

    def test_existing_lineage_and_provenance_are_preserved(self) -> None:
        set_current_transaction(
            RuntimeTransactionContext(
                transaction_id="tx:merge",
                lineage={"task_id": "task-a"},
                provenance={"source": "scope"},
            )
        )

        metadata = merge_current_transaction_metadata(
            {
                "lineage": {"step_id": "step-a"},
                "provenance": {"caller": "runtime_persistence_service"},
            }
        )

        self.assertEqual(metadata["lineage"]["task_id"], "task-a")
        self.assertEqual(metadata["lineage"]["step_id"], "step-a")
        self.assertEqual(metadata["provenance"]["source"], "scope")
        self.assertEqual(metadata["provenance"]["caller"], "runtime_persistence_service")

    def test_no_current_transaction_leaves_metadata_unchanged(self) -> None:
        metadata = merge_current_transaction_metadata({"operation": "read_only"})

        self.assertEqual(metadata, {"operation": "read_only"})


if __name__ == "__main__":
    unittest.main()
