from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.runtime.runtime_authority import (
    RuntimeAuthorityScope,
    RuntimeIdentity,
    default_human_authority_scope,
)
from core.runtime.runtime_capability_scope import default_workspace_capability_scope
from core.runtime.runtime_mutation_gateway import RuntimeMutationGateway
from core.runtime.runtime_mutation_policy import (
    MUTATION_POLICY_STATES,
    MUTATION_RISK_LEVELS,
    MutationPolicyDecision,
    RuntimeMutationPolicy,
)
from core.runtime.runtime_mutation_transaction import (
    MUTATION_TRANSACTION_STATUSES,
    RuntimeMutationRequest,
    RuntimeMutationTransactionResult,
)
from core.runtime.runtime_state_snapshot import RuntimeStateSnapshotter, hash_text


class RuntimeMutationGovernanceContractTest(unittest.TestCase):
    def test_mutation_policy_result_supports_required_states(self) -> None:
        self.assertTrue(
            {
                "allowed",
                "blocked",
                "requires_confirmation",
                "dry_run_only",
                "sandbox_required",
                "rollback_required",
                "snapshot_required",
            }
            <= MUTATION_POLICY_STATES
        )
        self.assertTrue(
            {"LOW", "MODERATE", "HIGH", "IRREVERSIBLE", "EXTERNAL"}
            <= MUTATION_RISK_LEVELS
        )
        decision = MutationPolicyDecision(
            state="snapshot_required",
            reason="test",
            risk_level="MODERATE",
            policy_source="test",
            target_path="target.txt",
            lineage={"request_id": "request-1"},
            audit_tags=("mutation",),
        )
        self.assertTrue(decision.allowed)

    def test_runtime_mutation_transaction_lifecycle_is_observable(self) -> None:
        self.assertTrue(
            {
                "created",
                "policy_checked",
                "snapshot_created",
                "applied",
                "verified",
                "committed",
                "rolled_back",
                "blocked",
                "failed",
            }
            <= MUTATION_TRANSACTION_STATUSES
        )
        with tempfile.TemporaryDirectory() as root:
            result = self._gateway(root).mutate(
                self._request(
                    request_id="lifecycle-1",
                    operation_type="file_write",
                    target_path="out.txt",
                    content="hello",
                    lineage={"request_id": "lifecycle-1"},
                )
            )
        self.assertEqual(result.transaction.status, "committed")
        self.assertEqual(
            result.transaction.metadata["lifecycle"],
            (
                "created",
                "policy_checked",
                "snapshot_created",
                "applied",
                "verified",
                "committed",
            ),
        )

    def test_snapshot_captures_content_hash(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "state.txt"
            target.write_text("before", encoding="utf-8")
            snapshot = RuntimeStateSnapshotter().capture(
                snapshot_id="snapshot-1",
                source_transaction_id="transaction-1",
                target_paths=(target,),
            )
        self.assertTrue(snapshot.created)
        self.assertTrue(snapshot.verified)
        self.assertEqual(snapshot.snapshot.records[0].content_hash, hash_text("before"))
        self.assertEqual(
            snapshot.snapshot.rollback_metadata["source_transaction_id"],
            "transaction-1",
        )

    def test_mutation_gateway_blocks_unsafe_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = self._gateway(root).mutate(
                self._request(
                    request_id="delete-1",
                    operation_type="file_delete",
                    target_path="out.txt",
                    lineage={"request_id": "delete-1"},
                    replay_id="replay:delete-1",
                    audit_id="audit:delete-1",
                )
            )
        self.assertTrue(result.blocked)
        self.assertEqual(result.transaction.status, "blocked")
        self.assertTrue(result.transaction.rollback_required)
        self.assertEqual(
            result.transaction.metadata["reason"],
            "mutation_operation_not_enabled_for_gateway_v1",
        )

    def test_allowed_mutation_produces_transaction_result(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = self._gateway(root).mutate(
                self._request(
                    request_id="write-1",
                    operation_type="file_write",
                    target_path="nested/out.txt",
                    content="governed",
                    lineage={"request_id": "write-1", "task_id": "task-1"},
                    replay_id="replay:write-1",
                    audit_id="audit:write-1",
                )
            )
            target = Path(root) / "nested" / "out.txt"
            self.assertEqual(target.read_text(encoding="utf-8"), "governed")

        self.assertIsInstance(result, RuntimeMutationTransactionResult)
        self.assertEqual(result.status, "committed")
        self.assertTrue(result.verified)
        self.assertEqual(result.transaction.request_id, "write-1")
        self.assertEqual(result.transaction.policy_result.state, "snapshot_required")
        self.assertEqual(result.transaction.operations[0].after_hash, hash_text("governed"))

    def test_rollback_metadata_exists(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = self._gateway(root).mutate(
                self._request(
                    request_id="rollback-1",
                    operation_type="file_write",
                    target_path="out.txt",
                    content="next",
                    lineage={"request_id": "rollback-1"},
                )
            )
        self.assertTrue(result.rollback_metadata["rollback_compatible"])
        self.assertEqual(
            result.rollback_metadata["snapshot_id"],
            result.transaction.snapshot_id,
        )
        self.assertIn("before_hash", result.rollback_metadata)

    def test_mutation_side_effect_is_registered(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = self._gateway(root).mutate(
                self._request(
                    request_id="effect-1",
                    operation_type="generated_artifact_write",
                    target_path="artifact.txt",
                    content="artifact",
                    lineage={"request_id": "effect-1"},
                )
            )
        effects = [effect for effect in result.side_effects if effect.effect_type == "generated_artifact_write"]
        self.assertEqual(len(effects), 1)
        self.assertTrue(effects[0].verified)
        self.assertTrue(effects[0].rollbackable)

    def test_replay_and_audit_lineage_metadata_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = self._gateway(root).mutate(
                self._request(
                    request_id="lineage-1",
                    operation_type="file_write",
                    target_path="lineage.txt",
                    content="lineage",
                    lineage={"request_id": "lineage-1", "parent": "scheduler"},
                    replay_id="replay:lineage-1",
                    audit_id="audit:lineage-1",
                )
            )
        self.assertEqual(result.replay_metadata["replay_id"], "replay:lineage-1")
        self.assertTrue(result.replay_metadata["replay_observable"])
        self.assertEqual(result.audit_metadata["audit_id"], "audit:lineage-1")
        self.assertTrue(result.audit_metadata["audit_compatible"])
        self.assertEqual(result.audit_metadata["lineage"]["parent"], "scheduler")
        self.assertEqual(result.execution_result.replay_id, "replay:lineage-1")

    def test_policy_classifies_required_mutation_types(self) -> None:
        policy = RuntimeMutationPolicy()
        cases = {
            "file_write": "MODERATE",
            "file_delete": "IRREVERSIBLE",
            "patch_apply": "HIGH",
            "generated_artifact_write": "MODERATE",
            "config_mutation": "HIGH",
            "source_code_mutation": "HIGH",
            "git_mutation": "IRREVERSIBLE",
            "external_state_mutation": "EXTERNAL",
        }
        for operation, risk in cases.items():
            with self.subTest(operation=operation):
                result = policy.evaluate(
                    operation_type=operation,
                    target_path="target.txt",
                    lineage={"request_id": operation},
                    metadata={"snapshot_required": False},
                )
                self.assertEqual(result.risk_level, risk)

    def _gateway(self, root: str) -> RuntimeMutationGateway:
        return RuntimeMutationGateway(workspace_root=root)

    def _request(self, **kwargs) -> RuntimeMutationRequest:
        request_id = str(kwargs.get("request_id") or "request")
        return RuntimeMutationRequest(
            **kwargs,
            identity=RuntimeIdentity(
                identity_id=f"human:{request_id}",
                identity_type="HUMAN",
                source="tests",
                display_name="Test Human",
                lineage={"request_id": request_id},
            ),
            authority_scope=default_human_authority_scope(),
            capability_scope=default_workspace_capability_scope(),
            provenance={"test": "runtime_mutation_governance_contract"},
        )


if __name__ == "__main__":
    unittest.main()
