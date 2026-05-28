from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_recovery_lineage_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeRecoveryLineageNode:
    node_id: str
    node_type: str
    ref_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "ref_id": self.ref_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeRecoveryLineageNode":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            node_id=str(data.get("node_id") or ""),
            node_type=str(data.get("node_type") or ""),
            ref_id=str(data.get("ref_id") or ""),
            payload=copy.deepcopy(data.get("payload") if isinstance(data.get("payload"), dict) else {}),
            metadata=copy.deepcopy(data.get("metadata") if isinstance(data.get("metadata"), dict) else {}),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeRecoveryLineageEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relation": self.relation,
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeRecoveryLineageEdge":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            edge_id=str(data.get("edge_id") or ""),
            source_node_id=str(data.get("source_node_id") or ""),
            target_node_id=str(data.get("target_node_id") or ""),
            relation=str(data.get("relation") or ""),
            metadata=copy.deepcopy(data.get("metadata") if isinstance(data.get("metadata"), dict) else {}),
            created_at=str(data.get("created_at") or utc_timestamp()),
        )


class RuntimeRecoveryLineageRejected(RuntimeError):
    pass


class RuntimeRecoveryLineage:
    """
    Causal graph for recovery continuity.

    Owns only the graph:
    session -> incident -> ticket -> recovery -> execution -> replay -> escalation
    """

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self._nodes: dict[str, RuntimeRecoveryLineageNode] = {}
        self._edges: dict[str, RuntimeRecoveryLineageEdge] = {}
        self._node_order: list[str] = []
        self._edge_order: list[str] = []
        if self.storage_path is not None:
            self.load()

    def add_node(
        self,
        *,
        node_type: str,
        ref_id: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        node_id: str | None = None,
    ) -> RuntimeRecoveryLineageNode:
        node_type = self._validate_text("node_type", node_type)
        ref_id = self._validate_text("ref_id", ref_id)
        if node_id is None:
            node_id = f"recovery-lineage-node-{stable_recovery_lineage_fingerprint({'node_type': node_type, 'ref_id': ref_id})[:16]}"
        node_id = self._validate_text("node_id", node_id)

        existing = self._nodes.get(node_id)
        if existing is not None:
            return copy.deepcopy(existing)

        node = RuntimeRecoveryLineageNode(
            node_id=node_id,
            node_type=node_type,
            ref_id=ref_id,
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._nodes[node_id] = node
        self._node_order.append(node_id)
        self.save()
        return copy.deepcopy(node)

    def add_edge(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        relation: str,
        metadata: dict[str, Any] | None = None,
        edge_id: str | None = None,
    ) -> RuntimeRecoveryLineageEdge:
        source_node_id = self._validate_text("source_node_id", source_node_id)
        target_node_id = self._validate_text("target_node_id", target_node_id)
        relation = self._validate_text("relation", relation)

        if source_node_id not in self._nodes:
            raise RuntimeRecoveryLineageRejected(f"source lineage node does not exist: {source_node_id!r}")
        if target_node_id not in self._nodes:
            raise RuntimeRecoveryLineageRejected(f"target lineage node does not exist: {target_node_id!r}")

        if edge_id is None:
            edge_id = "recovery-lineage-edge-" + stable_recovery_lineage_fingerprint(
                {
                    "source_node_id": source_node_id,
                    "target_node_id": target_node_id,
                    "relation": relation,
                }
            )[:16]
        edge_id = self._validate_text("edge_id", edge_id)

        existing = self._edges.get(edge_id)
        if existing is not None:
            return copy.deepcopy(existing)

        edge = RuntimeRecoveryLineageEdge(
            edge_id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation=relation,
            metadata=copy.deepcopy(metadata or {}),
        )
        self._edges[edge_id] = edge
        self._edge_order.append(edge_id)
        self.save()
        return copy.deepcopy(edge)

    def link_recovery_chain(
        self,
        *,
        source_session_id: str,
        incident_id: str,
        ticket_id: str,
        recovery_id: str,
        execution_id: str = "",
        replay_id: str = "",
        escalation_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = copy.deepcopy(metadata or {})
        nodes: dict[str, RuntimeRecoveryLineageNode] = {}
        edges: list[RuntimeRecoveryLineageEdge] = []

        if source_session_id:
            nodes["source_session"] = self.add_node(
                node_type="source_session",
                ref_id=source_session_id,
                metadata=metadata,
            )
        if incident_id:
            nodes["incident"] = self.add_node(
                node_type="incident",
                ref_id=incident_id,
                metadata=metadata,
            )
        if ticket_id:
            nodes["ticket"] = self.add_node(
                node_type="recovery_ticket",
                ref_id=ticket_id,
                metadata=metadata,
            )
        if recovery_id:
            nodes["recovery"] = self.add_node(
                node_type="recovery",
                ref_id=recovery_id,
                metadata=metadata,
            )
        if execution_id:
            nodes["execution"] = self.add_node(
                node_type="recovery_execution",
                ref_id=execution_id,
                metadata=metadata,
            )
        if replay_id:
            nodes["replay"] = self.add_node(
                node_type="runtime_replay",
                ref_id=replay_id,
                metadata=metadata,
            )
        if escalation_id:
            nodes["escalation"] = self.add_node(
                node_type="supervisor_escalation",
                ref_id=escalation_id,
                metadata=metadata,
            )

        def maybe_edge(left: str, right: str, relation: str) -> None:
            if left in nodes and right in nodes:
                edges.append(
                    self.add_edge(
                        source_node_id=nodes[left].node_id,
                        target_node_id=nodes[right].node_id,
                        relation=relation,
                        metadata=metadata,
                    )
                )

        maybe_edge("source_session", "incident", "produced_incident")
        maybe_edge("incident", "ticket", "queued_recovery")
        maybe_edge("ticket", "recovery", "created_recovery")
        maybe_edge("recovery", "execution", "executed_recovery")
        maybe_edge("execution", "replay", "linked_runtime_replay")
        maybe_edge("ticket", "escalation", "escalated_to_supervisor")
        maybe_edge("recovery", "escalation", "recovery_escalated")

        return {
            "runtime_phase": "runtime_recovery_lineage",
            "nodes": {key: node.to_dict() for key, node in nodes.items()},
            "edges": [edge.to_dict() for edge in edges],
        }

    def lineage_for_ref(self, ref_id: str) -> dict[str, Any]:
        ref_id = self._validate_text("ref_id", ref_id)
        node_ids = {node.node_id for node in self._nodes.values() if node.ref_id == ref_id}
        expanded = set(node_ids)
        changed = True
        while changed:
            changed = False
            for edge in self._edges.values():
                if edge.source_node_id in expanded and edge.target_node_id not in expanded:
                    expanded.add(edge.target_node_id)
                    changed = True
                if edge.target_node_id in expanded and edge.source_node_id not in expanded:
                    expanded.add(edge.source_node_id)
                    changed = True

        return {
            "runtime_phase": "runtime_recovery_lineage_query",
            "ref_id": ref_id,
            "nodes": [
                self._nodes[node_id].to_dict()
                for node_id in self._node_order
                if node_id in expanded and node_id in self._nodes
            ],
            "edges": [
                self._edges[edge_id].to_dict()
                for edge_id in self._edge_order
                if edge_id in self._edges
                and self._edges[edge_id].source_node_id in expanded
                and self._edges[edge_id].target_node_id in expanded
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_recovery_lineage",
            "nodes": [self._nodes[node_id].to_dict() for node_id in self._node_order if node_id in self._nodes],
            "edges": [self._edges[edge_id].to_dict() for edge_id in self._edge_order if edge_id in self._edges],
        }

    def load(self) -> None:
        if self.storage_path is None:
            return
        if not self.storage_path.exists():
            self._nodes = {}
            self._edges = {}
            self._node_order = []
            self._edge_order = []
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        nodes = payload.get("nodes") if isinstance(payload, dict) else []
        edges = payload.get("edges") if isinstance(payload, dict) else []

        self._nodes = {}
        self._edges = {}
        self._node_order = []
        self._edge_order = []

        if isinstance(nodes, list):
            for item in nodes:
                if not isinstance(item, dict):
                    continue
                node = RuntimeRecoveryLineageNode.from_dict(item)
                if node.node_id:
                    self._nodes[node.node_id] = node
                    self._node_order.append(node.node_id)

        if isinstance(edges, list):
            for item in edges:
                if not isinstance(item, dict):
                    continue
                edge = RuntimeRecoveryLineageEdge.from_dict(item)
                if edge.edge_id:
                    self._edges[edge.edge_id] = edge
                    self._edge_order.append(edge.edge_id)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeRecoveryLineageRejected(f"{field_name}_required")
        return text
