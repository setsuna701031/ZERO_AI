from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass
class RuntimeExecutionGraphNode:
    node_id: str
    operation: str
    runtime_args: Any
    payload: Any
    metadata: Any
    sequence: int


@dataclass
class RuntimeExecutionGraphEdge:
    from_node_id: str
    to_node_id: str
    reason: str
    metadata: Any
    sequence: int


class RuntimeExecutionGraphRejected(RuntimeError):
    pass


class RuntimeExecutionGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, RuntimeExecutionGraphNode] = {}
        self._edges: list[RuntimeExecutionGraphEdge] = []
        self._node_sequence = 0
        self._edge_sequence = 0

    def add_node(
        self,
        node_id: str,
        operation: str,
        runtime_args: Any = None,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeExecutionGraphNode:
        node_id = self._validate_text("node_id", node_id)
        operation = self._validate_text("operation", operation)
        if node_id in self._nodes:
            raise RuntimeExecutionGraphRejected(
                f"runtime execution graph duplicate node: {node_id!r}"
            )

        self._node_sequence += 1
        node = RuntimeExecutionGraphNode(
            node_id=node_id,
            operation=operation,
            runtime_args=runtime_args,
            payload=payload,
            metadata=metadata,
            sequence=self._node_sequence,
        )
        self._nodes[node_id] = node
        return self._copy_node(node)

    def add_dependency(
        self,
        from_node_id: str,
        to_node_id: str,
        reason: str | None = None,
        metadata: Any = None,
    ) -> RuntimeExecutionGraphEdge:
        from_node_id = self._validate_text("from_node_id", from_node_id)
        to_node_id = self._validate_text("to_node_id", to_node_id)
        if from_node_id not in self._nodes:
            raise RuntimeExecutionGraphRejected(
                f"runtime execution graph unknown from_node_id: {from_node_id!r}"
            )
        if to_node_id not in self._nodes:
            raise RuntimeExecutionGraphRejected(
                f"runtime execution graph unknown to_node_id: {to_node_id!r}"
            )
        if from_node_id == to_node_id:
            raise RuntimeExecutionGraphRejected(
                "runtime execution graph self dependency rejected"
            )
        if any(
            edge.from_node_id == from_node_id and edge.to_node_id == to_node_id
            for edge in self._edges
        ):
            raise RuntimeExecutionGraphRejected(
                "runtime execution graph duplicate dependency rejected"
            )
        if self._has_path(to_node_id, from_node_id):
            raise RuntimeExecutionGraphRejected(
                "runtime execution graph cycle rejected"
            )

        self._edge_sequence += 1
        edge = RuntimeExecutionGraphEdge(
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            reason="" if reason is None else reason,
            metadata=metadata,
            sequence=self._edge_sequence,
        )
        self._edges.append(edge)
        return self._copy_edge(edge)

    def get_node(self, node_id: str) -> RuntimeExecutionGraphNode:
        node_id = self._validate_text("node_id", node_id)
        node = self._nodes.get(node_id)
        if node is None:
            raise RuntimeExecutionGraphRejected(
                f"runtime execution graph unknown node: {node_id!r}"
            )

        return self._copy_node(node)

    def list_nodes(self) -> list[RuntimeExecutionGraphNode]:
        return [
            self._copy_node(node)
            for node in sorted(self._nodes.values(), key=lambda item: item.sequence)
        ]

    def list_edges(self) -> list[RuntimeExecutionGraphEdge]:
        return [
            self._copy_edge(edge)
            for edge in sorted(self._edges, key=lambda item: item.sequence)
        ]

    def get_dependencies(self, node_id: str) -> list[RuntimeExecutionGraphNode]:
        node_id = self._validate_text("node_id", node_id)
        if node_id not in self._nodes:
            raise RuntimeExecutionGraphRejected(
                f"runtime execution graph unknown node: {node_id!r}"
            )
        dependency_ids = {
            edge.from_node_id for edge in self._edges if edge.to_node_id == node_id
        }
        return [
            self._copy_node(node)
            for node in sorted(
                (self._nodes[node_id] for node_id in dependency_ids),
                key=lambda item: item.sequence,
            )
        ]

    def get_dependents(self, node_id: str) -> list[RuntimeExecutionGraphNode]:
        node_id = self._validate_text("node_id", node_id)
        if node_id not in self._nodes:
            raise RuntimeExecutionGraphRejected(
                f"runtime execution graph unknown node: {node_id!r}"
            )
        dependent_ids = {
            edge.to_node_id for edge in self._edges if edge.from_node_id == node_id
        }
        return [
            self._copy_node(node)
            for node in sorted(
                (self._nodes[node_id] for node_id in dependent_ids),
                key=lambda item: item.sequence,
            )
        ]

    def execution_order(self) -> list[RuntimeExecutionGraphNode]:
        self._assert_valid()
        incoming_counts = {node_id: 0 for node_id in self._nodes}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in self._nodes}
        for edge in self._edges:
            incoming_counts[edge.to_node_id] += 1
            outgoing[edge.from_node_id].append(edge.to_node_id)

        ready = sorted(
            [
                self._nodes[node_id]
                for node_id, count in incoming_counts.items()
                if count == 0
            ],
            key=lambda item: item.sequence,
        )
        ordered: list[RuntimeExecutionGraphNode] = []

        while ready:
            node = ready.pop(0)
            ordered.append(node)
            for dependent_id in sorted(
                outgoing[node.node_id],
                key=lambda item: self._nodes[item].sequence,
            ):
                incoming_counts[dependent_id] -= 1
                if incoming_counts[dependent_id] == 0:
                    ready.append(self._nodes[dependent_id])
                    ready.sort(key=lambda item: item.sequence)

        if len(ordered) != len(self._nodes):
            raise RuntimeExecutionGraphRejected(
                "runtime execution graph cycle rejected"
            )

        return [self._copy_node(node) for node in ordered]

    def validate(self) -> bool:
        self._assert_valid()
        return True

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._node_sequence = 0
        self._edge_sequence = 0

    def _assert_valid(self) -> None:
        for edge in self._edges:
            if edge.from_node_id not in self._nodes or edge.to_node_id not in self._nodes:
                raise RuntimeExecutionGraphRejected(
                    "runtime execution graph invalid edge endpoint"
                )
        for node_id in self._nodes:
            if self._has_path(node_id, node_id, allow_zero_length=False):
                raise RuntimeExecutionGraphRejected(
                    "runtime execution graph cycle rejected"
                )

    def _has_path(
        self,
        start_node_id: str,
        target_node_id: str,
        allow_zero_length: bool = True,
    ) -> bool:
        if allow_zero_length and start_node_id == target_node_id:
            return True

        visited: set[str] = set()
        stack = [start_node_id]
        while stack:
            current = stack.pop()
            for edge in self._edges:
                if edge.from_node_id != current:
                    continue
                if edge.to_node_id == target_node_id:
                    return True
                if edge.to_node_id not in visited:
                    visited.add(edge.to_node_id)
                    stack.append(edge.to_node_id)

        return False

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimeExecutionGraphRejected(
                f"runtime execution graph {field_name} is required"
            )

        return value

    def _copy_node(
        self,
        node: RuntimeExecutionGraphNode,
    ) -> RuntimeExecutionGraphNode:
        return replace(node)

    def _copy_edge(
        self,
        edge: RuntimeExecutionGraphEdge,
    ) -> RuntimeExecutionGraphEdge:
        return replace(edge)
