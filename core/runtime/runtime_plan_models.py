from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RuntimePlanNode:
    node_id: str
    node_type: str
    targets: List[str]
    description: str = ""
    depends_on: List[str] = field(default_factory=list)
    verification: List[str] = field(default_factory=list)
    force_verification_failure: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "targets": list(self.targets),
            "description": self.description,
            "depends_on": list(self.depends_on),
            "verification": list(self.verification),
            "force_verification_failure": self.force_verification_failure,
        }


@dataclass
class RuntimePlanEdge:
    from_node: str
    to_node: str
    edge_type: str = "depends_on"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": self.from_node,
            "to": self.to_node,
            "edge_type": self.edge_type,
        }


@dataclass
class RuntimePlanGraph:
    plan_id: str
    task_id: str
    goal: str
    nodes: List[RuntimePlanNode]
    edges: List[RuntimePlanEdge]
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "zero.aer.runtime_mutation_plan_graph.v1",
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "goal": self.goal,
            "created_at": self.created_at,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }
