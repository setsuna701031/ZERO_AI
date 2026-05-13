from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from core.runtime.runtime_execution_graph import RuntimeExecutionGraph
from core.runtime.runtime_operation import RuntimeOperation
from core.runtime.runtime_transaction import RuntimeTransaction


class ExecutionPlanRejected(RuntimeError):
    pass


class ExecutionPlan:
    def __init__(
        self,
        plan_id: str,
        graph: RuntimeExecutionGraph,
        transaction: RuntimeTransaction,
        runtime_args: Any = None,
        metadata: Any = None,
    ) -> None:
        self.plan_id = self._validate_text("plan_id", plan_id)
        self._graph = copy.deepcopy(graph)
        self._transaction = copy.deepcopy(transaction)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._metadata = copy.deepcopy(metadata)
        self._validate_contract()

    @property
    def graph(self) -> RuntimeExecutionGraph:
        return copy.deepcopy(self._graph)

    @property
    def transaction(self) -> RuntimeTransaction:
        return copy.deepcopy(self._transaction)

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def status(self) -> str:
        return self._transaction.status

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "plan_id": self.plan_id,
                "graph": self._graph_source_structure(),
                "transaction_fingerprint": self._transaction.fingerprint,
                "runtime_args": self._runtime_args,
                "metadata": self._metadata,
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def execution_order(self) -> list[RuntimeOperation]:
        ordered_nodes = self._graph.execution_order()
        operations_by_id = {
            operation.operation_id: operation
            for operation in self._transaction.list_operations()
        }
        return [
            copy.deepcopy(operations_by_id[node.node_id])
            for node in ordered_nodes
        ]

    def _validate_contract(self) -> None:
        self._graph.validate()
        graph_nodes = self._graph.list_nodes()
        operations = self._transaction.list_operations()
        graph_ids = {node.node_id for node in graph_nodes}
        operation_ids = {operation.operation_id for operation in operations}

        missing_operations = graph_ids - operation_ids
        if missing_operations:
            raise ExecutionPlanRejected(
                "execution plan graph node missing transaction operation: "
                f"{sorted(missing_operations)!r}"
            )

        missing_nodes = operation_ids - graph_ids
        if missing_nodes:
            raise ExecutionPlanRejected(
                "execution plan transaction operation missing graph node: "
                f"{sorted(missing_nodes)!r}"
            )

        operations_by_id = {
            operation.operation_id: operation
            for operation in operations
        }
        for node in graph_nodes:
            operation = operations_by_id[node.node_id]
            if node.operation != operation.operation:
                raise ExecutionPlanRejected(
                    "execution plan graph node operation mismatch: "
                    f"{node.node_id!r}"
                )

    def _graph_source_structure(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "node_id": node.node_id,
                    "operation": node.operation,
                    "runtime_args": node.runtime_args,
                    "payload": node.payload,
                    "metadata": node.metadata,
                    "sequence": node.sequence,
                }
                for node in self._graph.list_nodes()
            ],
            "edges": [
                {
                    "from_node_id": edge.from_node_id,
                    "to_node_id": edge.to_node_id,
                    "reason": edge.reason,
                    "metadata": edge.metadata,
                    "sequence": edge.sequence,
                }
                for edge in self._graph.list_edges()
            ],
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise ExecutionPlanRejected(f"execution plan {field_name} is required")

        return value
