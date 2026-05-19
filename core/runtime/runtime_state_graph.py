"""Runtime state graph for governed runtime relationships."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


STATE_GRAPH_EDGE_TYPES = frozenset(
    {
        "created_by",
        "mutated_by",
        "authorized_by",
        "replayed_by",
        "rolled_back_by",
        "verified_by",
        "derived_from",
        "depends_on",
    }
)


@dataclass(frozen=True)
class RuntimeStateNode:
    node_id: str
    node_type: str
    reference_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeStateEdge:
    edge_id: str
    edge_type: str
    from_node_id: str
    to_node_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeStateGraph:
    graph_id: str
    nodes: tuple[RuntimeStateNode, ...] = ()
    edges: tuple[RuntimeStateEdge, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeStateGraphResult:
    graph: RuntimeStateGraph
    updated: bool
    verified: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeStateGraphBuilder:
    def __init__(self, graph_id: str = "runtime_state_graph") -> None:
        self._graph = RuntimeStateGraph(graph_id=graph_id)

    def add_node(
        self,
        *,
        node_id: str,
        node_type: str,
        reference_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeStateGraphResult:
        existing = {node.node_id for node in self._graph.nodes}
        nodes = self._graph.nodes
        if node_id not in existing:
            nodes = (
                *nodes,
                RuntimeStateNode(
                    node_id=node_id,
                    node_type=node_type,
                    reference_id=reference_id,
                    metadata=dict(metadata or {}),
                ),
            )
        self._graph = replace(self._graph, nodes=nodes)
        return RuntimeStateGraphResult(
            graph=self.snapshot(),
            updated=True,
            verified=True,
            metadata={"node_id": node_id},
        )

    def add_edge(
        self,
        *,
        edge_id: str,
        edge_type: str,
        from_node_id: str,
        to_node_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeStateGraphResult:
        if edge_type not in STATE_GRAPH_EDGE_TYPES:
            return RuntimeStateGraphResult(
                graph=self.snapshot(),
                updated=False,
                verified=False,
                metadata={"reason": "unsupported_edge_type", "edge_type": edge_type},
            )

        edges = (
            *self._graph.edges,
            RuntimeStateEdge(
                edge_id=edge_id,
                edge_type=edge_type,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                metadata=dict(metadata or {}),
            ),
        )
        self._graph = replace(self._graph, edges=edges)
        return RuntimeStateGraphResult(
            graph=self.snapshot(),
            updated=True,
            verified=self.verify_dependency_edge(from_node_id, to_node_id),
            metadata={"edge_id": edge_id, "edge_type": edge_type},
        )

    def verify_dependency_edge(self, from_node_id: str, to_node_id: str) -> bool:
        node_ids = {node.node_id for node in self._graph.nodes}
        if from_node_id not in node_ids or to_node_id not in node_ids:
            return False
        return any(
            edge.from_node_id == from_node_id
            and edge.to_node_id == to_node_id
            for edge in self._graph.edges
        )

    def snapshot(self) -> RuntimeStateGraph:
        return replace(
            self._graph,
            nodes=tuple(self._graph.nodes),
            edges=tuple(self._graph.edges),
            metadata=dict(self._graph.metadata),
        )
