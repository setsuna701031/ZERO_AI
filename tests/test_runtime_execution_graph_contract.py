from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeExecutionGraphContractTest(unittest.TestCase):
    def _graph(self):
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraph

        return RuntimeExecutionGraph()

    def test_add_node(self) -> None:
        node = self._graph().add_node("node-1", "lifecycle.queue")

        self.assertEqual(node.node_id, "node-1")
        self.assertEqual(node.operation, "lifecycle.queue")

    def test_empty_node_id_rejected(self) -> None:
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraphRejected

        with self.assertRaises(RuntimeExecutionGraphRejected):
            self._graph().add_node("", "lifecycle.queue")

    def test_empty_operation_rejected(self) -> None:
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraphRejected

        with self.assertRaises(RuntimeExecutionGraphRejected):
            self._graph().add_node("node-1", "")

    def test_duplicate_node_rejected(self) -> None:
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraphRejected

        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")

        with self.assertRaises(RuntimeExecutionGraphRejected):
            graph.add_node("node-1", "lifecycle.dispatch")

    def test_add_dependency(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        edge = graph.add_dependency("node-1", "node-2", reason="after queue")

        self.assertEqual(edge.from_node_id, "node-1")
        self.assertEqual(edge.to_node_id, "node-2")
        self.assertEqual(edge.reason, "after queue")

    def test_dependency_requires_existing_from_node(self) -> None:
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraphRejected

        graph = self._graph()
        graph.add_node("node-2", "lifecycle.dispatch")

        with self.assertRaises(RuntimeExecutionGraphRejected):
            graph.add_dependency("node-1", "node-2")

    def test_dependency_requires_existing_to_node(self) -> None:
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraphRejected

        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")

        with self.assertRaises(RuntimeExecutionGraphRejected):
            graph.add_dependency("node-1", "node-2")

    def test_self_dependency_rejected(self) -> None:
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraphRejected

        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")

        with self.assertRaises(RuntimeExecutionGraphRejected):
            graph.add_dependency("node-1", "node-1")

    def test_duplicate_dependency_rejected(self) -> None:
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraphRejected

        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        graph.add_dependency("node-1", "node-2")

        with self.assertRaises(RuntimeExecutionGraphRejected):
            graph.add_dependency("node-1", "node-2")

    def test_cycle_rejected(self) -> None:
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraphRejected

        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        graph.add_node("node-3", "lifecycle.start_execution")
        graph.add_dependency("node-1", "node-2")
        graph.add_dependency("node-2", "node-3")

        with self.assertRaises(RuntimeExecutionGraphRejected):
            graph.add_dependency("node-3", "node-1")

    def test_node_sequence_increments_globally(self) -> None:
        graph = self._graph()
        first = graph.add_node("node-1", "lifecycle.queue")
        second = graph.add_node("node-2", "lifecycle.dispatch")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_edge_sequence_increments_globally(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        graph.add_node("node-3", "lifecycle.start_execution")
        first = graph.add_dependency("node-1", "node-2")
        second = graph.add_dependency("node-2", "node-3")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_execution_order_respects_dependency(self) -> None:
        graph = self._graph()
        graph.add_node("node-2", "lifecycle.dispatch")
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_dependency("node-1", "node-2")

        self.assertEqual(
            [node.node_id for node in graph.execution_order()],
            ["node-1", "node-2"],
        )

    def test_execution_order_stable_by_node_sequence_for_independent_nodes(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "recovery.run")
        graph.add_node("node-3", "mutation.write")

        self.assertEqual(
            [node.node_id for node in graph.execution_order()],
            ["node-1", "node-2", "node-3"],
        )

    def test_validate_returns_true_for_valid_graph(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        graph.add_dependency("node-1", "node-2")

        self.assertTrue(graph.validate())

    def test_get_dependencies_returns_direct_dependencies(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        graph.add_node("node-3", "lifecycle.start_execution")
        graph.add_dependency("node-1", "node-3")
        graph.add_dependency("node-2", "node-3")

        self.assertEqual(
            [node.node_id for node in graph.get_dependencies("node-3")],
            ["node-1", "node-2"],
        )

    def test_get_dependents_returns_direct_dependents(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        graph.add_node("node-3", "lifecycle.start_execution")
        graph.add_dependency("node-1", "node-2")
        graph.add_dependency("node-1", "node-3")

        self.assertEqual(
            [node.node_id for node in graph.get_dependents("node-1")],
            ["node-2", "node-3"],
        )

    def test_payload_preserved(self) -> None:
        payload = {"task_id": "task-1"}
        node = self._graph().add_node("node-1", "lifecycle.queue", payload=payload)

        self.assertIs(node.payload, payload)

    def test_metadata_preserved(self) -> None:
        metadata = {"source": "contract"}
        node = self._graph().add_node("node-1", "lifecycle.queue", metadata=metadata)

        self.assertIs(node.metadata, metadata)

    def test_runtime_args_preserved(self) -> None:
        runtime_args = {"lifecycle_id": "life-1"}
        node = self._graph().add_node(
            "node-1",
            "lifecycle.queue",
            runtime_args=runtime_args,
        )

        self.assertIs(node.runtime_args, runtime_args)

    def test_edge_metadata_preserved(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        metadata = {"reason": "contract"}
        edge = graph.add_dependency("node-1", "node-2", metadata=metadata)

        self.assertIs(edge.metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        payload = {"items": [{"id": "one"}]}
        before = copy.deepcopy(payload)
        self._graph().add_node("node-1", "lifecycle.queue", payload=payload)

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        metadata = {"tags": ["contract"]}
        before = copy.deepcopy(metadata)
        self._graph().add_node("node-1", "lifecycle.queue", metadata=metadata)

        self.assertEqual(metadata, before)

    def test_runtime_args_not_mutated(self) -> None:
        runtime_args = {"lifecycle_id": "life-1", "tags": ["contract"]}
        before = copy.deepcopy(runtime_args)
        self._graph().add_node(
            "node-1",
            "lifecycle.queue",
            runtime_args=runtime_args,
        )

        self.assertEqual(runtime_args, before)

    def test_edge_metadata_not_mutated(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        metadata = {"tags": ["contract"]}
        before = copy.deepcopy(metadata)
        graph.add_dependency("node-1", "node-2", metadata=metadata)

        self.assertEqual(metadata, before)

    def test_get_node_returns_copy(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        node = graph.get_node("node-1")
        node.operation = "polluted"

        self.assertEqual(graph.get_node("node-1").operation, "lifecycle.queue")

    def test_list_nodes_returns_copy(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        nodes = graph.list_nodes()
        nodes[0].operation = "polluted"
        nodes.clear()

        self.assertEqual(len(graph.list_nodes()), 1)
        self.assertEqual(graph.list_nodes()[0].operation, "lifecycle.queue")

    def test_list_edges_returns_copy(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        graph.add_dependency("node-1", "node-2")
        edges = graph.list_edges()
        edges[0].reason = "polluted"
        edges.clear()

        self.assertEqual(len(graph.list_edges()), 1)
        self.assertEqual(graph.list_edges()[0].reason, "")

    def test_execution_order_returns_copy(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        nodes = graph.execution_order()
        nodes[0].operation = "polluted"

        self.assertEqual(graph.execution_order()[0].operation, "lifecycle.queue")

    def test_clear_resets_graph_and_sequences(self) -> None:
        graph = self._graph()
        graph.add_node("node-1", "lifecycle.queue")
        graph.add_node("node-2", "lifecycle.dispatch")
        graph.add_dependency("node-1", "node-2")
        graph.clear()
        node = graph.add_node("node-3", "lifecycle.queue")
        graph.add_node("node-4", "lifecycle.dispatch")
        edge = graph.add_dependency("node-3", "node-4")

        self.assertEqual(node.sequence, 1)
        self.assertEqual(edge.sequence, 1)
        self.assertEqual(len(graph.list_nodes()), 2)
        self.assertEqual(len(graph.list_edges()), 1)


if __name__ == "__main__":
    unittest.main()
