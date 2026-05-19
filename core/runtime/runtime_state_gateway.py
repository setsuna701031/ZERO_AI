"""Governed runtime state gateway."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.runtime.runtime_authority import RuntimeAuthorityScope, RuntimeIdentity
from core.runtime.runtime_capability_scope import RuntimeCapabilityScope
from core.runtime.runtime_memory_constitution import (
    RuntimeMemoryConstitution,
    RuntimeMemoryRecord,
)
from core.runtime.runtime_state_graph import RuntimeStateGraphBuilder, RuntimeStateGraphResult
from core.runtime.runtime_lifecycle_context import (
    create_current_lifecycle_record,
    lifecycle_id_for_artifact,
    mark_current_lifecycle_active,
    mark_current_lifecycle_committed,
    mark_current_lifecycle_verified,
)
from core.runtime.runtime_transaction_context import bind_current_state, merge_current_transaction_metadata
from core.runtime.runtime_state_record import (
    RUNTIME_STATE_TYPES,
    RuntimeStateAccessEvaluator,
    RuntimeStateAccessResult,
    RuntimeStateOwner,
    RuntimeStateRecord,
    hash_state_data,
    utc_timestamp,
)


class RuntimeStateGateway:
    """Only approved new entrance for governed runtime state records."""

    def __init__(
        self,
        *,
        graph_builder: RuntimeStateGraphBuilder | None = None,
        access_evaluator: RuntimeStateAccessEvaluator | None = None,
        memory_constitution: RuntimeMemoryConstitution | None = None,
    ) -> None:
        self.graph_builder = graph_builder or RuntimeStateGraphBuilder()
        self.access_evaluator = access_evaluator or RuntimeStateAccessEvaluator()
        self.memory_constitution = memory_constitution or RuntimeMemoryConstitution()
        self._records: dict[str, RuntimeStateRecord] = {}

    def create_state_record(
        self,
        *,
        state_id: str,
        state_type: str,
        owner: RuntimeStateOwner,
        data: Any,
        lineage: dict[str, Any],
        provenance: dict[str, Any],
        memory_class: str,
        capability_scope: RuntimeCapabilityScope | None = None,
        dependencies: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = merge_current_transaction_metadata(metadata)
        lineage = merge_current_transaction_metadata({"lineage": dict(lineage)}).get("lineage", dict(lineage))
        provenance = merge_current_transaction_metadata({"provenance": dict(provenance)}).get("provenance", dict(provenance))
        if state_type not in RUNTIME_STATE_TYPES:
            raise ValueError(f"unsupported runtime state type: {state_type}")
        if not lineage:
            raise ValueError("runtime state lineage is required")
        if not provenance:
            raise ValueError("runtime state provenance is required")

        now = utc_timestamp()
        record = RuntimeStateRecord(
            state_id=state_id,
            state_type=state_type,
            owner_id=owner.owner_id,
            authority_scope_id=owner.authority_scope.scope_id,
            lineage=dict(lineage),
            created_at=now,
            updated_at=now,
            status="created",
            data_hash=hash_state_data(data),
            metadata={
                **dict(metadata or {}),
                "provenance": dict(provenance),
                "memory_class": memory_class,
            },
        )
        access_result = self.access_evaluator.evaluate(
            record=record,
            identity=owner.identity,
            authority_scope=owner.authority_scope,
            access_type="write",
            metadata={"provenance": dict(provenance), "explicit_authority": False},
        )
        memory_record = RuntimeMemoryRecord(
            memory_id=f"memory:{state_id}",
            memory_class=memory_class,
            owner_id=owner.owner_id,
            lineage=dict(lineage),
            sealed=bool(record.metadata.get("sealed", False)),
            append_only=memory_class == "AUDIT",
            metadata={"state_id": state_id, "provenance": dict(provenance)},
        )
        memory_result = self.memory_constitution.evaluate(
            record=memory_record,
            operation="append" if memory_class == "AUDIT" else "write",
            actor_id=owner.identity.identity_id,
            capability_scope=capability_scope,
            metadata={
                "explicit_authority": bool((metadata or {}).get("explicit_authority", False)),
                "provenance": dict(provenance),
            },
        )
        if not access_result.allowed or not memory_result.allowed:
            return {
                "ok": False,
                "record": record,
                "access": access_result,
                "memory": memory_result,
                "graph": self.graph_builder.snapshot(),
                "metadata": {
                    "provenance": dict(provenance),
                    "lineage": dict(lineage),
                },
            }

        self._records[state_id] = record
        bind_current_state(state_id, metadata={"source": "runtime_state_gateway"})
        state_lifecycle_id = lifecycle_id_for_artifact("state", state_id)
        create_current_lifecycle_record(
            lifecycle_id=state_lifecycle_id,
            artifact_id=state_id,
            artifact_type="state",
            lineage=lineage,
            provenance=provenance,
            metadata={"source": "runtime_state_gateway", "state_type": state_type},
        )
        mark_current_lifecycle_active(
            state_lifecycle_id,
            metadata={"source": "runtime_state_gateway"},
        )
        mark_current_lifecycle_verified(
            state_lifecycle_id,
            metadata={"source": "runtime_state_gateway"},
        )
        mark_current_lifecycle_committed(
            state_lifecycle_id,
            metadata={"source": "runtime_state_gateway"},
        )
        self.graph_builder.add_node(
            node_id=state_id,
            node_type=state_type,
            reference_id=state_id,
            metadata={
                "owner_id": owner.owner_id,
                "authority_scope_id": owner.authority_scope.scope_id,
                "provenance": dict(provenance),
            },
        )
        self.graph_builder.add_node(
            node_id=owner.identity.identity_id,
            node_type="authority_identity",
            reference_id=owner.identity.identity_id,
            metadata=owner.identity.metadata,
        )
        self.graph_builder.add_edge(
            edge_id=f"edge:{owner.identity.identity_id}:{state_id}:created_by",
            edge_type="created_by",
            from_node_id=state_id,
            to_node_id=owner.identity.identity_id,
            metadata={"provenance": dict(provenance)},
        )
        self.graph_builder.add_edge(
            edge_id=f"edge:{state_id}:{owner.identity.identity_id}:authorized_by",
            edge_type="authorized_by",
            from_node_id=state_id,
            to_node_id=owner.identity.identity_id,
            metadata={"authority_scope_id": owner.authority_scope.scope_id},
        )
        for dependency in dependencies:
            self.graph_builder.add_node(
                node_id=dependency,
                node_type="dependency",
                reference_id=dependency,
            )
            self.graph_builder.add_edge(
                edge_id=f"edge:{state_id}:{dependency}:depends_on",
                edge_type="depends_on",
                from_node_id=state_id,
                to_node_id=dependency,
                metadata={"provenance": dict(provenance)},
            )

        return {
            "ok": True,
            "record": record,
            "access": access_result,
            "memory": memory_result,
            "graph": self.graph_builder.snapshot(),
            "metadata": {
                "provenance": dict(provenance),
                "lineage": dict(lineage),
                "state_gateway": "core.runtime.runtime_state_gateway",
            },
        }

    def evaluate_state_access(
        self,
        *,
        state_id: str,
        identity: RuntimeIdentity,
        authority_scope: RuntimeAuthorityScope,
        access_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeStateAccessResult:
        record = self._records[state_id]
        return self.access_evaluator.evaluate(
            record=record,
            identity=identity,
            authority_scope=authority_scope,
            access_type=access_type,
            metadata=metadata or {},
        )

    def update_state_record(
        self,
        *,
        state_id: str,
        data: Any,
        identity: RuntimeIdentity,
        authority_scope: RuntimeAuthorityScope,
        provenance: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = merge_current_transaction_metadata(metadata)
        provenance = merge_current_transaction_metadata({"provenance": dict(provenance)}).get("provenance", dict(provenance))
        record = self._records[state_id]
        access = self.access_evaluator.evaluate(
            record=record,
            identity=identity,
            authority_scope=authority_scope,
            access_type="write",
            metadata={"provenance": dict(provenance), **dict(metadata or {})},
        )
        if not access.allowed:
            return {"ok": False, "record": record, "access": access}
        updated = replace(
            record,
            updated_at=utc_timestamp(),
            status="updated",
            data_hash=hash_state_data(data),
            metadata={**dict(record.metadata), **dict(metadata or {}), "provenance": dict(provenance)},
        )
        self._records[state_id] = updated
        self.graph_builder.add_edge(
            edge_id=f"edge:{state_id}:{identity.identity_id}:mutated_by",
            edge_type="mutated_by",
            from_node_id=state_id,
            to_node_id=identity.identity_id,
            metadata={"provenance": dict(provenance)},
        )
        return {
            "ok": True,
            "record": updated,
            "access": access,
            "graph": self.graph_builder.snapshot(),
            "metadata": {"provenance": dict(provenance)},
        }

    def graph_result(self) -> RuntimeStateGraphResult:
        graph = self.graph_builder.snapshot()
        return RuntimeStateGraphResult(
            graph=graph,
            updated=True,
            verified=True,
            metadata={"node_count": len(graph.nodes), "edge_count": len(graph.edges)},
        )


def governed_runtime_state_record(
    *,
    state_id: str,
    state_type: str,
    owner: RuntimeStateOwner,
    data: Any,
    lineage: dict[str, Any],
    provenance: dict[str, Any],
    memory_class: str,
    capability_scope: RuntimeCapabilityScope | None = None,
    dependencies: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = merge_current_transaction_metadata(metadata)
    lineage = merge_current_transaction_metadata({"lineage": dict(lineage)}).get("lineage", dict(lineage))
    provenance = merge_current_transaction_metadata({"provenance": dict(provenance)}).get("provenance", dict(provenance))
    return RuntimeStateGateway().create_state_record(
        state_id=state_id,
        state_type=state_type,
        owner=owner,
        data=data,
        lineage=lineage,
        provenance=provenance,
        memory_class=memory_class,
        capability_scope=capability_scope,
        dependencies=dependencies,
        metadata=metadata,
    )
