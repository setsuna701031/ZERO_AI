from __future__ import annotations

import unittest

from core.runtime.runtime_authority import (
    RuntimeAuthorityScope,
    RuntimeIdentity,
    default_human_authority_scope,
)
from core.runtime.runtime_capability_scope import default_workspace_capability_scope
from core.runtime.runtime_memory_constitution import (
    RuntimeMemoryConstitution,
    RuntimeMemoryRecord,
)
from core.runtime.runtime_session_governance import RuntimeSessionGovernance
from core.runtime.runtime_state_gateway import RuntimeStateGateway
from core.runtime.runtime_state_graph import RuntimeStateGraphBuilder
from core.runtime.runtime_state_record import RuntimeStateOwner, hash_state_data


class RuntimeStateMemoryConstitutionTest(unittest.TestCase):
    def test_runtime_state_record_is_typed_and_lineage_aware(self) -> None:
        result = self._gateway().create_state_record(
            state_id="state:execution:1",
            state_type="EXECUTION_STATE",
            owner=self._owner("owner-1"),
            data={"status": "succeeded"},
            lineage={"execution_id": "execution-1"},
            provenance={"requested_by": "unit_test"},
            memory_class="SESSION",
            capability_scope=default_workspace_capability_scope(),
        )

        record = result["record"]
        self.assertTrue(result["ok"])
        self.assertEqual(record.state_type, "EXECUTION_STATE")
        self.assertEqual(record.lineage["execution_id"], "execution-1")
        self.assertEqual(record.data_hash, hash_state_data({"status": "succeeded"}))

    def test_runtime_state_graph_links_execution_mutation_authority_snapshot(self) -> None:
        gateway = self._gateway()
        result = gateway.create_state_record(
            state_id="state:mutation:1",
            state_type="MUTATION_STATE",
            owner=self._owner("owner-2"),
            data={"transaction_id": "mutation-1"},
            lineage={"transaction_id": "mutation-1"},
            provenance={"requested_by": "unit_test"},
            memory_class="SESSION",
            capability_scope=default_workspace_capability_scope(),
            dependencies=(
                "execution:1",
                "mutation:1",
                "authority:owner-2",
                "snapshot:1",
            ),
        )
        graph = result["graph"]
        edge_types = {edge.edge_type for edge in graph.edges}

        self.assertIn("created_by", edge_types)
        self.assertIn("authorized_by", edge_types)
        self.assertIn("depends_on", edge_types)
        self.assertTrue(
            any(
                edge.from_node_id == "state:mutation:1"
                and edge.to_node_id == "snapshot:1"
                for edge in graph.edges
            )
        )

    def test_kernel_memory_blocks_unauthorized_mutation(self) -> None:
        memory = RuntimeMemoryConstitution()
        result = memory.evaluate(
            record=RuntimeMemoryRecord(
                memory_id="memory:kernel:1",
                memory_class="KERNEL",
                owner_id="owner-1",
                lineage={"state_id": "kernel-state"},
            ),
            operation="write",
            actor_id="owner-1",
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.decision.reason, "kernel_memory_requires_explicit_authority")

    def test_audit_memory_is_append_only(self) -> None:
        memory = RuntimeMemoryConstitution()
        append = memory.evaluate(
            record=RuntimeMemoryRecord(
                memory_id="memory:audit:1",
                memory_class="AUDIT",
                owner_id="owner-1",
                lineage={"audit_id": "audit-1"},
                append_only=True,
            ),
            operation="append",
            actor_id="owner-1",
        )
        overwrite = memory.evaluate(
            record=RuntimeMemoryRecord(
                memory_id="memory:audit:1",
                memory_class="AUDIT",
                owner_id="owner-1",
                lineage={"audit_id": "audit-1"},
                append_only=True,
            ),
            operation="write",
            actor_id="owner-1",
        )

        self.assertTrue(append.allowed)
        self.assertFalse(overwrite.allowed)
        self.assertEqual(overwrite.decision.reason, "audit_memory_append_only")

    def test_replay_memory_becomes_immutable_after_seal(self) -> None:
        result = RuntimeMemoryConstitution().evaluate(
            record=RuntimeMemoryRecord(
                memory_id="memory:replay:1",
                memory_class="REPLAY",
                owner_id="owner-1",
                lineage={"replay_id": "replay-1"},
                sealed=True,
            ),
            operation="write",
            actor_id="owner-1",
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.decision.reason, "replay_memory_immutable_after_seal")

    def test_session_memory_is_owner_bound(self) -> None:
        gateway = self._gateway()
        gateway.create_state_record(
            state_id="state:session:1",
            state_type="SESSION_STATE",
            owner=self._owner("owner-session"),
            data={"status": "active"},
            lineage={"session_id": "session-1"},
            provenance={"requested_by": "unit_test"},
            memory_class="SESSION",
            capability_scope=default_workspace_capability_scope(),
        )
        result = gateway.update_state_record(
            state_id="state:session:1",
            data={"status": "sealed"},
            identity=self._identity("other-owner"),
            authority_scope=default_human_authority_scope(),
            provenance={"requested_by": "unit_test"},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["access"].decision.reason, "state_owner_mismatch")

    def test_state_gateway_preserves_provenance_metadata(self) -> None:
        result = self._gateway().create_state_record(
            state_id="state:audit:1",
            state_type="AUDIT_STATE",
            owner=self._owner("owner-audit"),
            data={"event": "created"},
            lineage={"audit_id": "audit-1"},
            provenance={"requested_by": "unit_test", "ticket": "state-v1"},
            memory_class="AUDIT",
            capability_scope=default_workspace_capability_scope(),
        )

        self.assertEqual(result["metadata"]["provenance"]["ticket"], "state-v1")
        self.assertEqual(result["record"].metadata["provenance"]["ticket"], "state-v1")

    def test_state_access_decisions_enforce_authority(self) -> None:
        gateway = self._gateway()
        gateway.create_state_record(
            state_id="state:authority:1",
            state_type="AUTHORITY_STATE",
            owner=self._owner("owner-auth"),
            data={"scope": "owned"},
            lineage={"authority_id": "authority-1"},
            provenance={"requested_by": "unit_test"},
            memory_class="SESSION",
            capability_scope=default_workspace_capability_scope(),
        )
        access = gateway.evaluate_state_access(
            state_id="state:authority:1",
            identity=self._identity("different"),
            authority_scope=RuntimeAuthorityScope(
                scope_id="authority:different",
                allowed_execution_types=("*",),
                allowed_mutation_types=("*",),
                allowed_paths=("*",),
                risk_ceiling="MODERATE",
            ),
            access_type="write",
        )

        self.assertFalse(access.allowed)
        self.assertEqual(access.decision.reason, "state_owner_mismatch")

    def test_runtime_state_graph_can_verify_dependency_edges(self) -> None:
        graph = RuntimeStateGraphBuilder()
        graph.add_node(node_id="state:1", node_type="EXECUTION_STATE", reference_id="state:1")
        graph.add_node(node_id="snapshot:1", node_type="snapshot", reference_id="snapshot:1")
        graph.add_edge(
            edge_id="edge:state:1:snapshot:1",
            edge_type="depends_on",
            from_node_id="state:1",
            to_node_id="snapshot:1",
        )

        self.assertTrue(graph.verify_dependency_edge("state:1", "snapshot:1"))
        self.assertFalse(graph.verify_dependency_edge("state:1", "missing"))

    def test_session_governance_tracks_lifecycle_and_owner(self) -> None:
        owner = self._identity("session-owner")
        governance = RuntimeSessionGovernance()
        created = governance.create_session(
            session_id="session-1",
            owner_identity=owner,
            authority_scope=default_human_authority_scope(),
            lineage={"session_id": "session-1"},
        )
        active = governance.transition(
            session=created.session,
            status="active",
            actor_identity=owner,
        )

        self.assertTrue(created.allowed)
        self.assertTrue(active.allowed)
        self.assertEqual(active.session.status, "active")

    def _gateway(self) -> RuntimeStateGateway:
        return RuntimeStateGateway()

    def _owner(self, owner_id: str) -> RuntimeStateOwner:
        identity = self._identity(owner_id)
        return RuntimeStateOwner(
            owner_id=owner_id,
            identity=identity,
            authority_scope=default_human_authority_scope(),
        )

    def _identity(self, identity_id: str) -> RuntimeIdentity:
        return RuntimeIdentity(
            identity_id=identity_id,
            identity_type="HUMAN",
            source="tests",
            display_name=identity_id,
            lineage={"identity_id": identity_id},
        )


if __name__ == "__main__":
    unittest.main()
