from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.runtime.runtime_authority import (
    RuntimeAuthorityScope,
    RuntimeIdentity,
    default_human_authority_scope,
)
from core.runtime.runtime_capability_scope import (
    RuntimeCapabilityScope,
    default_workspace_capability_scope,
)
from core.runtime.runtime_kernel_protection import RuntimeKernelProtection
from core.runtime.runtime_mutation_gateway import RuntimeMutationGateway
from core.runtime.runtime_mutation_transaction import RuntimeMutationRequest


class RuntimeAuthorityGovernanceContractTest(unittest.TestCase):
    def test_human_identity_may_perform_governed_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = RuntimeMutationGateway(workspace_root=root).mutate(
                self._request(
                    request_id="human-1",
                    operation_type="file_write",
                    target_path="out.txt",
                    content="human",
                    identity=self._identity("human-1", "HUMAN"),
                    authority_scope=default_human_authority_scope(),
                    capability_scope=default_workspace_capability_scope(),
                )
            )
            self.assertEqual((Path(root) / "out.txt").read_text(encoding="utf-8"), "human")

        self.assertEqual(result.status, "committed")
        self.assertEqual(
            result.metadata["authority"]["runtime_identity"]["identity_type"],
            "HUMAN",
        )

    def test_planner_identity_is_scope_restricted(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = RuntimeMutationGateway(workspace_root=root).mutate(
                self._request(
                    request_id="planner-1",
                    operation_type="file_write",
                    target_path="blocked/out.txt",
                    content="planner",
                    identity=self._identity("planner-1", "PLANNER"),
                    authority_scope=RuntimeAuthorityScope(
                        scope_id="authority:planner:allowed-only",
                        allowed_execution_types=("mutation",),
                        allowed_mutation_types=("file_write",),
                        allowed_paths=("allowed/",),
                        risk_ceiling="MODERATE",
                    ),
                    capability_scope=default_workspace_capability_scope(),
                )
            )

        self.assertTrue(result.blocked)
        self.assertEqual(
            result.transaction.metadata["reason"],
            "target_path_outside_authority_scope",
        )

    def test_replay_engine_cannot_mutate_protected_zones(self) -> None:
        result = RuntimeMutationGateway(workspace_root=Path.cwd()).mutate(
            self._request(
                request_id="replay-1",
                operation_type="file_write",
                target_path="core/runtime/replay_block.txt",
                content="no",
                identity=self._identity("replay-1", "REPLAY_ENGINE"),
                authority_scope=default_human_authority_scope(),
                capability_scope=default_workspace_capability_scope(),
            )
        )

        self.assertTrue(result.blocked)
        self.assertEqual(
            result.transaction.metadata["reason"],
            "replay_engine_cannot_mutate_protected_runtime_state",
        )

    def test_external_connector_blocked_from_kernel_mutation(self) -> None:
        result = RuntimeMutationGateway(workspace_root=Path.cwd()).mutate(
            self._request(
                request_id="external-1",
                operation_type="file_write",
                target_path="core/runtime/external_block.txt",
                content="no",
                identity=self._identity("external-1", "EXTERNAL_CONNECTOR"),
                authority_scope=default_human_authority_scope(),
                capability_scope=default_workspace_capability_scope(),
            )
        )

        self.assertTrue(result.blocked)
        self.assertEqual(
            result.transaction.metadata["reason"],
            "external_connector_cannot_mutate_kernel_paths",
        )

    def test_self_edit_blocked_from_governance_layer_mutation(self) -> None:
        result = RuntimeMutationGateway(workspace_root=Path.cwd()).mutate(
            self._request(
                request_id="self-edit-1",
                operation_type="file_write",
                target_path="core/runtime/runtime_mutation_gateway.py",
                content="no",
                identity=self._identity("self-edit-1", "SELF_EDIT"),
                authority_scope=default_human_authority_scope(),
                capability_scope=default_workspace_capability_scope(),
            )
        )

        self.assertTrue(result.blocked)
        self.assertEqual(
            result.transaction.metadata["reason"],
            "self_edit_cannot_mutate_governance_layer_by_default",
        )

    def test_protected_zone_mutation_requires_elevated_authority(self) -> None:
        protection = RuntimeKernelProtection()
        identity = self._identity("human-protected", "HUMAN")
        blocked = protection.evaluate(
            identity=identity,
            target_path="core/runtime/runtime_mutation_policy.py",
            mutation_type="source_code_mutation",
            risk_level="HIGH",
            metadata={},
        )
        allowed = protection.evaluate(
            identity=identity,
            target_path="core/runtime/runtime_mutation_policy.py",
            mutation_type="source_code_mutation",
            risk_level="HIGH",
            metadata={"explicit_authority": True},
        )

        self.assertFalse(blocked.allowed)
        self.assertEqual(
            blocked.decision.reason,
            "protected_zone_high_risk_requires_explicit_authority",
        )
        self.assertTrue(allowed.allowed)

    def test_capability_scope_boundaries_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = RuntimeMutationGateway(workspace_root=root).mutate(
                self._request(
                    request_id="capability-1",
                    operation_type="file_write",
                    target_path="outside/out.txt",
                    content="no",
                    identity=self._identity("capability-1", "HUMAN"),
                    authority_scope=default_human_authority_scope(),
                    capability_scope=RuntimeCapabilityScope(
                        capability_id="capability:limited",
                        accessible_paths=("inside/",),
                        allowed_mutation_types=("file_write",),
                        allowed_execution_types=("mutation",),
                        risk_ceiling="MODERATE",
                        replay_allowed=True,
                        rollback_allowed=True,
                    ),
                )
            )

        self.assertTrue(result.blocked)
        self.assertEqual(
            result.transaction.metadata["reason"],
            "target_path_outside_capability_scope",
        )

    def test_authority_lineage_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = RuntimeMutationGateway(workspace_root=root).mutate(
                self._request(
                    request_id="lineage-auth-1",
                    operation_type="file_write",
                    target_path="lineage.txt",
                    content="ok",
                    identity=self._identity("lineage-auth-1", "HUMAN"),
                    authority_scope=default_human_authority_scope(),
                    capability_scope=default_workspace_capability_scope(),
                    lineage={"request_id": "lineage-auth-1", "parent": "scheduler"},
                )
            )

        self.assertEqual(
            result.metadata["authority"]["authority_lineage"]["parent"],
            "scheduler",
        )
        self.assertEqual(
            result.transaction.lineage["parent"],
            "scheduler",
        )

    def test_audit_and_provenance_metadata_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = RuntimeMutationGateway(workspace_root=root).mutate(
                self._request(
                    request_id="provenance-1",
                    operation_type="file_write",
                    target_path="provenance.txt",
                    content="ok",
                    identity=self._identity("provenance-1", "HUMAN"),
                    authority_scope=default_human_authority_scope(),
                    capability_scope=default_workspace_capability_scope(),
                    audit_id="audit:provenance-1",
                    provenance={"requested_by": "unit_test", "ticket": "authority-v1"},
                )
            )

        self.assertEqual(result.audit_metadata["audit_id"], "audit:provenance-1")
        self.assertEqual(result.metadata["provenance"]["ticket"], "authority-v1")
        self.assertEqual(
            result.execution_result.metadata["provenance"]["requested_by"],
            "unit_test",
        )

    def _request(self, **kwargs) -> RuntimeMutationRequest:
        request_id = str(kwargs.pop("request_id"))
        lineage = dict(kwargs.pop("lineage", {"request_id": request_id}))
        provenance = dict(kwargs.pop("provenance", {"requested_by": "unit_test"}))
        return RuntimeMutationRequest(
            request_id=request_id,
            lineage=lineage,
            replay_id=kwargs.pop("replay_id", f"replay:{request_id}"),
            audit_id=kwargs.pop("audit_id", f"audit:{request_id}"),
            provenance=provenance,
            metadata=kwargs.pop("metadata", {}),
            **kwargs,
        )

    def _identity(self, identity_id: str, identity_type: str) -> RuntimeIdentity:
        return RuntimeIdentity(
            identity_id=identity_id,
            identity_type=identity_type,
            source="tests",
            display_name=identity_id,
            lineage={"identity_id": identity_id},
        )


if __name__ == "__main__":
    unittest.main()
